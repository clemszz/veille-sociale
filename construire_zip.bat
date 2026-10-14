@echo off
rem Fabrique sur le Bureau le dossier "Veille AIPALS" (prêt à l'emploi) et "Veille AIPALS.zip".
rem Prérequis : .venv avec requirements.txt + pyinstaller, et un .env contenant la clé Gemini.
rem L'exe embarque aussi ces fichiers (dossier "defaut") : lancé seul, même depuis le zip, il fonctionne.
cd /d "%~dp0"
set BUREAU=%USERPROFILE%\Desktop
set P=%BUREAU%\Veille AIPALS
rmdir /s /q "%P%" 2>nul
del "%BUREAU%\Veille AIPALS.zip" 2>nul
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --console --name "Veille juridique" --icon "%CD%\assets\icone.ico" ^
  --add-data "%CD%\config.yaml;defaut" --add-data "%CD%\.env;defaut" --add-data "%CD%\templates;defaut\templates" ^
  --add-data "%CD%\assets;defaut\assets" --add-data "%CD%\data;defaut\data" ^
  --workpath "%TEMP%\veille-build" --specpath "%TEMP%\veille-build" --distpath "%P%" lanceur.py || exit /b 1
xcopy /e /i /q templates "%P%\templates" >nul
xcopy /e /i /q assets "%P%\assets" >nul
xcopy /e /i /q data "%P%\data" >nul
copy config.yaml "%P%" >nul
copy .env "%P%" >nul
copy LISEZMOI.txt "%P%" >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path '%P%' -DestinationPath '%BUREAU%\Veille AIPALS.zip'"
echo Dossier et zip "Veille AIPALS" crees sur le Bureau.
