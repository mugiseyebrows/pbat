from dataclasses import dataclass, field
import os
import re
import random
import textwrap
import yaml

# todo shell python bash pwsh

try:
    from .parsemacro import parse_macro, ParseMacroError
    from .parsedef import parse_def
except ImportError:
    from parsemacro import parse_macro, ParseMacroError
    from parsedef import parse_def

WARNING = 'This file is generated from {}, all edits will be lost'

ON_PUSH = 1
ON_TAG = 2
ON_RELEASE = 3
WINDOWS_2019 = "windows-2019"
WINDOWS_2022 = "windows-2022"
WINDOWS_LATEST = "windows-latest"
CHECKSUM_ALGS = ['b2','md5','sha1','sha224','sha256','sha384','sha512']

@dataclass
class Opts:
    debug: bool = False
    clean: bool = False
    curl_in_path: bool = False
    curl_user_agent: str = None
    curl_proxy: str = None
    download_test: bool = True
    unzip_test: bool = True
    zip_test: bool = True
    github: bool = False
    zip_in_path = False
    git_in_path = False
    tar_in_path = False
    patch_in_path = False
    github_workflow = False
    github_image: str = WINDOWS_LATEST
    github_on: int = ON_PUSH
    msys2_msystem: str = None

@dataclass
class GithubUpload:
    name: str = None
    path: list = field(default_factory=list)

@dataclass
class GithubSetupNode:
    node_version: int = None

@dataclass
class GithubSetupMsys2:
    msystem: str = None
    install: str = None
    update: bool = True

(
    SHELL_CMD,
    SHELL_MSYS2,
) = range(2)

@dataclass
class GithubShellStep:
    run: str = None
    shell: str = "cmd"
    name: str = None

@dataclass
class GithubMatrix:
    matrix: dict = field(default_factory=dict)
    include: list = field(default_factory=list)
    exclude: list = field(default_factory=list)

@dataclass
class GithubData:
    checkout: bool = False
    release: list = field(default_factory=list)
    upload: GithubUpload = None
    matrix: GithubMatrix = field(default_factory=GithubMatrix)
    setup_msys2: GithubSetupMsys2 = None
    setup_node: GithubSetupNode = None
    steps: list = field(default_factory=list)

@dataclass
class Ctx:
    github: bool
    shell: str

MACRO_NAMES = [
    'pushd_cd', 'popd_cd', 
    'find_app',
    'download', 
    'zip', 'unzip',
    'set_path', 
    'foreach',
    'copy_file', 'copy_dir', 'mkdir', 'rmdir', 'move_file',
    'git_clone', 'git_pull', 'patch', 
    'github_matrix', 'github_matrix_include', 'github_matrix_exclude', 
    'github_checkout', 'github_upload', 'github_release', 
    'github_setup_msys2', 'github_setup_node',
    'untar',
    'if_arg', 
    'log', 
    'where',
    'clean_dir', 'clean_file', 
    'set_var',
    'substr', 
    'use_tool', 'install_tool', 'call_vcvars'
]

def get_dst_bat(src):
    dirname = os.path.dirname(src)
    basename = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(dirname, basename + '.bat')

def get_dst_workflow(src):
    dirname = os.path.dirname(src)
    basename = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(dirname, ".github", "workflows", basename + '.yml')

class folded_str(str): pass
class literal_str(str): pass
def folded_str_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='>')
def literal_str_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
yaml.add_representer(folded_str, folded_str_representer)
yaml.add_representer(literal_str, literal_str_representer)

def str_or_literal(items):
    if len(items) == 1:
        return items[0]
    return literal_str("\n".join(items) + "\n")

def make_release_step(artifacts):
    return {
        "name": "release",
        "uses": "softprops/action-gh-release@v1",
        "if": "startsWith(github.ref, 'refs/tags/')",
        "with": {
            "files": str_or_literal(artifacts)
        }
    }

def make_upload_step(data: GithubUpload):
    return {
        "name": "upload",
        "uses": "actions/upload-artifact@v3",
        "with": {
            "name": data.name,
            "path": str_or_literal(data.path)
        }
    }

def save_workflow(path, steps, opts: Opts, githubdata: GithubData):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    on = opts.github_on
    if on == ON_TAG:
        on_ = {"push":{"tags":"*"}}
    elif on == ON_PUSH:
        on_ = "push"
    elif on == ON_RELEASE:
        on_ = {"release": {"types": ["created"]}}

    main = {"runs-on":opts.github_image}

    matrix = githubdata.matrix.matrix
    include = githubdata.matrix.include
    exclude = githubdata.matrix.exclude

    if len(matrix) > 0 or len(include) > 0:
        strategy = {"matrix": matrix, "fail-fast": False}
        if len(include) > 0:
            strategy["matrix"]["include"] = include
        if len(exclude) > 0:
            strategy["matrix"]["exclude"] = exclude
        main["strategy"] = strategy

    main['steps'] = steps

    data = {"name":"main","on":on_}

    if opts.msys2_msystem:
        data["env"] = {
            "MSYSTEM": opts.msys2_msystem,
            "CHERE_INVOKING": 'yes'
        }

    data["jobs"] = {"main": main}

    with open(path, 'w', encoding='utf-8') as f:
        f.write(yaml.dump(data, None, Dumper=Dumper, sort_keys=False))

def make_setup_msys2_step(data: GithubSetupMsys2, opts: Opts):
    if data.msystem:
        msystem = data.msystem
    elif opts.msys2_msystem:
        msystem = opts.msys2_msystem
    else:
        msystem = 'MINGW64'

    obj = {
        "name": "setup-msys2",
        "uses": "msys2/setup-msys2@v2",
        "with": {
            "msystem": msystem,
        }
    }
    if data.install:
        obj["with"]["install"] = data.install
    if data.update is not None:
        obj["with"]["update"] = data.update
    return obj

def make_setup_node_step(data: GithubSetupNode):
    obj = {
        "uses": "actions/setup-node@v3",
        "with": {"node-version": data.node_version}
    }
    return obj

def make_github_step(step: GithubShellStep, opts: Opts, githubdata: GithubData):

    obj = dict()

    if step.name:
        obj["name"] = step.name

    shell = step.shell
    if isinstance(shell, int):
        shell = {SHELL_CMD: "cmd", SHELL_MSYS2: "msys2 {0}"}[step.shell]

    if shell == "msys2":
        if githubdata.setup_msys2:
            shell = "msys2 {0}"
        else:
            print("warning: you might forgot to add github_setup_msys2() to script")
            shell = "C:\\msys64\\usr\\bin\\bash.exe {0}"
    
    if shell == "node":
        if githubdata.setup_node is None:
            print("warning: you might forgot to add github_setup_node() to script")
        shell = "node {0}"

    obj["shell"] = shell
    
    if opts.msys2_msystem:
        pass

    if shell == "msys2":
        if opts.msys2_msystem is None:
            obj["env"] = {"MSYSTEM": opts.msys2_msystem, "CHERE_INVOKING": 'yes'}
    
    obj["run"] = str_or_literal(step.run.split("\n"))

    return obj

def count_parenthesis(line):
    op = 0
    cl = 0
    is_str = False
    for c in line:
        if c == '"':
            is_str = not is_str
        elif c == '(' and not is_str:
            op += 1
        elif c == ')' and not is_str:
            cl += 1
    return op, cl

def read(src, github):

    def_line = dict()

    defs = dict()

    deps = dict()

    thens = dict()

    shells = dict()

    opts = Opts()

    lines = []

    def pattern_join(*args):
        return "".join(args)

    def process_line(line, cwd):

        PBAT_FILE = "([0-9a-z_]+[.]pbat)"
        SPACE = "\\s*"
        START = "^\\s*"

        m = re.match(pattern_join(START, 'include', SPACE, '\\(', SPACE, PBAT_FILE, SPACE, '\\)'), line)
        if m:
            path = os.path.join(cwd, m.group(1))
            with open(path, encoding='utf-8') as f_:
                for line in f_.readlines():
                    lines.append(line)
        else:
            lines.append(line)

    if isinstance(src, str):
        cwd = os.path.dirname(src)
        with open(src, encoding='utf-8') as f:
            for i, line in enumerate(f):
                process_line(line, cwd)
    else:
        # StringIO
        cwd = os.getcwd()
        for line in src:
            process_line(line, cwd)

    has_main = False
    for line in lines:
        if re.match('^def main', line):
            has_main = True
            break
    if not has_main:
        lines = ['def main\n'] + lines

    lines_ = []

    skip = set()

    def unsplit_line(lines, i, skip: set):
        tot = 0
        res = []
        for i in range(i, len(lines)):
            skip.add(i)
            line = lines[i]
            res.append(line)
            op, cl = count_parenthesis(line)
            tot += (op - cl)
            if tot == 0:
                break
        return " ".join(res) + "\n"

    used = set()
    chksum_used = set()

    # unsplit
    for i, line in enumerate(lines):
        if i in skip:
            continue

        ID = "([0-9a-z_]+)"
        SPACE = "\\s*"
        START = "^\\s*"

        m1 = re.match(SPACE.join([START,ID,"=",ID]), line)
        m2 = re.match(START + ID, line)
        if (m1 and m1.group(2) in MACRO_NAMES) or (m2 and m2.group(1) in MACRO_NAMES):
            line = unsplit_line(lines, i, skip)
            lines_.append(line)
            if m1:
                name = m1.group(2)
            if m2:
                name = m2.group(1)
            used.add(name)
            if name == 'download':
                m = re.search(':({})\\s*='.format("|".join(CHECKSUM_ALGS)), line)
                if m:
                    alg = m.group(1)
                    chksum_used.add(alg)
        else:
            lines_.append(line)

    t = 1

    lines = lines_
    #print(lines)

    name = None
    for i, line in enumerate(lines):
        #line = line.strip()
        m = re.match('^\\s*(debug|clean|download_test|unzip_test|zip_test|github|github_workflow)\\s+(off|on|true|false|1|0)\\s*$', line)
        if m is not None:
            setattr(opts, m.group(1), m.group(2) in ['on','true','1'])
            continue

        m = re.match('^\\s*([a-z0-9_]+_in_path)\\s+(off|on|true|false|1|0)\\s*$', line, re.IGNORECASE)
        if m:
            name = m.group(1)
            if hasattr(opts, name):
                setattr(opts, name, m.group(2) in ['on','true','1'])
                continue
        
        ID = "([0-9a-z_]+)"
        SPACE = "\\s*"
        START = "^\\s*"
        END = "\\s*$"

        m = re.match(pattern_join(START, 'msys2[_-]msystem', SPACE, ID, END), line, re.IGNORECASE)
        if m:
            opts.msys2_msystem = m.group(1).strip()
            continue

        m = re.match('^\\s*github[-_]image\\s+(.*)$', line)
        if m:
            opts.github_image = m.group(1).strip()
            continue

        m = re.match('^\\s*github[-_]on\\s+(.*)$', line)
        if m:
            trigger = m.group(1).strip()
            opts.github_on = {
                "push": ON_PUSH,
                "release": ON_RELEASE,
                "tag": ON_TAG
            }[trigger]
            continue

        m = re.match('^curl_user_agent\\s+(safari|chrome|mozilla)$', line)
        if m is not None:
            opts.curl_user_agent = m.group(1)
            continue
        m = re.search('^curl_proxy\\s+(.*)$', line)
        if m is not None:
            opts.curl_proxy = m.group(1).rstrip()
            continue
        
        ID = "([0-9a-z_]+)"
        IDS = "([0-9a-z_ ]*)"
        SPACE = "\\s*"
        START = "^\\s*"
        END = "\\s*$"

        m = re.match(pattern_join(START, 'def', SPACE, ID, SPACE, IDS, END), line)
        if m is not None:

            name, then, deps_, shell = parse_def(line)
            #print("name {} then {} deps_ {} shell {}".format(name, then, deps_, shell))

            deps_ = []
            if shell is None:
                shell = 'cmd'

            deps[name] = deps_
            if then is not None:
                thens[name] = then
            shells[name] = shell

            if name in defs:
                print("redefinition {} on line {}, first defined on line {}".format(name, i+1, def_line[name]))
            def_line[name] = i
            defs[name] = []

            #print("line {} def {} depends on {} then {} shell {}".format(i, name, deps_, then, shell))
            
            continue
        
        # todo calculate order after parse
        m = re.match('^\\s*order\\s+(.*)$', line)
        if m is not None:
            names = re.split('\\s+', m.group(1))
            
            names_ = insert_deps(names, deps)
            for n1, n2 in zip(names_, names_[1:]):
                thens[n1] = n2
            continue
        if line == '':
            continue
        if re.match("^\\s*#", line):
            continue

        if name is not None:
            defs[name].append(line + "\n")

    for n1, n2 in thens.items():
        if n1 not in defs:
            if n1 != "end":
                print("missing def {}".format(n1))
        if n2 not in defs:
            if n2 != "end":
                print("missing def {}".format(n2))
    
    if 'download' in used and not opts.curl_in_path:
        defs['main'] = ['CURL = find_app([C:\\Windows\\System32\\curl.exe, C:\\Program Files\\Git\\mingw64\\bin\\curl.exe, C:\\Program Files\\Git\\mingw32\\bin\\curl.exe])\n'] + defs['main']
    if ('zip' in used or 'unzip' in used) and not opts.zip_in_path:
        defs['main'] = ['P7Z = find_app([C:\\Program Files\\7-Zip\\7z.exe])\n'] + defs['main']
    if 'git_clone' in used and not opts.git_in_path:
        defs['main'] = ['GIT = find_app([C:\\Program Files\\Git\\cmd\\git.exe])\n'] + defs['main']
    if 'patch' in used and not opts.patch_in_path:
        defs['main'] = ['PATCH = find_app([C:\\Program Files\\Git\\usr\\bin\\patch.exe])\n'] + defs['main']
    if 'untar' in used and not opts.tar_in_path:
        defs['main'] = ['TAR = find_app([C:\\Program Files\\Git\\usr\\bin\\tar.exe])\n'] + defs['main']
        defs['main'] = ['GZIP = find_app([C:\\Program Files\\Git\\usr\\bin\\gzip.exe])\n'] + defs['main']

    if 'msys2' in shells.values():
        if github:
            pass
        else:
            defs['main'] = [
                'MSYS2 = find_app([C:\\msys64\\usr\\bin\\bash.exe])\n',
                'set_var(CHERE_INVOKING, yes)\n'
            ] + defs['main']
    if 'python' in shells.values():
        if github:
            pass
        else:
            defs['main'] = ["""PYTHON = find_app([
    %LOCALAPPDATA%\\Programs\\Python\\Python39\\python.exe,
    C:\\Python39\\python.exe,
    %LOCALAPPDATA%\\Programs\\Python\\Python310\\python.exe,
    C:\\Python310\\python.exe,
    %LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe,
    C:\\Python311\\python.exe,
    C:\\Miniconda3\\python.exe,
    %USERPROFILE%\\Miniconda3\\python.exe,
    C:\\Anaconda3\\python.exe,
    %USERPROFILE%\\Anaconda3\\python.exe
])
"""] + defs['main']

    if 'pwsh' in shells.values():
        if github:
            pass
        else:
            defs['main'] = ["PWSH = find_app([C:\\Program Files\\PowerShell\\7\\pwsh.exe])\n"] + defs['main']

    if 'node' in shells.values():
        if github:
            pass
        else:
            defs['main'] = ["NODE = find_app([C:\\Program Files\\nodejs\\node.exe])\n"] + defs['main']

    for alg in chksum_used:
        exe = alg + 'sum.exe'
        var = (alg + 'sum').upper()
        defs['main'] = ['{} = find_app([C:\\Program Files\\Git\\usr\\bin\\{}])\n'.format(var, exe)] + defs['main']
    
    return defs, thens, shells, opts

def insert_deps(names, deps):
    res = []
    for n in names:
        if n in deps:
            n_deps = deps[n]
            for d in n_deps:
                if d not in res:
                    res.append(d)
        res.append(n)

    #print('before insert:', names)
    #print('after insert:', res)
    return res

def find_app(name, items, label):
    label_success = "{}_find_app_found".format(name)
    tests = ["if exist \"{}\" goto {}\n".format(item, label_success) for item in items]
    puts = ["if exist \"{}\" set PATH={};%PATH%\n".format(item, os.path.dirname(item)) for item in items]
    return "".join(tests) + "goto {}_begin\n".format(label) + ":" + label_success + "\n" + "".join(puts)

def without(vs, v):
    return [e for e in vs if e != v]


def render_one(name, defs, thens, opts: Opts, src_name, echo_off=True, warning=True):
    res = []
    if not opts.debug and echo_off:
        res = res + ['@echo off\n']

    if warning:
        res += ['rem {}\n'.format(WARNING.format(src_name))]

    if 'main' not in defs:
        print("main not defined")
        return ""

    keys = [ name ]

    for name in keys:
        lines = defs[name]
        #res.append("rem def {}\n".format(name))
        res.append(":{}_begin\n".format(name))
        if opts.debug:
            res.append("echo {}\n".format(name))
            res.append(macro_log(name, [name]))
        res.append("".join(lines))
        res.append(":{}_end\n".format(name))
        #res.append("goto {}\n".format(thens[name] + "_begin" if name in thens and thens[name] not in ["end","exit"] else "end"))
        res.append("\n")

    while(True):
        ok1 = remove_unused_labels(res)
        ok2 = remove_redundant_gotos(res)
        if not ok1 and not ok2:
            break

    return "".join(res)

def dedent(text):
    def d(line):
        if line.startswith('    '):
            line = line[4:]
        return line
    return "\n".join([d(line) for line in text.split('\n') if line.strip() != ''])

def render_local_main(defs, thens, shells, opts: Opts, src_name, echo_off=True, warning=True):
    res = []

    files = []

    if not opts.debug and echo_off:
        res = res + ['@echo off\n']

    if warning:
        res += ['rem This file is generated from {}, all edits will be lost\n'.format(src_name)]

    if 'main' not in defs:
        print("main not defined")
        return ""

    keys = ['main'] + without(defs.keys(), 'main')

    if not opts.clean:
        keys = without(keys, 'clean')

    for name in keys:
        lines = defs[name]
        #res.append("rem def {}\n".format(name))
        res.append(":{}_begin\n".format(name))
        if opts.debug:
            res.append("echo {}\n".format(name))
            res.append(macro_log(name, [name]))
        shell = shells[name]
        if shell == 'cmd':
            res.append("".join(lines))
        elif shell in ['msys2', 'python', 'pwsh', 'node']:

            file_content = ''
            comment = "# "
            if shell == 'msys2':
                ext = '.sh'
                file_content = "#!/bin/bash\n"
            elif shell == 'python':
                ext = '.py'
            elif shell == 'pwsh':
                ext = '.ps1'
            elif shell == 'node':
                ext = '.js'
                comment = '// '
                
            if warning:
                file_content += comment + WARNING.format(src_name) + "\n"

            file_content += "".join(lines) + "\n"

            #file_content = dedent(file_content)
            
            file_name = "{}-{}{}".format(os.path.splitext(src_name)[0], name, ext)

            if shell == 'msys2':
                res.append('"%MSYS2%" %~dp0{}\n'.format(file_name))
            elif shell == 'python':
                res.append('"%PYTHON%" %~dp0{}\n'.format(file_name))
            elif shell == 'pwsh':
                res.append('"%PWSH%" %~dp0{}\n'.format(file_name))
            elif shell == 'node':
                res.append('"%NODE%" %~dp0{}\n'.format(file_name))
            
            files.append((file_name, file_content))

            #print(files)

            if opts.msys2_msystem:
                res.append("set MSYSTEM={}\n".format(opts.msys2_msystem))

        else:
            raise Exception('unknown shell {}'.format(shells[name]))

        res.append(":{}_end\n".format(name))
        res.append("goto {}\n".format(thens[name] + "_begin" if name in thens and thens[name] not in ["end","exit"] else "end"))
        res.append("\n")

    while(True):
        ok1 = remove_unused_labels(res)
        ok2 = remove_redundant_gotos(res)
        if not ok1 and not ok2:
            break

    return "".join(res), files

def remove_unused_labels(res):
    #print('remove_unused_labels')
    changed = False
    gotos = []
    goto_rx = re.compile('goto\\s*([0-9a-z_]+)', re.IGNORECASE)
    label_rx = re.compile('^:([0-9a-z_]+)', re.IGNORECASE)
    call_rx = re.compile('call\\s*:([0-9a-z_]+)', re.IGNORECASE)

    for line in res:
        for m in goto_rx.findall(line):
            gotos.append(m)
        for m in call_rx.findall(line):
            gotos.append(m)

    for i, line in enumerate(res):
        m = label_rx.match(line)
        if m:
            if m.group(1) not in gotos:
                res[i] = ""
                changed = True
    return changed

def remove_redundant_gotos(res):
    #print('remove_redundant_gotos')
    goto_rx = re.compile('goto ([0-9a-z_]+)', re.IGNORECASE)
    label_rx = re.compile('^:([0-9a-z_]+)', re.IGNORECASE)
    changed = False
    ixs = [i for i, line in enumerate(res) if goto_rx.match(line)]
    for i in ixs:
        goto = goto_rx.match(res[i]).group(1)
        if goto == 'end':
            res[i] = "exit /b\n"
            changed = True
            continue
        for j in range(i+1, len(res)):
            line = res[j]
            if line.strip() == "":
                continue
            m = label_rx.match(line)
            if m:
                label = m.group(1)
                if label == goto:
                    res[i] = ""
                    changed = True
            break

    # trim extra exits at the end of the file
    for i in reversed(range(len(res))):
        line = res[i].strip()
        if line == "exit /b":
            res[i] = ""
            changed = True
        elif line == "":
            pass
        else:
            #print(i, line)
            break

    return changed

def validate_args(fnname, args, kwargs, ret, argmin = None, argmax = None, kwnames = None, needret = False):

    argmin_ = argmin is not None and argmin > -1
    argmax_ = argmax is not None and argmax > -1

    if argmin_ and argmax_:
        if not (argmin <= len(args) <= argmax):
            if argmin == argmax:
                nargs = str(argmin)
            else:
                nargs = "{} to {}".format(argmin, argmax)
            raise Exception("{} expects {} args, got {}: {}".format(fnname, nargs, len(args), str(args)))
    elif argmin_:
        if len(args) < argmin:
            nargs = "{} or more".format(argmin)
            raise Exception("{} expects {} args, got {}: {}".format(fnname, nargs, len(args), str(args)))
    elif argmax_:
        if len(args) > argmax:
            nargs = "{} or less".format(argmin)
            raise Exception("{} expects {} args, got {}: {}".format(fnname, nargs, len(args), str(args)))

    if kwnames is not None:
        for n in kwargs:
            if n not in kwnames:
                raise Exception("{} unknown option {}".format(fnname, n))
    if needret and ret is None:
        raise Exception("{} must be assigned to env variable".format(fnname))

def macro_find_app(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    
    validate_args("find_app", args, kwargs, ret, 1, 1, {"g", "goto", "c", "cmd"}, True)

    err_goto = kwarg_value(kwargs, 'goto', 'g')
    err_cmd = kwarg_value(kwargs, 'cmd', 'c')

    if err_goto:
        error = 'goto {}_begin'.format(err_goto)
    elif err_cmd:
        error = err_cmd
    else:
        error = """(
echo {} not found
exit /b
)""".format(ret)

    env_name = ret
    items = args[0]
    if len(args) > 1:
        raise ValueError("find_app requires one positional argument")
        
    tests = ["if exist \"{}\" set {}={}\n".format(item, env_name, item) for i,item in enumerate(reversed(items))]
    tests = tests + ['if not defined {} {}\n'.format(env_name, error)]
    return "".join(tests)

def macro_find_file(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    items = args[0]
    label = args[1]
    label_success = "{}_find_file_found".format(name)
    tests = ["if exist \"{}\" goto {}\n".format(item, label_success) for item in items]
    puts = []
    return "".join(tests) + "goto {}_begin\n".format(label) + ":" + label_success + "\n" + "".join(puts)

def quoted(s):
    if ' ' in s or '%' in s:
        return '"' + s + '"'
    return s

def escape_url(s):
    return quoted("".join(["^" + c if c == '%' else c for c in s]))

def macro_download(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    url = args[0]
    dest = args[1]

    shell = ctx.shell

    force = kwargs.get('force')
    keep = kwargs.get('keep')
    if opts.curl_in_path or shell =='msys2':
        curl = "curl"
    else:
        curl = '"%CURL%"'

    user_agent = ""
    if opts.curl_user_agent is not None:
        user_agent = '--user-agent "' + {
            'mozilla': 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0',
            'safari': 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'chrome': 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        }[opts.curl_user_agent] + '"'

    proxy = ''
    if opts.curl_proxy is not None:
        proxy = '-x {}'.format(opts.curl_proxy)

    #print("user_agent", user_agent)

    is_wget = False
    is_curl = True

    def spacejoin_nonempty(*vs):
        return " ".join([v for v in vs if v != ""])

    if kwarg_value(kwargs, 'k', 'insecure'):
        insecure = '-k'
    else:
        insecure = ''

    if is_curl:
        cmd = spacejoin_nonempty(curl, '-L', proxy, user_agent, insecure, '-o', quoted(dest), quoted(url)) + "\n"
    elif is_wget:
        wget = "C:\\msys64\\usr\\bin\\wget.exe"
        cmd = " ".join([wget, '-O', quoted(dest), quoted(url)]) + "\n"

    if force or opts.download_test == False or ctx.github:
        exp = cmd
    else:
        if shell == 'cmd':
            exp = "if not exist {} {}\n".format(quoted(dest), cmd)
        elif shell == 'msys2':
            exp = "if [ ! -f {} ]; then {}; fi\n".format(quoted(dest), cmd)
        else:
            raise Exception("download not implemented for shell {}".format(shell))

    if keep:
        clean_exp = ""
    else:
        #clean_exp = macro_clean_file(None, [dest], {}, None, opts)
        # todo optiona clean
        clean_exp = ''

    sum_file = None
    sum_alg = None

    for n in CHECKSUM_ALGS:
        if n in kwargs:
            sum_file = kwargs[n]
            sum_alg = n

    if sum_file:
        sum_var = (sum_alg + 'sum').upper()
        exp = exp + """"%{}%" -c {} || (
echo {} {}sum mismatch
def /f {}
exit /b
)
""".format(sum_var, quoted(sum_file), quoted(dest), sum_alg, quoted(dest))

    return exp, clean_exp

def kwarg_value(kwargs, *names):
    for name in names:
        value = kwargs.get(name)
        if value is not None:
            return value


def macro_unzip(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):

    src = args[0]
    force = kwargs.get('force')
    keep = kwargs.get('keep')
    output = kwarg_value(kwargs, 'output', 'o')

    if len(args) > 1:
        test = args[1]
    else:
        test = None

    if opts.zip_in_path:
        cmd = ['7z']
    else:
        cmd = ['"%P7Z%"']

    cmd = cmd + ['x', '-y']
    if output:
        cmd.append("-o{}".format(quoted(output)))
    cmd.append(quoted(src))
    exp = " ".join(cmd) + "\n"

    if force or opts.unzip_test == False:
        pass
    elif test:
        exp = "if not exist {} ".format(quoted(test)) + exp
    else:
        pass

    if keep:
        clean_exp = ""
    else:
        #print(os.path.splitext(src)[1])
        # todo optional clean
        clean_exp = ""
    return exp, clean_exp


def macro_untar(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    #print(args)
    shell = ctx.shell
    src = args[0]
    if len(args) > 1:
        test = args[1]
    else:
        test = None

    if shell == 'cmd':
        if opts.tar_in_path:
            cmds = ['tar -xf {}'.format(quoted(src))]
            if test:
                return if_group("not exist {}".format(quoted(test)), cmds)
            return "\n".join(cmds) + "\n"
        else:
            ext = os.path.splitext(src)[1]
            if ext == '.gz':
                cmds = [
                    '"%GZIP%" -k -d {}'.format(src), 
                    '"%TAR%" -xf {}'.format(os.path.splitext(src)[0])
                ]
                if test:
                    return if_group("exist {}".format(quoted(test)), cmds)
                else:
                    return "\n".join(cmds) + "\n"
            else:
                raise Exception("untar not implemented for ext {}".format(ext))
    elif shell == 'msys2':
        cmd = 'tar -xf {}'.format(quoted(src))
        if test:
            exp = "if [ ! -f {} ]; then {}; fi\n".format(quoted(src), cmd)
        else:
            exp = cmd
        return exp
    else:
        raise Exception("untar not implemented for shell {}".format(shell))

    return exp

def macro_zip(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):

    COMPRESSION_MODE = {
        "-mx0": "copy",
        "-mx1": "fastest",
        "-mx3": "fast",
        "-mx5": "normal",
        "-mx7": "maximum",
        "-mx9": "ultra"
    }
    kwnames = list(COMPRESSION_MODE.values()) + ["lzma"]

    validate_args("zip", args, kwargs, ret, 2, 2, kwnames, False)

    src, dst = args
    if opts.zip_in_path:
        zip = '7z'
    else:
        zip = '"%P7Z%"'

    if opts.zip_in_path:
        cmd = '7z'
    else:
        cmd = '"%P7Z%"'
    #cmd = cmd + ' a -y {} {}\n'.format(quoted(dst), quoted(src))
    flags = ['-y']
    if kwarg_value(kwargs, "lzma"):
        flags.append('-m0=lzma2')
    for flag, mode in COMPRESSION_MODE.items():
        if kwarg_value(kwargs, mode):
            flags.append(flag)
            break

    test = []
    if opts.zip_test:
        test = ['if not exist', quoted(dst)]

    cmd = test + [zip, 'a'] + flags + [quoted(dst), quoted(src)]

    return " ".join(cmd) + "\n"

def macro_patch(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("patch", args, kwargs, ret, 1, 1, {"N", "forward", "p", "strip"})
    if opts.patch_in_path:
        patch = "patch"
    else:
        patch = '"%PATCH%"'

    cmd = [patch]
    if kwarg_value(kwargs, 'N', "forward"):
        cmd.append('-N')
    p = kwarg_value(kwargs, "p", "strip")
    if p:
        cmd.append('-p{}'.format(p))

    cmd = cmd + ["-i", quoted(args[0])]

    return " ".join(cmd) + "\n"
    
def macro_mkdir(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    arg = args[0]
    return "if not exist \"{}\" mkdir \"{}\"\n".format(arg, arg)

def macro_log(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    arg = args[0]
    return "echo %DATE% %TIME% {} >> %~dp0log.txt\n".format(arg)

def macro_clean_dir(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    arg = args[0]
    if ctx.shell == 'cmd':
        return "rmdir /s /q {}\n".format(quoted(arg))
    elif ctx.shell == 'msys2':
        return "rm -rf {}\n".format(quoted(arg))
    else:
        raise Exception("rmdir not implemented for shell {}".format(ctx.shell))

def macro_rmdir(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    return macro_clean_dir(name, args, opts)

def macro_clean_file(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    arg = args[0]
    return "del /q \"{}\"\n".format(arg)

def if_group(cond, cmds):
    if len(cmds) == 1:
        return "if {} {}\n".format(cond, cmds[0])
    return """if {} (
    {}
)
""".format(cond, "\n    ".join(cmds))

def macro_git_clone(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    url = args[0]
    if len(args) > 1:
        dir = args[1]
    else:
        dir = None

    branch = kwarg_value(kwargs, 'b', 'branch', 'ref')
    
    basename = os.path.splitext(os.path.basename(url))[0]
    if dir:
        basename = dir

    if opts.git_in_path:
        git = 'git'
    else:
        git = '"%GIT%"'

    clone = [git, 'clone', url]
    if dir:
        clone.append(dir)
    clone = " ".join(clone)

    cond = "not exist {}".format(quoted(basename))

    if branch:
        checkout = " ".join([git, 'checkout', branch])
        cmds = [clone, "pushd {}".format(basename), "    " + checkout, "popd"]
    else:
        cmds = [clone]

    cmd = if_group(cond, cmds)
    if kwargs.get('pull'):
        cmd = cmd + """pushd {}
    {} pull
popd
""".format(basename, git)

    return cmd

def macro_git_pull(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    base = args[0]
    return textwrap.dedent("""\
    pushd {}
    git pull
    popd
    """).format(base)

def macro_set_path(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    """
    if ctx.github:
        return "echo PATH={}>> %GITHUB_ENV%\n".format(";".join(args))
    """
    return "set PATH=" + ";".join(args) + "\n"

def macro_set_var(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    n, v = args
    res = []
    if ctx.shell == 'cmd':
        res.append("set {}={}\n".format(n,v))
        if ctx.github:
            res.append("echo {}={}>> %GITHUB_ENV%\n".format(n,v))
    elif ctx.shell == 'msys2':
        res.append("export {}={}\n".format(n,v))
        if ctx.github:
            res.append("echo {}={}>> $GITHUB_ENV%\n".format(n,v))
    else:
        raise Exception("set_var not implemented for shell {}".format(ctx.shell))
    return "".join(res)

def macro_copy_file(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("copy_file", args, kwargs, ret, 2, 2, set(), False)
    src, dst = args
    return "copy /y {} {}\n".format(quoted(src), quoted(dst))

def macro_move_file(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("move_file", args, kwargs, ret, 2, 2, set(), False)
    src, dst = args
    return "move /y {} {}\n".format(quoted(src), quoted(dst))

def macro_copy_dir(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("copy_dir", args, kwargs, ret, 2, 2, set(), False)
    src, dst = args
    return "xcopy /s /q /y /i {} {}\n".format(quoted(src), quoted(dst))

def macro_use_tool(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    #print("opts", opts)
    paths1 = set()
    paths2 = set()
    for n in args:
        if n == 'xz':
            paths1.add('C:\\Program Files\\Git\\usr\\bin')
        elif n == 'tar':
            paths1.add('C:\\Program Files\\Git\\mingw64\\bin')
        elif n == 'ninja':
            if ctx.github:
                #paths.add('C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\Common7\\IDE\\CommonExtensions\\Microsoft\\CMake\\Ninja')
                #paths2.add('C:\\ProgramData\\Chocolatey\\bin')
                # C:\\ProgramData\\Chocolatey\\bin has gcc in it
                pass
            else:
                paths1.add('C:\\Ninja')
        elif n in ['mingw8', 'mingw81']:
            paths1.add('C:\\qt\\Tools\\mingw810_64\\bin')
        elif n == 'qt5-mingw8':
            paths1.add('C:\\Qt\\5.15.2\\mingw81_64\\bin')
        elif n == 'git':
            paths1.add('C:\\Program Files\\Git\\mingw64\\bin')
        elif n == 'cmake':
            if ctx.github:
                paths1.add('C:\\Program Files\\CMake\\bin')
            else:
                paths1.add('C:\\cmake-3.23.2-windows-x86_64\\bin')
        elif n == 'patch':
            paths1.add('C:\\Program Files\\Git\\usr\\bin')
        elif n in ['python', 'aqt']:
            if ctx.github:
                paths1.add("C:\\Miniconda")
                paths1.add("C:\\Miniconda\\Scripts")
            else:
                paths1.add('C:\\Miniconda3')
                paths1.add('C:\\Miniconda3\\Scripts')
        elif n == '7z':
            paths1.add('C:\\Program Files\\7-Zip')
        else:
            print("use_tool({}) not implemented".format(n))

    if len(paths1) + len(paths2) > 0:
        paths = list(paths1) + list(paths2) + ['%PATH%']
        return "set PATH=" + ";".join(paths) + "\n"
    return ""

def macro_install_tool(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    res = []
    for n in args:
        if n == 'aqt':
            res.append('where aqt || pip install aqtinstall')
        elif n in ['mingw8', 'mingw81']:
            res.append('if not exist C:\\Qt\\Tools\\mingw810_64\\bin\\gcc.exe aqt install-tool --outputdir C:\\Qt windows desktop tools_mingw qt.tools.win64_mingw810')
        elif n == 'cmake':
            if ctx.github:
                # windows-2022 C:\Program Files\CMake\bin\cmake.exe
                pass
            else:
                download_expr, _ = macro_download('', ['https://github.com/Kitware/CMake/releases/download/v3.24.2/cmake-3.24.2-windows-x86_64.zip', 'cmake-3.24.2-windows-x86_64.zip'], opts)
                #unzip_expr, _ = macro_unzip('', ['cmake-3.24.2-windows-x86_64.zip', 'cmake-3.24.2-windows-x86_64'], opts)
                res.append('if not exist C:\\cmake-3.24.2-windows-x86_64\\bin\\cmake.exe (')
                res.append(download_expr.rstrip())
                res.append('7z x -y -oC:\ cmake-3.24.2-windows-x86_64.zip')
                res.append(')')
        elif n == 'ninja':
            if ctx.github:
                # windows-2022 C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe
                pass
            else:
                pass
        else:
            print("install_tool({}) not implemented".format(n))

    return "\n".join(res) + "\n"

def macro_call_vcvars(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    if ctx.github:
        return 'call "{}"\n'.format('C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\VC\\Auxiliary\\Build\\vcvars64.bat')
    else:
        return 'call "{}"\n'.format('C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat')


def macro_where(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    res = []
    for n in args:
        res.append('echo where {}'.format(n))
        res.append('where {}'.format(n))
    return "\n".join(res) + "\n"

def macro_if_arg(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    value, defname = args
    return 'if "%1" equ "{}" goto {}_begin\n'.format(value, defname)

def macro_github_release(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    githubdata.release = args
    return '\n'

def macro_github_checkout(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    githubdata.checkout = True
    return '\n'

def macro_github_upload(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("github_upload", args, kwargs, ret, 1, 1, {"n", "name"})
    arg = args[0]
    if isinstance(arg, list):
        path = arg
    else:
        path = [arg]
    name = kwarg_value(kwargs, "n", "name")
    if name is None:
        name = os.path.splitext(os.path.basename(path[0]))[0]
    githubdata.upload = GithubUpload(name, path)
    return '\n'

def macro_github_matrix(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("github_matrix", args, kwargs, ret, 1, 1, set(), True)
    githubdata.matrix.matrix[ret] = args[0]
    return '\n'

def macro_github_matrix_include(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    githubdata.matrix.include.append(kwargs)
    return '\n'

def macro_github_matrix_exclude(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    githubdata.matrix.exclude.append(kwargs)
    return '\n'

def macro_github_setup_msys2(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("setup_msys2", args, kwargs, ret, 0, 0, {"m", "msystem", "i", "install", "u", "update"})
    msystem = kwarg_value(kwargs, "m", "msystem")
    install = kwarg_value(kwargs, "i", "install")
    update = kwarg_value(kwargs, "u", "update")
    if update is not None:
        update = {"false":False, "true":True}[update]
    githubdata.setup_msys2 = GithubSetupMsys2(msystem, install, update)
    return '\n'

def macro_github_setup_node(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("setup_node", args, kwargs, ret, 1, 1, {})
    node_version = args[0]
    githubdata.setup_node = GithubSetupNode(node_version)
    return '\n'

def macro_pushd_cd(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    if ctx.github:
        return '\n'
    return 'pushd %~dp0\n'

def macro_popd_cd(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    if ctx.github:
        return '\n'
    return 'popd\n'

def macro_substr(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("substr", args, kwargs, ret, 2, 3, {}, True)
    stop = None
    if len(args) == 3:
        varname, start, stop = args
    elif len(args) == 2:
        varname, start, _ = args
    if stop:
        ixs = "{},{}".format(start, stop)
    else:
        ixs = stop
    return 'set {}=%{}:~{}%\n'.format(ret, varname, ixs)

def macro_foreach(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("foreach", args, kwargs, ret, 2, -1, [])
    vars = args[1:]
    res = []
    for i in range(len(vars[0])):
        expr = args[0]
        for j in range(len(vars)):
            pat = "\\${}".format(j + 1)
            expr = re.sub(pat, vars[j][i], expr)
        res.append(expr + "\n")
    return "".join(res)

def maybe_macro(line):
    if '(' not in line:
        return False
    if ')' not in line:
        return False
    for n in MACRO_NAMES:
        if n in line:
            return True
    return False
    
def rewrap(lines):
    text = "".join(lines)
    lines = [line + "\n" for line in text.split("\n")]
    return lines

def reindent(expr, orig):
    ws = re.match("(\\s*)", orig).group(1)
    lines = [ws + line for line in expr.split("\n")]
    #print(expr, lines)
    return "\n".join(lines) + "\n"

def expand_macros(defs, thens, shells, opts: Opts, github, githubdata: GithubData):

    if 'clean' not in defs:
        defs['clean'] = []
        shells['clean'] = 'cmd'

    need_rewrap = set()

    for name in defs.keys():
        shell = shells[name]
        for i, line in enumerate(defs[name]):
            if 'foreach' in line and maybe_macro(line):
                try:
                    ret, macroname, args, kwargs = parse_macro(line)
                    if macroname == 'foreach':
                        ctx = Ctx(github, shell)
                        exp = macro_foreach(name, args, kwargs, ret, opts, ctx, githubdata)
                        defs[name][i] = reindent(exp, line)
                        need_rewrap.add(name)
                except ParseMacroError as e:
                    pass

    for name in need_rewrap:
        defs[name] = rewrap(defs[name])

    for name in defs.keys():
        shell = shells[name]
        for i, line in enumerate(defs[name]):
            if maybe_macro(line):
                try:
                    ret, macroname, args, kwargs = parse_macro(line)
                    ctx = Ctx(github, shell)
                    if macroname.split("_")[0] == 'github':
                        exp = globals()['macro_' + macroname](name, args, kwargs, ret, opts, ctx, githubdata)
                    elif macroname in ['download', 'unzip']:
                        exp, clean_exp = globals()['macro_' + macroname](name, args, kwargs, ret, opts, ctx, githubdata)
                    else:
                        exp = globals()['macro_' + macroname](name, args, kwargs, ret, opts, ctx, githubdata)
                    defs[name][i] = reindent(exp, line)
                    continue
                except ParseMacroError as e:
                    pass

    if len(defs['clean']) > 0:
        defs['clean'] = ['pushd %~dp0\n'] + defs['clean'] + ['popd\n']
    else:
        del defs['clean']

def write(path, text):
    if isinstance(path, str):
        with open(path, 'w', encoding='cp866') as f:
            f.write(text)
    else:
        # StringIO
        path.write(text)

used_ids = set()

class Dumper(yaml.Dumper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # disable resolving on as tag:yaml.org,2002:bool (disable single quoting)
        cls = self.__class__
        cls.yaml_implicit_resolvers['o'] = []


def make_main_step(cmds, name, local):
    if local:
        return "rem {}\n".format(name) + "\n".join(cmds) + "\n"
    else:
        return {
            "name": name, 
            "shell": "cmd", 
            "run": str_or_literal(cmds)
        }

def is_empty_def(def_):
    if def_ is None:
        return True
    for line in def_:
        if line.strip() != "":
            return False
    return True

def defnames_ordered(defs, thens):
    res = ['main']
    
    while len(res) < len(defs):
        if res[-1] in thens:
            res.append(thens[res[-1]])
        else:
            not_used = set(defs.keys()).difference(set(res))
            print("warning: not used defs ({}) will not be in workkflow".format(", ".join(not_used)))
            break

    return res

def filter_empty_lines(text):
    return "\n".join([l for l in text.split('\n') if l.strip() != ''])

def insert_matrix_values(text, matrix : GithubMatrix):
    for key, values in matrix.matrix.items():
        pattern = '[$][{][{]\\s*' + 'matrix.' + key + '\\s*[}][}]'
        text = re.sub(pattern, values[0], text)
    include = matrix.include
    if len(include) > 0:
        for key, value in include[0].items():
            pattern = '[$][{][{]\\s*' + 'matrix.' + key + '\\s*[}][}]'
            text = re.sub(pattern, value, text)
    return text

def github_check_cd(text):
    problem = '%~dp0'
    if problem in text:
        raise Exception("{} does not work on github actions use %CD%".format(problem))

def read_compile_write(src, dst_bat, dst_workflow, verbose=True, echo_off=True, warning=True):

    if isinstance(src, str):
        src_name = os.path.basename(src)
    else:
        src_name = 'untitled'

    dst_paths = []

    for github in [False, True]:
        githubdata = GithubData()
        
        defs, thens, shells, opts = read(src, github)

        if github and not opts.github_workflow:
            continue

        if github:
            os.makedirs(os.path.dirname(dst_workflow), exist_ok=True)

        expand_macros(defs, thens, shells, opts, github, githubdata)

        if github:
            
            steps = []
            if githubdata.checkout:
                steps.append({"uses": "actions/checkout@v3", "name": "checkout"})

            if githubdata.setup_msys2:
                steps.append(make_setup_msys2_step(githubdata.setup_msys2, opts))

            if githubdata.setup_node:
                steps.append(make_setup_node_step(githubdata.setup_node))

            for name in defnames_ordered(defs, thens):
                text = filter_empty_lines(render_one(name, defs, thens, opts, src_name, echo_off = False, warning = False))
                text = dedent(text)
                github_check_cd(text)
                step = GithubShellStep(text, shells[name], name)
                steps.append(make_github_step(step, opts, githubdata))

            if githubdata.upload:
                steps.append(make_upload_step(githubdata.upload))

            if len(githubdata.release) > 0:
                steps.append(make_release_step(githubdata.release))

            save_workflow(dst_workflow, steps, opts, githubdata)
            dst_paths.append(dst_workflow)
        else:

            text, files = render_local_main(defs, thens, shells, opts, src_name, echo_off, warning)

            for file_name, file_content in files:
                dst_path = os.path.join(os.path.dirname(src), file_name)
                file_content = dedent(insert_matrix_values(file_content, githubdata.matrix))
                write(dst_path, file_content)
                dst_paths.append(dst_path)

            text = dedent(insert_matrix_values(text, githubdata.matrix))

            write(dst_bat, text)
            dst_paths.append(dst_bat)

    if verbose and isinstance(src, str) and isinstance(dst_bat, str):
        print("{} -> \n {}".format(src, "\n ".join(dst_paths)))

