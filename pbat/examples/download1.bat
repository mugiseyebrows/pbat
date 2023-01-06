@echo off
rem This file is generated from download1.pbat, all edits will be lost
if exist "C:\Program Files\Git\mingw64\bin\curl.exe" set CURL=C:\Program Files\Git\mingw64\bin\curl.exe
if exist "C:\Windows\System32\curl.exe" set CURL=C:\Windows\System32\curl.exe
if not defined CURL (
echo CURL not found
exit /b
)
if not exist qwt-6.2.0.zip "%CURL%" -L -o qwt-6.2.0.zip https://altushost-swe.dl.sourceforge.net/project/qwt/qwt/6.2.0/qwt-6.2.0.zip


