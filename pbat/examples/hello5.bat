@echo off
rem This file is generated from hello5.pbat, all edits will be lost
set PATH=C:\Program Files\Git\cmd;C:\windows;C:\windows\system32
if not exist pbat (
git clone https://github.com/mugiseyebrows/pbat.git
pushd pbat
git checkout main
popd
)


