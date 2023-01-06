@echo off
rem This file is generated from set_path1.pbat, all edits will be lost
set PATH=C:\Program Files\7-Zip;C:\Program Files (x86)\7-Zip;C:\Windows\System32

if not exist 0.0.14.zip curl -L -o 0.0.14.zip https://github.com/mugiseyebrows/event-loop/archive/refs/tags/0.0.14.zip
if not exist 0.0.14 7z x -y 0.0.14.zip


