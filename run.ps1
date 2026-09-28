<#
.SYNOPSIS
  Organizador de Tarefas: prepara o ambiente (na primeira vez) e inicia o servidor.

.EXAMPLE
  .\run.ps1                      # http://localhost:8000
  .\run.ps1 -Port 8080 -Lan      # acessível por outros computadores da rede
  .\run.ps1 -Demo                # dados de demonstração (banco separado, ~1.000 tarefas)
  .\run.ps1 -Test                # testes automatizados com cobertura

  Se a execução de scripts estiver bloqueada:
  powershell -ExecutionPolicy Bypass -File .\run.ps1
#>
param(
  [int]$Port = 8000,
  [switch]$Lan,
  [switch]$Demo,
  [switch]$Test
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$home_ = Join-Path $env:LOCALAPPDATA "OrganizadorDeTarefas"
# O ambiente virtual e os dados ficam fora do OneDrive: sincronizar milhares de arquivos ou um SQLite em uso causa problemas.
$venv = Join-Path $home_ "venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
  Write-Host "Criando ambiente virtual em $venv ..."
  New-Item -ItemType Directory -Force $home_ | Out-Null
  if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv $venv } else { & python -m venv $venv }
}

# Instala dependências só quando os arquivos de requisitos mudam.
$reqFiles = @("requirements.txt", "requirements-dev.txt") | ForEach-Object { Join-Path $root $_ }
$hash = ($reqFiles | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash }) -join ""
$marker = Join-Path $venv ".requirements.sha256"
if (-not (Test-Path $marker) -or (Get-Content $marker -Raw).Trim() -ne $hash) {
  Write-Host "Instalando dependências ..."
  & $python -m pip install --disable-pip-version-check -q -r (Join-Path $root "requirements-dev.txt")
  if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependências." }
  Set-Content -Path $marker -Value $hash -Encoding ascii
}

Push-Location $root
try {
  if ($Test) {
    $env:SCHEDULER_ENABLED = "false"
    & $python -m pytest --cov=app --cov-report=term-missing
    exit $LASTEXITCODE
  }
  if ($Demo) {
    $env:DATA_DIR = Join-Path $home_ "demo"
    $env:SCHEDULER_ENABLED = "false"
    if (-not (Test-Path (Join-Path $env:DATA_DIR "organizador.sqlite3"))) {
      Write-Host "Gerando dados de demonstração em $env:DATA_DIR ..."
      & $python -m app.demo --tasks 250
    }
  }
  $bind = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
  Write-Host ""
  Write-Host "Organizador de Tarefas em http://localhost:$Port  (API: http://localhost:$Port/api/docs)"
  if ($Lan) { Write-Host "Na rede: http://$($env:COMPUTERNAME):$Port  — para uso offline/instalação (PWA) em outros aparelhos, publique com HTTPS." }
  Write-Host "Ctrl+C para encerrar."
  & $python -m uvicorn app.main:app --host $bind --port $Port --proxy-headers
}
finally {
  Pop-Location
}
