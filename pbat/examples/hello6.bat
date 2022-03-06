@echo off
rem This file is generated from hello6.pbat, all edits will be lost
if "%1" equ "test" goto test_begin
if "%1" equ "silence" goto main_end
goto not_test_begin
:main_end
exit /b

:test_begin
echo this is a test
exit /b

:not_test_begin
echo this is not a test


