# fix_tasks.ps1 - Re-register Heatseeker schtasks with proper S4U principals.
# Right-click -> Run with PowerShell (it self-elevates), or run from an admin terminal.

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\proio\newerthanthelastbuildforant'

# --- self-elevate if needed ---
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Not elevated - relaunching as Administrator..."
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host "== Elevated: $($id.Name) =="

# --- unregister broken tasks ---
foreach ($tn in @('HeatseekerWatch', 'HeatseekerDaily')) {
    schtasks /delete /tn $tn /f 2>&1 | Out-Null
    Write-Host "unregistered: $tn"
}

# --- re-register from patched XMLs (Principals/S4U now inside) ---
schtasks /create /tn 'HeatseekerWatch' /xml "$repo\ops\watch_loop.xml" /f
schtasks /create /tn 'HeatseekerDaily' /xml "$repo\ops\daily_loop.xml" /f

# --- fire the watch task NOW and verify for real ---
Remove-Item "$repo\ledger\loop.log" -ErrorAction SilentlyContinue
schtasks /run /tn 'HeatseekerWatch' | Out-Null
Write-Host "fired HeatseekerWatch, waiting for run..."
Start-Sleep -Seconds 25

$log = Test-Path "$repo\ledger\loop.log"
$watch = schtasks /query /tn 'HeatseekerWatch' /v /fo LIST | Select-String 'Last Result'
$mark = & "$repo\.venv\Scripts\python.exe" -c "import json; m=json.load(open(r'$repo\ledger\state.json'))['marks']['BTC/USD']; print(m['ts'])" 2>$null

Write-Host ""
Write-Host "== VERIFICATION =="
Write-Host "loop.log created:  $log"
Write-Host "watch LastResult:  $watch  (expect 0)"
Write-Host "BTC mark ts:       $mark  (expect ~now, not 07:33Z)"
if ($log -and ($watch -match '0')) {
    Write-Host "RESULT: TASKS FIXED AND RUNNING" -ForegroundColor Green
} else {
    Write-Host "RESULT: STILL FAILING - run schtasks /query manually and check" -ForegroundColor Yellow
}
Write-Host ""
Read-Host "Press Enter to close"