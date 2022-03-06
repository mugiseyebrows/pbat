@echo off
rem This file is generated from hello4.pbat, all edits will be lost
set PATH=C:\Program Files\7-Zip;C:\Program Files (x86)\7-Zip

if exist "C:\msys64\usr\bin\curl.exe" set CURL=C:\msys64\usr\bin\curl.exe
if exist "C:\Program Files\Git\mingw64\bin\curl.exe" set CURL=C:\Program Files\Git\mingw64\bin\curl.exe
if exist "C:\Windows\System32\curl.exe" set CURL=C:\Windows\System32\curl.exe
if not defined CURL goto curl_not_found_begin
goto fetch_begin

:curl_not_found_begin
echo curl not found
exit /b

:fetch_begin
if not exist "0.0.14.zip" "%CURL%" -L -o "0.0.14.zip" https://github.com/mugiseyebrows/event-loop/archive/refs/tags/0.0.14.zip
if not exist "0.0.14" 7z x -y "0.0.14.zip"


