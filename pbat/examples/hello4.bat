@echo off
rem This file is generated from hello4.pbat, all edits will be lost

python setup.py bdist_wheel

twine upload dist\app-0.0.1-py3-none-any.whl


