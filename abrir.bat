@echo off
rem Organizador de Tarefas: clique duas vezes para iniciar o servidor e abrir o app no navegador.
setlocal
title Organizador de Tarefas
cd /d "%~dp0"

set "PORTA=8000"
set "URL=http://localhost:%PORTA%"
set "CHECK=$c = New-Object Net.WebClient; $c.Proxy = $null; $c.DownloadString('http://127.0.0.1:%PORTA%/api/meta') | Out-Null"

rem Se o servidor ja estiver rodando, apenas abre o navegador.
powershell -NoProfile -Command "try { %CHECK%; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
  start "" "%URL%"
  exit /b 0
)

echo.
echo  Organizador de Tarefas
echo  ----------------------
echo  Iniciando o servidor em %URL% ...
echo  O navegador abre sozinho quando o app estiver pronto.
echo  Na primeira vez as dependencias sao instaladas e pode levar alguns minutos.
echo.
echo  Mantenha esta janela aberta enquanto usa o app. Feche-a para encerrar.
echo.

rem Espera o servidor responder (ate 5 minutos) e abre o navegador.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 300; $i++) { try { %CHECK%; Start-Process '%URL%'; break } catch { Start-Sleep -Seconds 1 } }"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Port %PORTA%
if errorlevel 1 (
  echo.
  echo  Ocorreu um erro ao iniciar. Veja as mensagens acima.
  pause
)
endlocal
