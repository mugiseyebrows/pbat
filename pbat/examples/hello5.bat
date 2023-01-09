@echo off
rem This file is generated from hello5.pbat, all edits will be lost
if exist "C:\Program Files\Git\cmd\git.exe" set GIT=C:\Program Files\Git\cmd\git.exe
if not defined GIT (
echo GIT not found
exit /b
)
set PATH=C:\Program Files\Git\cmd;C:\windows;C:\windows\system32
if not exist pbat (
"%GIT%" clone https://github.com/mugiseyebrows/pbat.git
pushd pbat
"%GIT%" checkout main
popd
)


