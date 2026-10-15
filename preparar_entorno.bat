@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS="

if exist "%PROJECT_DIR%backend\requirements.txt" set "REQUIREMENTS=%PROJECT_DIR%backend\requirements.txt"
if not defined REQUIREMENTS if exist "%PROJECT_DIR%requirements.txt" set "REQUIREMENTS=%PROJECT_DIR%requirements.txt"

if exist "%VENV_PY%" (
    call :check_environment
    if not errorlevel 1 goto environment_ok
    echo El entorno existe, pero esta incompleto. Instalando dependencias...
) else (
    echo Creando entorno virtual...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        where python >nul 2>&1
        if errorlevel 1 goto python_missing
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 goto setup_failed
)

echo Actualizando pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto setup_failed

if defined REQUIREMENTS (
    echo Instalando requisitos del proyecto desde:
    echo %REQUIREMENTS%
    "%VENV_PY%" -m pip install -r "%REQUIREMENTS%"
    if errorlevel 1 goto setup_failed
)

echo Instalando Jupyter y paquetes de procesamiento de imagen...
"%VENV_PY%" -m pip install numpy opencv-contrib-python matplotlib jupyterlab ipywidgets
if errorlevel 1 goto setup_failed

call :check_environment
if errorlevel 1 goto setup_failed

echo.
echo El entorno y los imports necesarios estan listos.
echo Virtual environment: %VENV_DIR%
echo Para iniciar Jupyter, ejecuta: %VENV_DIR%\Scripts\jupyter.exe lab
goto finish

:environment_ok
echo El entorno ya existe y las dependencias principales funcionan.
echo Todo esta correcto.
echo Virtual environment: %VENV_DIR%
echo Para iniciar Jupyter, ejecuta: %VENV_DIR%\Scripts\jupyter.exe lab
goto finish

:check_environment
echo Checking Python imports...
"%VENV_PY%" -c "import numpy, cv2, matplotlib, matplotlib.pyplot, jupyterlab, ipywidgets; print('Imports OK')"
if errorlevel 1 exit /b 1
echo Checking installed package compatibility...
"%VENV_PY%" -m pip check
if errorlevel 1 exit /b 1
exit /b 0

:python_missing
echo No se encontro Python 3. Instalalo y vuelve a intentarlo.
goto finish_error

:setup_failed
echo La configuracion fallo. Revisa el error anterior y vuelve a intentarlo.
goto finish_error

:finish_error
set "RESULT=1"
goto finish_pause

:finish
set "RESULT=0"

:finish_pause
echo.
pause
exit /b %RESULT%
