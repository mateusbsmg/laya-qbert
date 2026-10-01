@echo off
rem Liga o Q*bert com o Laya (porta 8768) e abre o navegador.
cd /d "%~dp0"
set HF_HOME=D:\Mateus\.hf-cache
start "Laya - Q*bert" .venv\Scripts\python.exe qbert\servidor_laya.py
echo Carregando o Laya...
:espera
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { if ((Invoke-RestMethod http://127.0.0.1:8768/api/health -TimeoutSec 2).laya_pronto) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1 || goto espera
start http://127.0.0.1:8768
echo Pronto. Para desligar, feche a janela "Laya - Q*bert".
