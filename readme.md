# About

Pbat is batch file preprocessor developed to enchance functions syntax, add macro definitions and refine control flow of batch scripts.

Pbat file (script.pbat) compiles to bat script (script.bat) and consists of function definitions (code blocks) and order of execution. Pbat must at least have one function named `main`. 

Functions introduced by `def` keyword (see `examples/hello1.pbat`). 

By default flow of execution is static which means there are no stack and each function either always jumps to specific function or always exits (conditional statement can change this flow like shortcut, yet it is still static). Next function can be defined by `then` clause in function definition (see `examples/hello2.pbat`), or by `order` statement somewhere in the file (see `examples/hello3.pbat`). 

Most important feature is macros like `download`, `unzip` or `git_clone` (see `examples/hello4.pbat` and `examples/hello5.pbat`).

You can add function to execution flow using `depends on` keyword (see `examples/hello4.pbat`). Notice that order is defined like `main fetch` but actulal order is `main tool_curl fetch` since `fetch` depens on `tool_curl`.

You can jump to begin of the function `funcname` using `goto funcname_begin` or to the end of the function using `goto funcname_end` (see `examples/hello6.pbat`). 

`%~dp0` is handy - it's directory of current script. Use [pushd](https://docs.microsoft.com/en-us/windows-server/administration/windows-commands/pushd) and `popd` instead of `cd`.

Comments starts with `#`

# Install

```cmd
python -m pip install pbat
```

# Compile scripts

```cmd
python -m pbat.compile examples
```
or
```cmd
pbat examples
```

# Watch and compile

You can use `eventloop` to trigger `pbat` on filechange

```cmd
onchange path\to\dir -i *.pbat -- pbat FILE
```

```cmd
onchange path\to\file -- pbat FILE
```