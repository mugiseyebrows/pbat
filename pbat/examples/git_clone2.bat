@echo off
rem This file is generated from git_clone2.pbat, all edits will be lost
if not exist pbat (
git clone https://github.com/mugiseyebrows/pbat.git
pushd pbat
git checkout main
popd
)

