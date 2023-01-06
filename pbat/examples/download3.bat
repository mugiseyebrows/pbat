@echo off
rem This file is generated from download3.pbat, all edits will be lost
if exist "C:\Program Files\Git\usr\bin\md5sum.exe" set MD5SUM=C:\Program Files\Git\usr\bin\md5sum.exe
if not defined MD5SUM (
echo MD5SUM not found
exit /b
)
if not exist qwt-6.2.0.zip curl -L -o qwt-6.2.0.zip https://altushost-swe.dl.sourceforge.net/project/qwt/qwt/6.2.0/qwt-6.2.0.zip
"%MD5SUM%" -c qwt-6.2.0.zip.md5 || (
echo qwt-6.2.0.zip md5sum mismatch
def /f qwt-6.2.0.zip
exit /b
)


