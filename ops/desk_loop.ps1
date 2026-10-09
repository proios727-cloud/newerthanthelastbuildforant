# desk_loop.ps1 - persistent desk automation (replaces Task Scheduler launches).
# Runs, in the logged-on session:
#   - Heatseeker watch pass every 15 min (on wall-clock quarters)
#   - Heatseeker full daily loop at 08:45 and 20:15 local
#   - Etsy operator cycle at 08:45 daily (Mondays 08:40)
# Single-instance via a global mutex. All state in ledger\desk_loop_state.
$desk = 'C:\Users\proio\newerthanthelastbuildforant'
$op   = 'C:\Users\proio\etsy-shop\operator'
$log  = "$desk\ledger\loop.log"
$state = "$desk\ledger\desk_loop_state"
$pyDesk = "$desk\.venv\Scripts\python.exe"
$pySys  = 'C:\Python314\python.exe'

function Log($m) {
  try { Add-Content $log ("[{0}] desk_loop: {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) } catch {}
}
function GetState($k) {
  if (Test-Path $state) {
    $hit = Select-String -Path $state -Pattern ("^" + $k + "=") -ErrorAction SilentlyContinue
    if ($hit) { return ($hit.Line -replace "^[^=]+=", "") }
  }
  return ""
}
function SetState($k, $v) {
  $lines = @()
  if (Test-Path $state) {
    $lines = @(Get-Content $state | Where-Object { $_ -notmatch ("^" + $k + "=") })
  }
  $lines += "$k=$v"
  Set-Content -Path $state -Value $lines
}
function RunStep($name, $exe, $arg, $wd) {
  Log ("run: " + $name)
  try {
    $p = Start-Process -FilePath $exe -ArgumentList $arg -WorkingDirectory $wd -Wait -PassThru -WindowStyle Hidden
    Log ("done: " + $name + " (exit " + $p.ExitCode + ")")
  } catch { Log ("FAILED: " + $name + ": " + $_.Exception.Message) }
}

$mtx = New-Object System.Threading.Mutex($false, 'Global\DeskLoop')
if (-not $mtx.WaitOne(0)) { Log "another desk_loop is already running - exiting"; exit }

Log ("started (pid " + $PID + ")")
while ($true) {
  try {
    $now = Get-Date
    $d = $now.ToString('yyyyMMdd')

    # 1) watch pass every wall-clock quarter
    $q = [int]($now.Minute / 15)
    $qkey = "$d-$($now.Hour)-$q"
    if ((GetState 'watch') -ne $qkey) {
      RunStep 'heatseeker-watch' $pyDesk '-m fund loop --watch' $desk
      SetState 'watch' $qkey
    }

    # 2) heatseeker daily loops
    if ($now.Hour -gt 8 -or ($now.Hour -eq 8 -and $now.Minute -ge 45)) {
      if ((GetState 'hdam') -ne "$d-am") {
        RunStep 'heatseeker-daily-am' $pyDesk '-m fund loop --once' $desk
        SetState 'hdam' "$d-am"
      }
    }
    if ($now.Hour -ge 20 -and $now.Minute -ge 15) {
      if ((GetState 'hdpm') -ne "$d-pm") {
        RunStep 'heatseeker-daily-pm' $pyDesk '-m fund loop --once' $desk
        SetState 'hdpm' "$d-pm"
      }
    }

    # 3) etsy cycle (Mon 08:40, else 08:45)
    $startMin = 45; if ($now.DayOfWeek -eq 'Monday') { $startMin = 40 }
    if ($now.Hour -gt 8 -or ($now.Hour -eq 8 -and $now.Minute -ge $startMin)) {
      if ((GetState 'etsy') -ne $d) {
        RunStep 'etsy-cycle' $pySys ($op + '\engine\run_daily.py') $op
        SetState 'etsy' $d
      }
    }
  } catch { Log ("loop error: " + $_.Exception.Message) }
  Start-Sleep -Seconds 20
}