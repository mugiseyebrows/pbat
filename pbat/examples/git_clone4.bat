@echo off
rem This file is generated from git_clone4.pbat, all edits will be lost
if not exist altdir (
git clone https://github.com/mugiseyebrows/pbat.git altdir
pushd altdir
git checkout main
popd
)


