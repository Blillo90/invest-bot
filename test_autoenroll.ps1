# Test local del flujo autoenroll (sin Invoke-Command)
# Ejecutar como Administrador en la maquina objetivo

$ErrorActionPreference = "Stop"
$cesTimeoutSec = 20

Write-Host ""
Write-Host "=== TEST AUTOENROLL CERTIFICADO ===" -ForegroundColor Cyan
Write-Host "Maquina: $env:COMPUTERNAME"
Write-Host ""

# ── Ficheros temporales ──────────────────────────────────────────────────────
$rand    = Get-Random -Maximum 99999
$base    = "$env:TEMP\AirbusEnrollTest_$rand"
$infPath = "$base.inf"
$reqPath = "$base.req"
$cerPath = "$base.cer"

# ── PASO 1: Generar INF y CSR ────────────────────────────────────────────────
Write-Host "[ PASO 1 ] certreq -new (genera CSR)..." -ForegroundColor Yellow

@"
[Version]
Signature="`$Windows NT`$"

[NewRequest]
Subject = "CN=$env:COMPUTERNAME"
MachineKeySet = TRUE
KeySpec       = AT_KEYEXCHANGE
KeyLength     = 2048
Exportable    = FALSE
RequestType   = PKCS10

"@ | Out-File $infPath -Encoding ASCII

# La plantilla NO va en el INF — certreq -new la consultaria via CEP (sin red)
# Se pasa como -attrib al certreq -submit directamente al CES
$newOut = certreq -new -machine -q $infPath $reqPath 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FALLO - certreq -new (ExitCode=$LASTEXITCODE)" -ForegroundColor Red
    Write-Host "  $($newOut -join "`n  ")"
    Remove-Item $infPath -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "  OK - CSR generado en $reqPath" -ForegroundColor Green

# ── PASO 2: Submit a cada CES con timeout y deteccion de error ───────────────
Write-Host ""
Write-Host "[ PASO 2 ] certreq -submit a servidores CES..." -ForegroundColor Yellow

$cesUrls = @(
    "https://aefews01.autoenroll.pki.intra.corp/Airbus%20Issuing%20CA%20Breguet%20G1_CES_Kerberos/service.svc/CES",
    "https://aefews02.autoenroll.pki.intra.corp/Airbus%20Issuing%20CA%20Breguet%20G1_CES_Kerberos/service.svc/CES",
    "https://aefews01.autoenroll.pki.intra.corp/Airbus%20Issuing%20CA%20da%20Vinci%20G1_CES_Kerberos/service.svc/CES",
    "https://aefews02.autoenroll.pki.intra.corp/Airbus%20Issuing%20CA%20da%20Vinci%20G1_CES_Kerberos/service.svc/CES"
)

$submitOk  = $false
$lastErr   = ""

foreach ($url in $cesUrls) {
    Write-Host "  -> $url"

    $job = Start-Job -ScriptBlock {
        param($u, $rq, $cp)
        certreq -submit -config $u -attrib "CertificateTemplate:AirbusAutoEnrolledClientAuthentication" -q -machine $rq $cp 2>&1
    } -ArgumentList $url, $reqPath, $cerPath

    $null = Wait-Job $job -Timeout $cesTimeoutSec

    if ($job.State -eq 'Running') {
        Stop-Job $job; Remove-Job $job -Force
        Write-Host "     TIMEOUT (>${cesTimeoutSec}s)" -ForegroundColor DarkYellow
        Remove-Item $cerPath -Force -ErrorAction SilentlyContinue
        $lastErr = "$url TIMEOUT"
        continue
    }

    $submitOut = Receive-Job $job

    # ← LINEA CORREGIDA (if/else en lugar de operador ternario de PS7)
    if ($job.ChildJobs[0].Error.Count -gt 0) { $submitExit = 1 } else { $submitExit = 0 }
    Remove-Job $job -Force

    Write-Host "     submitExit=$submitExit  |  Salida: $($submitOut -join ' ')"

    if ($submitExit -eq 0 -and (Test-Path $cerPath)) {

        # ── PASO 3: Aceptar / instalar certificado ───────────────────────────
        Write-Host ""
        Write-Host "[ PASO 3 ] certreq -accept (instala el cert)..." -ForegroundColor Yellow
        $acceptOut = certreq -accept -machine $cerPath 2>&1
        Remove-Item $infPath,$reqPath,$cerPath -Force -ErrorAction SilentlyContinue

        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK - Certificado instalado en LocalMachine\My via $url" -ForegroundColor Green
            $submitOk = $true
        } else {
            Write-Host "  WARN - Emitido pero accept fallo (ExitCode=$LASTEXITCODE):" -ForegroundColor DarkYellow
            Write-Host "  $($acceptOut -join "`n  ")"
            $submitOk = $true   # el cert se emitio aunque no se instalo
        }
        break
    }

    $lastErr = "$url ExitCode=$submitExit : $($submitOut -join ' ')"
    Remove-Item $cerPath -Force -ErrorAction SilentlyContinue
    Write-Host "     No se obtuvo .cer - siguiendo con el siguiente servidor" -ForegroundColor DarkYellow
}

# ── Limpieza si ningún CES respondio ────────────────────────────────────────
Remove-Item $infPath,$reqPath -Force -ErrorAction SilentlyContinue

Write-Host ""
if ($submitOk) {
    Write-Host "RESULTADO: EXITO" -ForegroundColor Green
} else {
    Write-Host "RESULTADO: FALLO - $lastErr" -ForegroundColor Red
    exit 1
}
