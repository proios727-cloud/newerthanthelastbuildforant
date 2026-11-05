@echo off
rem Wi-Fi Check: double-click to run. Read-only: it never logs into or changes your router.
rem Pings your router and the internet for a few minutes, tracks your Wi-Fi band and signal,
rem then says whether drops come from your Wi-Fi or your internet provider.
title Wi-Fi Check
set "WIFICHECK_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:WIFICHECK_SELF); $m='#'+'#PS'; iex $s.Substring($s.IndexOf($m)+$m.Length)"
echo.
pause
exit /b
##PS
$ErrorActionPreference = 'Continue'
$InternetHost = '1.1.1.1'

function Get-Median([double[]]$v) {
    if (-not $v -or $v.Count -eq 0) { return $null }
    $s = $v | Sort-Object
    $n = $s.Count
    if ($n % 2) { return [double]$s[[int](($n - 1) / 2)] }
    return ([double]$s[$n / 2 - 1] + [double]$s[$n / 2]) / 2
}

function ConvertFrom-Netsh([string[]]$lines) {
    # "    Radio type             : 802.11ax" -> @{ 'Radio type' = '802.11ax' }. Exact keys, so BSSID never matches SSID.
    $h = @{}
    foreach ($l in $lines) {
        if ($l -match '^\s*([^:]+?)\s+:\s(.*)$') {
            $k = $Matches[1].Trim()
            if (-not $h.ContainsKey($k)) { $h[$k] = $Matches[2].Trim() }
        }
    }
    $sig = $null
    if ($h['Signal'] -match '(\d+)') { $sig = [int]$Matches[1] }
    $band = $h['Band']
    if (-not $band -and $h['Channel'] -match '^\d+$') { if ([int]$h['Channel'] -le 14) { $band = '2.4 GHz' } else { $band = '5 GHz' } }
    [pscustomobject]@{
        SSID = $h['SSID']; Radio = $h['Radio type']; Band = $band; Channel = $h['Channel']
        RxMbps = $h['Receive rate (Mbps)']; TxMbps = $h['Transmit rate (Mbps)']; Signal = $sig
        State = $h['State']
    }
}

function Get-Wifi { ConvertFrom-Netsh (netsh wlan show interfaces 2>$null) }

function Get-Gateway {
    try {
        $r = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop | Sort-Object RouteMetric | Select-Object -First 1
        if ($r -and $r.NextHop -ne '0.0.0.0') { return $r.NextHop }
    } catch { }
    $m = (ipconfig) | Select-String 'Default Gateway[ .]*:\s*(\d+\.\d+\.\d+\.\d+)' | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value }
    return $null
}

function Send-Ping([string]$target) {
    if (-not $target) { return $null }
    try {
        $r = (New-Object System.Net.NetworkInformation.Ping).Send($target, 1000)
        if ($r.Status -eq 'Success') { return [double][Math]::Max([double]$r.RoundtripTime, 0.5) }
    } catch { }
    return $null
}

function Get-SideStats($samples, [string]$key) {
    # Spike: over min(100, max(3x median, median + 30)) ms. Drop: no reply. Same rule as router_doctor.py.
    $vals = @($samples | Where-Object { $null -ne $_.$key } | ForEach-Object { [double]$_.$key })
    $med = Get-Median $vals
    $bad = @()
    if ($null -ne $med) { $thr = [Math]::Min(100, [Math]::Max(3 * $med, $med + 30)) } else { $thr = 0 }
    for ($i = 0; $i -lt $samples.Count; $i++) {
        $x = $samples[$i].$key
        if ($null -eq $x -or ($null -ne $med -and $x -gt $thr)) { $bad += $i }
    }
    [pscustomobject]@{
        Median = $med
        Drops = @($samples | Where-Object { $null -eq $_.$key }).Count
        Spikes = $bad.Count
        BadAt = $bad
    }
}

function Get-Cause($samples) {
    $gw = Get-SideStats $samples 'Router'
    $net = Get-SideStats $samples 'Internet'
    if ($samples.Count -eq 0 -or ($null -eq $gw.Median -and $null -eq $net.Median)) { $cause = 'no_data' }
    elseif ($net.BadAt.Count -eq 0) { $cause = 'stable' }
    else {
        $shared = @($net.BadAt | Where-Object { $gw.BadAt -contains $_ }).Count
        if ($null -ne $gw.Median -and $shared -ge 0.5 * $net.BadAt.Count) { $cause = 'wifi_link' } else { $cause = 'isp_or_upstream' }
    }
    [pscustomobject]@{ Cause = $cause; Router = $gw; Internet = $net; Samples = $samples.Count }
}

function Test-Dfs($channel) {
    # 5 GHz channels 52-144 share spectrum with radar. When the router hears radar it must
    # leave the channel at once, so devices drop for seconds to a minute (DFS).
    $c = 0
    if (-not [int]::TryParse([string]$channel, [ref]$c)) { return $false }
    return ($c -ge 52 -and $c -le 144)
}

function Get-ChannelChanges($samples) {
    # Channel switches seen during the run, each with the drops/spikes within 30 s before it.
    $changes = @()
    $prev = $null
    for ($i = 0; $i -lt $samples.Count; $i++) {
        $ch = [string]$samples[$i].Channel
        if (-not $ch) { continue }
        if ($null -ne $prev -and $ch -ne $prev.Channel) {
            $lo = [Math]::Max(0, $i - 15)
            $hits = @($samples[$lo..$i] | Where-Object { $null -eq $_.Router -or $null -eq $_.Internet }).Count
            $changes += [pscustomobject]@{ Time = $samples[$i].Time; From = $prev.Channel; To = $ch
                FromDfs = (Test-Dfs $prev.Channel); DropsBefore = $hits }
        }
        $prev = [pscustomobject]@{ Channel = $ch }
    }
    return $changes
}

function Get-Advice([string]$cause, $bands, $minSignal, $startChannel, $changes) {
    $a = @()
    switch ($cause) {
        'wifi_link' {
            $a += 'The hiccups start between this PC and your router, so it is your Wi-Fi, not your provider.'
            if (@($changes | Where-Object { $_.FromDfs }).Count) { break }  # radar event explains it; coverage advice would mislead
            $a += 'eero app: tap this PC in the device list; check which eero it is on, the band and the signal.'
            $a += 'Turn on "Optimize for conferencing and gaming" if your app shows it, then restart the network once from the app.'
            $a += 'If the PC is far from its eero, move the eero or add a node. No setting replaces coverage.'
        }
        'isp_or_upstream' {
            $a += 'Your Wi-Fi to the router was fine at the moments the internet hiccuped. That points at your provider or line.'
            $a += 'eero app: run its speed test. If it is slow there too, report it to your provider with this report.'
        }
        'stable' {
            $a += 'Nothing caught this time. Run it again at the time of day it usually acts up.'
        }
        'no_data' {
            $a += 'Neither the router nor the internet answered. Make sure this PC is connected to your home Wi-Fi.'
        }
    }
    if (@($bands | Select-Object -Unique).Count -gt 1) {
        $a += "Your PC switched Wi-Fi bands during the test ($((@($bands | Select-Object -Unique)) -join ' <-> ')). Band hopping often causes short drops."
    } elseif ($bands -contains '2.4 GHz') {
        $a += 'Your PC was on 2.4 GHz (slower, more interference). Being close to the eero should normally give 5 GHz.'
    }
    if ($null -ne $minSignal -and $minSignal -lt 60) {
        $a += "Signal dipped to $minSignal%. Under ~60% means distance or walls are in the way."
    }
    $radar = @($changes | Where-Object { $_.FromDfs })
    if ($radar.Count) {
        foreach ($c in $radar) {
            $a += "At $($c.Time) the eero left radar-shared channel $($c.From) for $($c.To) ($($c.DropsBefore) drops just before). That is a radar (DFS) event, a known cause of short random drops."
        }
        $a += 'If this keeps happening, ask eero support or your provider to keep the 5 GHz radio off radar channels (52-144). The eero app does not let you pick a channel.'
    } elseif (@($changes).Count) {
        $a += "The Wi-Fi channel changed during the test ($((@($changes | ForEach-Object { "$($_.From)->$($_.To) at $($_.Time)" })) -join ', '))."
    } elseif (Test-Dfs $startChannel) {
        $a += "You are on channel $startChannel, which is radar-shared (DFS). Fine for now, but radar events force a channel switch and a short drop. If drops come back, rerun this: a channel change in the report confirms it."
    }
    $a += 'ISP-supplied eeros can have settings locked; if an option is missing, your provider controls it.'
    return $a
}

function Format-Ms($v) { if ($null -eq $v) { 'none' } else { '{0:N0} ms' -f $v } }

function Invoke-WifiCheck {
    Write-Host ''
    Write-Host '  Wi-Fi Check (read-only)' -ForegroundColor Cyan
    Write-Host '  Best run WHILE the Wi-Fi is acting up.' -ForegroundColor DarkGray
    Write-Host ''
    $in = Read-Host '  Minutes to watch (Enter = 15)'
    $minutes = 15
    if ($in -match '^\d+(\.\d+)?$') { $minutes = [double]$in }

    $wifi = Get-Wifi
    $gw = Get-Gateway
    Write-Host ''
    Write-Host ("  Network: {0} | {1} | {2} ch {3} | signal {4}% | rx {5} / tx {6} Mbps" -f $wifi.SSID, $wifi.Radio, $wifi.Band, $wifi.Channel, $wifi.Signal, $wifi.RxMbps, $wifi.TxMbps)
    if (Test-Dfs $wifi.Channel) { Write-Host "  Note: channel $($wifi.Channel) is radar-shared (DFS). Watching for forced channel switches." -ForegroundColor DarkYellow }
    Write-Host ("  Router:  {0}" -f $(if ($gw) { $gw } else { 'not found' }))
    Write-Host ''

    $samples = New-Object System.Collections.Generic.List[object]
    $bands = New-Object System.Collections.Generic.List[string]
    $signals = New-Object System.Collections.Generic.List[int]
    $end = (Get-Date).AddMinutes($minutes)
    $total = [int]($minutes * 30)
    $i = 0
    $lastCh = [string]$wifi.Channel
    while ((Get-Date) -lt $end) {
        $t = Get-Date
        $r = Send-Ping $gw
        $n = Send-Ping $InternetHost
        $w = $null
        if ($i % 5 -eq 0) {
            $w = Get-Wifi
            if ($w.Band) { $bands.Add($w.Band) }
            if ($null -ne $w.Signal) { $signals.Add($w.Signal) }
            if ($w.Channel -and $lastCh -and [string]$w.Channel -ne $lastCh) {
                Write-Host ("  {0}  CHANNEL CHANGED {1} -> {2}{3}" -f $t.ToString('HH:mm:ss'), $lastCh, $w.Channel, $(if (Test-Dfs $lastCh) { '  (left a radar channel)' } else { '' })) -ForegroundColor Magenta
            }
            if ($w.Channel) { $lastCh = [string]$w.Channel }
        }
        $samples.Add([pscustomobject]@{ Time = $t.ToString('HH:mm:ss'); Router = $r; Internet = $n
            Band = $(if ($w) { $w.Band } else { '' }); Channel = $(if ($w) { $w.Channel } else { '' }); Signal = $(if ($w) { $w.Signal } else { '' }) })
        $line = "  {0}  router {1,7}  internet {2,7}" -f $t.ToString('HH:mm:ss'), (Format-Ms $r), (Format-Ms $n)
        if ($null -eq $r -or $null -eq $n -or $r -gt 100 -or $n -gt 100) { Write-Host $line -ForegroundColor Yellow } else { Write-Host $line -ForegroundColor DarkGray }
        $i++
        Write-Progress -Activity 'Watching Wi-Fi' -Status "$i samples" -PercentComplete ([Math]::Min(100, 100 * $i / [Math]::Max(1, $total)))
        $left = 2 - ((Get-Date) - $t).TotalSeconds
        if ($left -gt 0) { Start-Sleep -Milliseconds ([int]($left * 1000)) }
    }
    Write-Progress -Activity 'Watching Wi-Fi' -Completed

    $res = Get-Cause $samples
    $minSig = $null
    if ($signals.Count) { $minSig = ($signals | Measure-Object -Minimum).Minimum }
    $changes = Get-ChannelChanges $samples
    $advice = Get-Advice $res.Cause $bands $minSig $wifi.Channel $changes
    $label = @{ wifi_link = 'YOUR WI-FI'; isp_or_upstream = 'YOUR INTERNET PROVIDER'; stable = 'NOTHING CAUGHT (stable)'; no_data = 'NO DATA' }[$res.Cause]

    $report = @()
    $report += "Wi-Fi Check  $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    $report += "Network: $($wifi.SSID) | $($wifi.Radio) | $($wifi.Band) ch $($wifi.Channel) | signal $($wifi.Signal)% | rx $($wifi.RxMbps) / tx $($wifi.TxMbps) Mbps"
    $report += "Router: $gw   Samples: $($res.Samples) over $minutes min"
    $report += ''
    $report += "VERDICT: $label"
    $report += ("Router link:   median {0}, spikes {1}, drops {2}" -f (Format-Ms $res.Router.Median), $res.Router.Spikes, $res.Router.Drops)
    $report += ("Internet link: median {0}, spikes {1}, drops {2}" -f (Format-Ms $res.Internet.Median), $res.Internet.Spikes, $res.Internet.Drops)
    $chs = @($samples | Where-Object { $_.Channel } | ForEach-Object { [string]$_.Channel } | Select-Object -Unique)
    $chNote = @($chs | ForEach-Object { if (Test-Dfs $_) { "$_ (radar-shared)" } else { "$_" } }) -join ' -> '
    $report += "Channels seen: $(if ($chNote) { $chNote } else { 'unknown' })   Channel changes: $(@($changes).Count)"
    $report += "Bands seen: $(if ($bands.Count) { (@($bands | Select-Object -Unique)) -join ', ' } else { 'unknown' })   Lowest signal: $(if ($null -ne $minSig) { "$minSig%" } else { 'unknown' })"
    $report += ''
    $report += 'What to do:'
    foreach ($x in $advice) { $report += " - $x" }

    $desk = [Environment]::GetFolderPath('Desktop')
    if (-not $desk -or -not (Test-Path $desk)) { $desk = $env:TEMP }
    if (-not $desk) { $desk = (Get-Location).Path }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmm'
    $txt = Join-Path $desk "WiFi-Check-$stamp.txt"
    $csv = Join-Path $desk "WiFi-Check-$stamp.csv"
    $report | Set-Content -Path $txt -Encoding UTF8
    $samples | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8

    Write-Host ''
    $color = @{ wifi_link = 'Yellow'; isp_or_upstream = 'Magenta'; stable = 'Green'; no_data = 'Red' }[$res.Cause]
    Write-Host "  VERDICT: $label" -ForegroundColor $color
    $report | Select-Object -Skip 5 | ForEach-Object { Write-Host "  $_" }
    Write-Host ''
    Write-Host "  Saved: $txt" -ForegroundColor Cyan
    Write-Host '  Send that file (or a screenshot of this window) to Claude.' -ForegroundColor Cyan
    try { Start-Process notepad.exe $txt } catch { }
}

if (-not $env:WIFICHECK_TEST) { Invoke-WifiCheck }
