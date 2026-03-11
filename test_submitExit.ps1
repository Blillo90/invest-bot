# Test: simula un job con error y otro sin error
# Verifica que el if/else funciona igual que el operador ternario ?: de PS7

Write-Host "=== Test 1: Job con ERROR ===" -ForegroundColor Cyan

$job = Start-Job -ScriptBlock {
    Write-Error "Error simulado"
}
$null = Wait-Job $job
$null = Receive-Job $job -ErrorAction SilentlyContinue

if ($job.ChildJobs[0].Error.Count -gt 0) { $submitExit = 1 } else { $submitExit = 0 }
Remove-Job $job -Force

if ($submitExit -eq 1) {
    Write-Host "OK - submitExit = $submitExit (detectó el error)" -ForegroundColor Green
} else {
    Write-Host "FALLO - submitExit = $submitExit (deberia ser 1)" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Test 2: Job SIN error ===" -ForegroundColor Cyan

$job = Start-Job -ScriptBlock {
    Write-Output "Todo bien"
}
$null = Wait-Job $job
$null = Receive-Job $job

if ($job.ChildJobs[0].Error.Count -gt 0) { $submitExit = 1 } else { $submitExit = 0 }
Remove-Job $job -Force

if ($submitExit -eq 0) {
    Write-Host "OK - submitExit = $submitExit (sin errores)" -ForegroundColor Green
} else {
    Write-Host "FALLO - submitExit = $submitExit (deberia ser 0)" -ForegroundColor Red
}
