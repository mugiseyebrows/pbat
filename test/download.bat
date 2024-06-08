@echo off
rem This file is generated from download.pbat, all edits will be lost
if exist "C:\Program Files\Git\mingw32\bin\curl.exe" set CURL=C:\Program Files\Git\mingw32\bin\curl.exe
if exist "C:\Program Files\Git\mingw64\bin\curl.exe" set CURL=C:\Program Files\Git\mingw64\bin\curl.exe
if exist "C:\Windows\System32\curl.exe" set CURL=C:\Windows\System32\curl.exe
if not defined CURL (
echo CURL not found
exit /b
)
rem no dest
"%CURL%" -L -o origname.png http://example.com/origname.png
rem no dest c
if not exist origname.png "%CURL%" -L -o origname.png http://example.com/origname.png
rem dest
"%CURL%" -L -o img.png http://example.com/origname.png
rem dest c
if not exist img.png "%CURL%" -L -o img.png http://example.com/origname.png
rem dest cache
if not exist img.png "%CURL%" -L -o img.png http://example.com/origname.png