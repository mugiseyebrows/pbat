@echo off
rem This file is generated from unzip.pbat, all edits will be lost
set PATH=C:\Program Files\7-Zip;%PATH%
rem no opts
7z x -y arc.zip
rem test file.txt
if not exist file.txt 7z x -y arc.zip
rem 3 args
7z x -y arc.zip file1.txt file2.txt
rem 3 args + output foo
7z x -y -ofoo arc.zip file1.txt file2.txt