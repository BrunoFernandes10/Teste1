@echo off
REM Atalho para quem prefere nao usar o terminal: dois cliques neste arquivo.
REM Ele se posiciona sozinho na propria pasta, entao nao existe erro de caminho.
cd /d "%~dp0"

echo.
echo   Analise de Sentimento de Perfis do Instagram
echo   -------------------------------------------
echo.

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo   [ERRO] Python nao encontrado nesta maquina.
    echo.
    echo   Instale em https://www.python.org/downloads/
    echo   Marque a caixa "Add python.exe to PATH" durante a instalacao,
    echo   feche esta janela e abra de novo.
    echo.
    pause
    exit /b 1
  )
  py iniciar.py
) else (
  python iniciar.py
)

echo.
echo   A janela vai ficar aberta para voce ler as mensagens acima.
pause
