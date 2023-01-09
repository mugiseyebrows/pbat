@echo off
rem This file is generated from git_clone1.pbat, all edits will be lost
if exist "C:\Program Files\Git\cmd\git.exe" set GIT=C:\Program Files\Git\cmd\git.exe
if not defined GIT (
echo GIT not found
exit /b
)
if not exist pbat (
"%GIT%" clone https://github.com/mugiseyebrows/pbat.git
pushd pbat
"%GIT%" checkout main
popd
)


