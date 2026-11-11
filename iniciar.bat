@echo off
chcp 65001 >nul
title SIGE - Gestion Eficiente de Estacionamientos (Hito 2)
echo ============================================================
echo   SIGE - Gestion Eficiente de Estacionamientos (Hito 2)
echo   Iniciando aplicacion en Streamlit...
echo ============================================================
if exist "..\Emprendimiento\.venv\Scripts\streamlit.exe" (
    "..\Emprendimiento\.venv\Scripts\streamlit.exe" run app.py
) else (
    streamlit run app.py
)
pause
