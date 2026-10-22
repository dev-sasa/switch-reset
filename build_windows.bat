@echo off
REM Baut switch_reset.exe (eigenstaendig, kein Python noetig zum Ausfuehren).
REM Muss EINMAL auf einem Windows-PC mit installiertem Python ausgefuehrt werden.
cd /d "%~dp0"
python -m venv .venv || goto :fehler
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip pyserial pyinstaller || goto :fehler
pyinstaller --onefile --console --name switch_reset switch_reset.py || goto :fehler
echo.
echo Fertig: dist\switch_reset.exe  (diese Datei einfach auf jeden Windows-PC kopieren)
pause
exit /b 0
:fehler
echo Build fehlgeschlagen.
pause
exit /b 1
