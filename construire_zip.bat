@echo off
rem Fabrique "Veille juridique AIPALS.zip" (exe autonome + fichiers de travail) sur le Bureau.
rem Prérequis : .venv avec requirements.txt + pyinstaller, et un .env contenant la clé Gemini.
cd /d "%~dp0"
set P=%TEMP%\veille-paquet\Veille juridique AIPALS
rmdir /s /q "%TEMP%\veille-paquet" 2>nul
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --console --name "Veille juridique" --icon "%CD%\assets\icone.ico" --workpath "%TEMP%\veille-build" --specpath "%TEMP%\veille-build" --distpath "%P%" lanceur.py || exit /b 1
xcopy /e /i /q templates "%P%\templates" >nul
xcopy /e /i /q assets "%P%\assets" >nul
xcopy /e /i /q data "%P%\data" >nul
copy config.yaml "%P%" >nul
copy .env "%P%" >nul
copy LISEZMOI.txt "%P%" >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path '%P%' -DestinationPath \"$([Environment]::GetFolderPath('Desktop'))\Veille juridique AIPALS.zip\""
echo Zip cree sur le Bureau.
