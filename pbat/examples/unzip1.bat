@echo off
rem This file is generated from unzip1.pbat, all edits will be lost
if exist "C:\Program Files\7-Zip\7z.exe" set P7Z=C:\Program Files\7-Zip\7z.exe
if not defined P7Z (
echo P7Z not found
exit /b
)
if not exist mingw64 "%P7Z%" x -y x86_64-8.1.0-release-posix-seh-rt_v6-rev0.7z


