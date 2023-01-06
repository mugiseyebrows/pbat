@echo off
rem This file is generated from if_arg1.pbat, all edits will be lost
if "%1" equ "test" goto test_begin
if "%1" equ "silence" goto silence_begin
exit /b

:test_begin
echo this is a test
exit /b

echo this is not a test
exit /b

:silence_begin


