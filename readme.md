# Pbat

Pbat is batch file preprocessor developed to introduce functions, macro expressions and automate PATH variable management.

Pbat script is compiled into bat file to run localy and (optionaly) into yaml workflow to run on github workflow runner.

# Functions

Pbat script contains of function definitions. Functions introduced by `def` keyword.

#### functions1.pbat (source)
```
def main
    echo hello world
```

#### functions1.bat (generated)
```shell
@echo off
rem This file is generated from functions1.pbat, all edits will be lost
echo hello world
```


Last defined function become main entry point (main step).

#### functions2.pbat (source)
```
def foo
    echo foo

def bar
    echo bar
```

#### functions2.bat (generated)
```shell
@echo off
rem This file is generated from functions2.pbat, all edits will be lost
echo bar
```


It's likely that you need to execute multiple interdependent steps. To do this you need to add `depends on ...name` to function definition.

#### functions3.pbat (source)
```
def foo
    echo foo

def bar depends on foo
    echo bar
```

#### functions3.bat (generated)
```shell
@echo off
rem This file is generated from functions3.pbat, all edits will be lost
echo foo
echo bar
```


# Macros

Macro expressions are like function call. Macro expression consists of name and comma-separated arguments enclosed in parenthesis, strings may be enclosed into double quotes, but it's not required. Arguments can be positional and named, named arguments expressed as `:name=value` or just `:name` for boolean true value.

`use(program)` includes relative paths into PATH variable. Defined for cmake, ninja and some other tools.

`download(url, [file], [:cache])` curls specified url into local file, if `:cache` specified curl is only called if file not exist.

`add_path(path)` appends path into PATH.

`unzip(zip_path, [:test=test])` unzips zip_path using 7z, if `:test` specified 7z is only called if file not exist.

`zip(zip_path, [...path], [:test])` zips one or many paths into zip_path.

`if_exist_return(path)` exits function if path exists.

`patch(path, [:p1], [:N])` calls patch.

#### macros1.pbat (source)
```
def main
    use(cmake)
    :: download
    download(http://example.com/foo.zip)
    :: download unless exists
    download(http://example.com/bar.zip, :cache)
    :: unzip
    unzip(foo.zip)
    :: unzip unless bar exists
    unzip(bar.zip, :t=bar)
    :: unzip two files
    unzip(bar.zip, part1.txt, part2.txt)
    time /t > time.txt
    date /t > date.txt
    :: zip two files
    zip(data.zip, time.txt, date.txt)
    mkdir(foo)
    rmdir(bar)
    xcopy(src, dst)
    patch(..\patch.patch, :p1, :N)
    del(part1.txt, part2.txt)
```

#### macros1.bat (generated)
```shell
@echo off
rem This file is generated from macros1.pbat, all edits will be lost
set PATH=C:\Program Files\CMake\bin;C:\Program Files\7-Zip;%PATH%
if exist "C:\Program Files\Git\mingw32\bin\curl.exe" set CURL=C:\Program Files\Git\mingw32\bin\curl.exe
if exist "C:\Program Files\Git\mingw64\bin\curl.exe" set CURL=C:\Program Files\Git\mingw64\bin\curl.exe
if exist "C:\Windows\System32\curl.exe" set CURL=C:\Windows\System32\curl.exe
if not defined CURL (
echo CURL not found
exit /b
)
if exist "C:\Program Files\Git\usr\bin\patch.exe" set PATCH=C:\Program Files\Git\usr\bin\patch.exe
if not defined PATCH (
echo PATCH not found
exit /b
)
:: download
"%CURL%" -L -o foo.zip http://example.com/foo.zip
:: download unless exists
if not exist bar.zip "%CURL%" -L -o bar.zip http://example.com/bar.zip
:: unzip
7z x -y foo.zip
:: unzip unless bar exists
if not exist bar 7z x -y bar.zip
:: unzip two files
7z x -y bar.zip part1.txt part2.txt
time /t > time.txt
date /t > date.txt
:: zip two files
7z a -y data.zip time.txt date.txt
if not exist "foo" mkdir "foo"
rmdir /s /q bar || echo 1 > NUL
xcopy /s /e /y /i src dst
"%PATCH%" -N -p1 -i ..\patch.patch
del /f /q part1.txt part2.txt
```


There are few `github_` macros that do nothing for local script but add steps into github actions workflow.

`github_checkout()`

`github_cache(...path, :key=key)` 

`github_upload(path, [:name=name])`

`github_release(path)`

To turn on github workflow generation add `github-workflow 1` anywhere in script.

#### macros2.pbat (source)
```
def main
    github_checkout()
    time /t > time.txt
    github_upload(time.txt)
    github_release(time.txt)
    
github-workflow 1
```

#### macros2.bat (generated)
```shell
@echo off
rem This file is generated from macros2.pbat, all edits will be lost
time /t > time.txt
```

#### macros2.yml (generated)
```yaml
name: main
on: push
jobs:
  main:
    runs-on: windows-latest
    steps:
    - name: checkout
      uses: actions/checkout@v4
    - name: main
      shell: cmd
      run: time /t > time.txt
    - name: upload
      uses: actions/upload-artifact@v4
      with:
        name: time
        path: time.txt
    - name: release
      uses: softprops/action-gh-release@v1
      if: startsWith(github.ref, 'refs/tags/')
      with:
        files: time.txt

```


Lets cache build artifact time.txt using cache action on github workflow and filesystem persistance localy.

#### macros3.pbat (source)
```
def generate
    github_cache(time.txt, :k=time)
    if_exist_return(time.txt)
    time /t > time.txt

def main depends on generate
    type time.txt
    
github-workflow 1
```

#### macros3.bat (generated)
```shell
@echo off
rem This file is generated from macros3.pbat, all edits will be lost
if exist time.txt goto generate_end
time /t > time.txt
:generate_end
type time.txt
```

#### macros3.yml (generated)
```yaml
name: main
on: push
jobs:
  main:
    runs-on: windows-latest
    steps:
    - name: cache time.txt
      uses: actions/cache@v4
      with:
        path: time.txt
        key: time
    - name: generate
      shell: cmd
      run: |
        if exist time.txt goto generate_end
        time /t > time.txt
        :generate_end
    - name: main
      shell: cmd
      run: type time.txt

```


You can split code into multiple files and use `include(path)` to put it back together.

#### dep1.pbat (source)
```
def dep1
    echo dep1
```

#### dep1.bat (generated)
```shell
@echo off
rem This file is generated from dep1.pbat, all edits will be lost
echo dep1
```


#### include1.pbat (source)
```
include(dep1.pbat)

def main depends on dep1
    echo main
```

#### include1.bat (generated)
```shell
@echo off
rem This file is generated from include1.pbat, all edits will be lost
echo dep1
echo main
```


# Notes

Comments starts with `#`. Identation is optional.

# Advanced usage

With `pbat` you can build advanced readable pipelines consisting of clearly defined reusable blocks.

#### advanced1.pbat (source)
```
def install_compiler
    github_cache(C:\compiler, :k=compiler)
    add_path(C:\compiler)
    if_exist_return(C:\compiler\cl.exe)
    download(https://example.com/compiler.zip, :cache)
    unzip(compiler.zip, :o=C:\compiler, :t=C:\compiler\cl.exe)

def build_lib
    use(cmake)
    use(ninja)
    git_clone(https://example.com/lib.git)
    pushd lib
        cmake -D CMAKE_INSTALL_PREFIX=C:/example ..
        cmake --build .
        cmake --install .
    popd

def build_app depends on install_compiler and build_lib
    github_checkout()
    mkdir(build)
    pushd build
        cmake -D CMAKE_PREFIX_PATH=C:/example ..
        cmake --build .
    popd
    zip(app.zip, build\app.exe, C:\example\bin\example.dll)
    github_upload(app.zip)
    github_release(app.zip)

github-workflow 1
```

#### advanced1.bat (generated)
```shell
@echo off
rem This file is generated from advanced1.pbat, all edits will be lost
set PATH=C:\compiler;C:\Program Files\7-Zip;C:\Program Files\CMake\bin;C:\Program Files\Meson;C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja;C:\Program Files (x86)\Android\android-sdk\cmake\3.22.1\bin;C:\Program Files\Git\cmd;%PATH%
if exist "C:\Program Files\Git\mingw32\bin\curl.exe" set CURL=C:\Program Files\Git\mingw32\bin\curl.exe
if exist "C:\Program Files\Git\mingw64\bin\curl.exe" set CURL=C:\Program Files\Git\mingw64\bin\curl.exe
if exist "C:\Windows\System32\curl.exe" set CURL=C:\Windows\System32\curl.exe
if not defined CURL (
echo CURL not found
exit /b
)
if exist C:\compiler\cl.exe goto install_compiler_end
if not exist compiler.zip "%CURL%" -L -o compiler.zip https://example.com/compiler.zip
if not exist C:\compiler\cl.exe 7z x -y -oC:\compiler compiler.zip
:install_compiler_end
if not exist lib git clone https://example.com/lib.git
pushd lib
    cmake -D CMAKE_INSTALL_PREFIX=C:/example ..
    cmake --build .
    cmake --install .
popd
if not exist "build" mkdir "build"
pushd build
    cmake -D CMAKE_PREFIX_PATH=C:/example ..
    cmake --build .
popd
7z a -y app.zip build\app.exe C:\example\bin\example.dll
```

#### advanced1.yml (generated)
```yaml
name: main
on: push
jobs:
  main:
    runs-on: windows-latest
    steps:
    - name: checkout
      uses: actions/checkout@v4
    - name: cache C:\compiler
      uses: actions/cache@v4
      with:
        path: C:\compiler
        key: compiler
    - name: install_compiler
      shell: cmd
      run: |
        set PATH=C:\compiler;C:\Program Files\7-Zip;C:\Program Files\CMake\bin;C:\Program Files\Meson;C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja;C:\Program Files (x86)\Android\android-sdk\cmake\3.22.1\bin;C:\Program Files\Git\cmd;%PATH%
        if exist C:\compiler\cl.exe goto install_compiler_end
        if not exist compiler.zip curl -L -o compiler.zip https://example.com/compiler.zip
        if not exist C:\compiler\cl.exe 7z x -y -oC:\compiler compiler.zip
        :install_compiler_end
    - name: build_lib
      shell: cmd
      run: |
        set PATH=C:\compiler;C:\Program Files\7-Zip;C:\Program Files\CMake\bin;C:\Program Files\Meson;C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja;C:\Program Files (x86)\Android\android-sdk\cmake\3.22.1\bin;C:\Program Files\Git\cmd;%PATH%
        if not exist lib git clone https://example.com/lib.git
        pushd lib
            cmake -D CMAKE_INSTALL_PREFIX=C:/example ..
            cmake --build .
            cmake --install .
        popd
    - name: build_app
      shell: cmd
      run: |
        set PATH=C:\compiler;C:\Program Files\7-Zip;C:\Program Files\CMake\bin;C:\Program Files\Meson;C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja;C:\Program Files (x86)\Android\android-sdk\cmake\3.22.1\bin;C:\Program Files\Git\cmd;%PATH%
        if not exist "build" mkdir "build"
        pushd build
            cmake -D CMAKE_PREFIX_PATH=C:/example ..
            cmake --build .
        popd
        7z a -y app.zip build\app.exe C:\example\bin\example.dll
    - name: upload
      uses: actions/upload-artifact@v4
      with:
        name: app
        path: app.zip
    - name: release
      uses: softprops/action-gh-release@v1
      if: startsWith(github.ref, 'refs/tags/')
      with:
        files: app.zip

```


# Run

## Compile scripts

```cmd
python -m pbat.compile path/to/file
```
or
```cmd
pbat path/to/file
```

## Watch and compile

You can use `eventloop` to trigger `pbat` on filechange

```cmd
onchange path\to\dir -i *.pbat -- pbat FILE
```

```cmd
onchange path\to\file -- pbat FILE
```

# More examples 

[antlr4-cpp-demo/build.pbat](https://github.com/mugiseyebrows/antlr4-cpp-demo/blob/main/build.pbat)