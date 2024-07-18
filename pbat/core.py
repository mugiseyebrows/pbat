from dataclasses import dataclass, field
import os
import re
import random
import textwrap
import yaml
from collections import defaultdict
import hashlib

# todo shell python bash pwsh


try:
    from .parsemacro import parse_macro, ParseMacroError
    from .parsedef import parse_def
    from .Opts import Opts, copy_opts
    from .parsescript import parse_script, ON_PUSH, ON_TAG, ON_RELEASE, MACRO_NAMES, DEPRECATED_MACRO_NAMES, Script, Function
except ImportError:
    from parsemacro import parse_macro, ParseMacroError
    from parsedef import parse_def
    from Opts import Opts, copy_opts
    from parsescript import parse_script, ON_PUSH, ON_TAG, ON_RELEASE, MACRO_NAMES, DEPRECATED_MACRO_NAMES, Script, Function

WARNING = 'This file is generated from {}, all edits will be lost'


CHECKSUM_ALGS = ['b2','md5','sha1','sha224','sha256','sha384','sha512']



@dataclass
class GithubUpload:
    name: str = None
    path: list = field(default_factory=list)

@dataclass
class GithubSetupNode:
    node_version: int = None

@dataclass
class GithubSetupJava:
    distribution: str = None
    java_version: int = None

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
    condition: str = None

@dataclass
class GithubCacheStep:
    name: str
    path: list[str]
    key: str

@dataclass
class GithubMatrix:
    matrix: dict = field(default_factory=dict)
    include: list = field(default_factory=list)
    exclude: list = field(default_factory=list)

@dataclass
class GithubData:
    checkout: bool = False
    release: list = field(default_factory=list)
    upload: list[GithubUpload] = field(default_factory=list)
    matrix: GithubMatrix = field(default_factory=GithubMatrix)
    setup_msys2: GithubSetupMsys2 = None
    setup_node: GithubSetupNode = None
    setup_java: GithubSetupJava = None
    steps: list = field(default_factory=list)
    cache: list[GithubCacheStep] = field(default_factory=list)

@dataclass
class Ctx:
    github: bool
    shell: str

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
    if len(items) == 1 and '%' not in items[0]:
        return items[0]
    return literal_str("\n".join(items) + "\n")

def make_release_step(artifacts):
    return {
        "name": "release",
        "uses": "softprops/action-gh-release@v2",
        "if": "startsWith(github.ref, 'refs/tags/')",
        "with": {
            "files": str_or_literal(artifacts)
        }
    }

def make_upload_step(data: GithubUpload):
    
    return {
        "name": "upload",
        "uses": "actions/upload-artifact@v4",
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

def make_checkout_step():
    return {"name": "checkout", "uses": "actions/checkout@v4"}

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
        "name": "setup node",
        "uses": "actions/setup-node@v3",
        "with": {"node-version": data.node_version}
    }
    return obj

def make_setup_java_step(data: GithubSetupJava):
    obj = {
        "name": "setup java",
        "uses": "actions/setup-java@v4",
        "with": {
            "distribution": data.distribution,
            "java-version": data.java_version
        }
    }
    return obj

def make_cache_step(step: GithubCacheStep):
    obj = {
        "name": step.name,
        "uses": "actions/cache@v4",
        "with": {
            "path": str_or_literal(step.path),
            "key": step.key
        }
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

    if step.condition:
        obj["if"] = step.condition

    return obj







def insert_deps(names, deps):
    res = []
    for n in names:
        if n in deps:
            n_deps = deps[n]
            for d in n_deps:
                if d not in res:
                    res.append(d)
        res.append(n)
    #print('deps', deps)
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

def uniq(vs):
    res = []
    for v in vs:
        if v not in res:
            res.append(v)
    return res

def render_function(function: Function, opts: Opts, github_data: GithubData):
    res = []
    opts = copy_opts(opts)
    github = True
    name = function._name
    lines = expand_macros(name, function._body, opts, github, github_data)
    head = []
    if len(opts.env_path) > 0 or opts.clear_path:
        if opts.clear_path:
            env_path = opts.env_path + ['C:\Windows', 'C:\Windows\System32']
            pat = 'set PATH={}'
        else:
            env_path = opts.env_path
            pat = 'set PATH={};%PATH%'
        head += [pat.format(";".join(uniq(env_path))) + '\n']
    lines = head + lines
    res.append(":{}_begin\n".format(name))
    res.append("".join(lines))
    res.append(":{}_end\n".format(name))
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

def insert_before(a, b, keys):
    if b not in keys:
        return False
    if a in keys and b in keys:
        if keys.index(a) < keys.index(b):
            return False
    if a in keys:
        keys.pop(keys.index(a))
    keys.insert(keys.index(b), a)
    return True

def insert_after(a, b, keys):
    if b not in keys:
        return False
    if a in keys and b in keys:
        if keys.index(a) > keys.index(b):
            return False
    if a in keys:
        keys.pop(keys.index(a))
    keys.insert(keys.index(b) + 1, a)
    return True




def update_chain_(deps, chain, tested):
    name = next(filter(lambda n: n not in tested, chain), None)
    if name is None:
        return False
    tested.add(name)
    def get_deps(name):
        if name in deps:
            return deps[name]
        return []
    ins = [n for n in get_deps(name) if n not in chain]
    ix = chain.index(name)
    for i, n in enumerate(ins):
        chain.insert(ix + i, n)
    return True


def render_local_main(script: Script, opts: Opts, src_name, echo_off=True, warning=True):
    res = []

    keys, thens = script.compute_order()
    for name in keys:
        function = script.function(name)
        lines = expand_macros(name, function._body, opts, False)
        #res.append("rem def {}\n".format(name))
        res.append(":{}_begin\n".format(name))
        if opts.debug:
            res.append("echo {}\n".format(name))
            #res.append(macro_log(name, [name]))
        shell = function._shell
        if shell is None:
            shell = 'cmd'
        if shell == 'cmd':
            res.append("".join(lines))
        else:
            raise Exception('not implemented')
        res.append(":{}_end\n".format(name))
        goto = None
        if name in thens:
            if thens[name] != 'exit':
                goto = "goto {}_begin\n".format(thens[name])
        if goto is None:
            goto = "exit /b\n"
        res.append(goto)
        res.append("\n")

    head = []

    if not opts.debug and echo_off:
        head.append('@echo off\n')

    if warning:
        head.append('rem This file is generated from {}, all edits will be lost\n'.format(src_name))

    if len(opts.env_path) > 0 or opts.clear_path:
        if opts.clear_path:
            env_path = opts.env_path + ['C:\Windows', 'C:\Windows\System32']
            pat = 'set PATH={}'
        else:
            env_path = opts.env_path
            pat = 'set PATH={};%PATH%'
        head += [pat.format(";".join(uniq(env_path))) + '\n']

    if opts.need_patch_var:
        head += expand_macros(name, ['PATCH = find_app(C:\\Program Files\\Git\\usr\\bin\\patch.exe)\n'], opts)
    
    if opts.need_curl_var:
        head += expand_macros(name, ['CURL = find_app(C:\\Windows\\System32\\curl.exe, C:\\Program Files\\Git\\mingw64\\bin\\curl.exe, C:\\Program Files\\Git\\mingw32\\bin\\curl.exe)\n'], opts)

    files = []

    res = head + res

    while(True):
        ok1 = remove_unused_labels(res)
        ok2 = remove_redundant_gotos(res)
        if not ok1 and not ok2:
            break

    return "".join(res), files



def render_local_main_(defs, deps, thens, shells, top, order, opts: Opts, src_name, echo_off=True, warning=True):

    #print("render_local_main")

    res = []

    files = []

    if not opts.debug and echo_off:
        res = res + ['@echo off\n']

    if warning:
        res += ['rem This file is generated from {}, all edits will be lost\n'.format(src_name)]

    if len(opts.env_path) > 0:
        if opts.clear_path:
            pat = 'set PATH={};C:\Windows;C:\Windows\System32'
        else:
            pat = 'set PATH={};%PATH%'
        res += [pat.format(";".join(uniq(opts.env_path))) + '\n']

    defs_ = {"top": top}
    thens_ = dict()
    shells_ = {"top": 'cmd'}
    expand_macros(defs_, thens_, shells_, opts)
    #print(defs_['top'])
    res.extend(defs_['top'])

    keys, thens_ = compute_order(defs, deps, thens, order)
    
    """
    if opts.main_def:
        main_def = opts.main_def
    else:
        main_def = 'main'

    keys = [main_def] + without(defs.keys(), main_def)
    """

    #print("order", order)
    #return "".join(res), files

    

    #print("deps", deps)
    #print("thens", thens)

    """
    if not opts.clean:
        keys = without(keys, 'clean')
    """

    for name in keys:
        lines = defs[name]
        #res.append("rem def {}\n".format(name))
        res.append(":{}_begin\n".format(name))
        if opts.debug:
            res.append("echo {}\n".format(name))
            #res.append(macro_log(name, [name]))
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
        
        goto = None
        if name in thens_:
            if thens_[name] != 'exit':
                goto = "goto {}_begin\n".format(thens_[name])
        if goto is None:
            goto = "exit /b\n"

        res.append(goto)
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
    
    validate_args("find_app", args, kwargs, ret, 1, None, {"g", "goto", "c", "cmd"}, True)

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

    if isinstance(args[0], list):
        items = args[0]
    else:
        items = args

    tests = ["if exist \"{}\" set {}={}\n".format(item, env_name, item) for i, item in enumerate(reversed(items))]
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
    if "*" in s:
        return s
    if ' ' in s or '%' in s or '+' in s:
        return '"' + s + '"'
    return s

def escape_url(s):
    return quoted("".join(["^" + c if c == '%' else c for c in s]))

def macro_return(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    return 'goto {}_end'.format(name)

def macro_download(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):

    url = args[0]

    if len(args) > 1:
        dest = args[1]
    else:
        dest = os.path.basename(url).split('?')[0]

    shell = ctx.shell

    cache = kwarg_value(kwargs, 'cache', 'c')

    if opts.env_policy and not ctx.github:
        curl = '"%CURL%"'
        opts.need_curl_var = True
    else:
        curl = "curl"
        if not ctx.github:
            opts.env_path.append('C:\\Program Files\\Git\\mingw64\\bin')
            opts.env_path.append('C:\\Program Files\\Git\\mingw32\\bin')
            opts.env_path.append('C:\\Windows\\System32')
    
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

    if kwarg_value(kwargs, 'k'):
        insecure = '-k'
    else:
        insecure = ''

    if is_curl:
        cmd = spacejoin_nonempty(curl, '-L', proxy, user_agent, insecure, '-o', quoted(dest), quoted(url)) + "\n"
    elif is_wget:
        wget = "C:\\msys64\\usr\\bin\\wget.exe"
        cmd = " ".join([wget, '-O', quoted(dest), quoted(url)]) + "\n"

    if shell == 'cmd':
        if cache is None:
            exp = cmd
        else:
            exp = "if not exist {} {}\n".format(quoted(dest), cmd)
    elif shell == 'msys2':
        if cache is None:
            exp = cmd
        else:
            exp = "if [ ! -f {} ]; then {}; fi\n".format(quoted(dest), cmd)
    else:
        raise Exception('not implemented for shell {}'.format(shell))

    return exp

def kwarg_value(kwargs, *names):
    for name in names:
        value = kwargs.get(name)
        if value is not None:
            return value


def macro_unzip(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):

    if not ctx.github:
        opts.env_path.append('C:\\Program Files\\7-Zip')

    src = args[0]

    if len(args) == 2:
        print("unzip with 2 args, did you mean :test?", args)

    #force = kwargs.get('force')
    #keep = kwargs.get('keep')
    test = kwarg_value(kwargs, 'test', 't')
    output = kwarg_value(kwargs, 'output', 'o')
    #files = kwarg_value(kwargs, 'files', 'f')

    """
    if opts.zip_in_path or ctx.github:
        cmd = ['7z']
    else:
        cmd = ['"%P7Z%"']
    """
    cmd = ['7z']

    cmd = cmd + ['x', '-y']
    if output:
        cmd.append("-o{}".format(quoted(output)))
    cmd.append(quoted(src))

    for arg in args[1:]:
        cmd.append(quoted(arg))

    exp = " ".join(cmd) + "\n"

    if test:
        exp = "if not exist {} ".format(quoted(test)) + exp
    else:
        pass

    return exp

def macro_zip(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):

    if ctx.shell == 'cmd':
        opts.env_path.append('C:\\Program Files\\7-Zip')

    COMPRESSION_MODE = {
        "-mx0": "copy",
        "-mx1": "fastest",
        "-mx3": "fast",
        "-mx5": "normal",
        "-mx7": "maximum",
        "-mx9": "ultra"
    }
    kwnames = list(COMPRESSION_MODE.values()) + ["lzma", "test", "clean"]

    validate_args("zip", args, kwargs, ret, 2, None, kwnames, False)

    dst, src = args[0], args[1:]
    zip = '7z'
    
    #cmd = cmd + ' a -y {} {}\n'.format(quoted(dst), quoted(src))
    flags = ['-y']
    if kwarg_value(kwargs, "lzma"):
        flags.append('-m0=lzma2')
    for flag, mode in COMPRESSION_MODE.items():
        if kwarg_value(kwargs, mode):
            flags.append(flag)
            break

    test = []
    #if opts.zip_test:
    if kwarg_value(kwargs, "t", "test"):
        test = ['if not exist', quoted(dst)]

    cmd = test + [zip, 'a'] + flags + [quoted(dst)] + [quoted(e) for e in src]

    return " ".join(cmd) + "\n"

def macro_patch(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("patch", args, kwargs, ret, 1, 1, {"N", "forward", "p1"})

    opts.use_patch = True

    if opts.env_policy and not ctx.github:
        patch = '"%PATCH%"'
        opts.need_patch_var = True
    else:
        patch = "patch"
        if not ctx.github:
            opts.env_path.append('C:\\Program Files\\Git\\usr\\bin')

    cmd = [patch]
    if kwarg_value(kwargs, 'N', "forward"):
        cmd.append('-N')
    p1 = kwarg_value(kwargs, "p1")
    if p1:
        cmd.append('-p1')

    cmd = cmd + ["-i", quoted(args[0])]
    return " ".join(cmd) + "\n"
    
def macro_mkdir(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    arg = args[0]
    return "if not exist \"{}\" mkdir \"{}\"\n".format(arg, arg)

def macro_log(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    arg = args[0]
    return "echo %DATE% %TIME% {} >> %~dp0log.txt\n".format(arg)

def macro_rmdir(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    arg = args[0]
    github = kwarg_value(kwargs, "github")
    if not ctx.github and github:
        return '\n'
    return "rmdir /s /q {} || echo 1 > NUL\n".format(quoted(arg))

def macro_test_exist(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    path = args[0]
    return "if exist {} (\necho {} exist\n) else (\necho {} does not exist\n)\n".format(
        quoted(path), path, path
    )

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
    submodules = kwarg_value(kwargs, 'submodules', 'recurse-submodules')
    
    basename = os.path.splitext(os.path.basename(url))[0]
    if dir:
        basename = dir

    opts.env_path.append('C:\\Program Files\\Git\\cmd')
    git = 'git'

    clone = [git, 'clone']
    if submodules is not None:
        clone.append('--recurse-submodules')
    clone.append(url)

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

def macro_copy(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("copy", args, kwargs, ret, 2, 2, set(), False)
    src, dst = args
    return "copy /y {} {}\n".format(quoted(src), quoted(dst))

def macro_move(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("move", args, kwargs, ret, 2, 2, ["github", "g", "i", "ignore-errors"], False)
    github = kwarg_value(kwargs, "github", "g")
    ignore_errors = kwarg_value(kwargs, "ignore-errors", "i")
    src, dst = args
    if not ctx.github and github:
        return '\n'
    res = ["move /y {} {}".format(quoted(src), quoted(dst))]
    if ignore_errors:
        res.append("echo 1 > NUL")
    return " || ".join(res) + "\n"

def macro_del(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    return "del /f /q " + " ".join([quoted(arg) for arg in args])

def macro_xcopy(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("xcopy", args, kwargs, ret, 2, 2, ['q'], False)
    src, dst = args
    keys = ['s','e','y','i']
    q = kwargs.get('q')
    if q:
        keys.append('q')
    keys_ = " ".join(["/{}".format(k) for k in keys])
    return "xcopy {} {} {}\n".format(keys_, quoted(src), quoted(dst))


def macro_call_vcvars(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):

    opts.env_path.append('C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\VC\\Auxiliary\\Build')
    opts.env_path.append('C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\Community\\VC\\Auxiliary\\Build')

    """
    if ctx.github:
        return 'call "{}"\n'.format('C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\VC\\Auxiliary\\Build\\vcvars64.bat')
    else:
        return 'call "{}"\n'.format('C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat')
    """
    return 'call vcvars64.bat'

def macro_if_exist_return(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    if len(args) < 1:
        print("macro if_exist_return requires an argument")
        return ''
    return 'if exist {} goto {}_end'.format(quoted(args[0]), name)

def macro_where(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    res = []
    for n in args:
        res.append('where {} || echo {} not found'.format(n, n))
    return "\n".join(res) + "\n"

def macro_if_arg(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    value, defname = args
    return 'if "%1" equ "{}" goto {}_begin\n'.format(value, defname)

def macro_github_release(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    githubdata.release.extend(args)
    return '\n'

def macro_github_checkout(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    githubdata.checkout = True
    return '\n'

def macro_github_upload(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("github_upload", args, kwargs, ret, 1, None, {"n", "name"})
    path = args
    upload_name = kwarg_value(kwargs, "n", "name")
    if upload_name is None:
        upload_name = os.path.splitext(os.path.basename(path[0]))[0]
        upload_name = upload_name.replace('*', '')
    githubdata.upload.append(GithubUpload(upload_name, path))
    return '\n'

def macro_github_cache(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    step_name = kwarg_value(kwargs, "n", "name")
    paths = args
    if len(paths) == 0:
        raise ValueError("github_cache() requires at least one path as argument")
    key = kwarg_value(kwargs, "k", "key")
    if step_name is None:
        step_name = "cache {}".format(" ".join(paths))
    if key is None:
        key = hashlib.md5(";".join(paths)).digest().hex()
    githubdata.cache.append(GithubCacheStep(step_name, paths, key))
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

def macro_github_setup_java(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    validate_args("setup_java", args, kwargs, ret, 2, 2, {})
    distribution, java_version = args
    githubdata.setup_java = GithubSetupJava(distribution, java_version)
    return '\n'

def macro_pushd_cd(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    if ctx.github:
        return 'pushd %GITHUB_WORKSPACE%\n'
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

def macro_install(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):

    ver = None
    arch = None
    if len(args) == 3:
        app, ver, arch = args
    elif len(args) == 2:
        app, ver = args
    elif len(args) == 1:
        app, = args
    else:
        raise ValueError("install requires at least one arg")
    
    if app == 'qt':
        if ver == '5.15.2' or ver is None:
            if arch == 'win64_mingw81' or arch is None:
                opts.env_path.append('C:\\Qt\\5.15.2\\mingw81_64\\bin')
                return 'if not exist "C:\\Qt\\5.15.2\\mingw81_64\\bin\\qmake.exe" aqt install-qt windows desktop 5.15.2 win64_mingw81 -O C:\\Qt'
            else:
                raise ValueError("install(qt, {}, {}) not implemented".format(ver, arch))
        else:
            raise ValueError("install(qt, {}) not implemented".format(ver))

    elif app in ['mingw', 'mingw64']:
        if ver == '8.1.0':
            opts.env_path.append('C:\\Qt\\Tools\\mingw810_64\\bin')
            return 'if not exist "C:\\Qt\\Tools\\mingw810_64\\bin\\gcc.exe" aqt install-tool windows desktop tools_mingw qt.tools.win64_mingw810 -O C:\\Qt'
        else:
            raise ValueError("install(mingw, {}) not implemented".format(ver))

    elif app in ['aqt', 'aqtinstall']:
        return 'where aqt > NUL || pip install aqtinstall'

    elif app == 'mugideploy':
        return 'where mugideploy > NUL || pip install mugideploy'

    elif app == 'mugicli':
        return 'where pyfind > NUL || pip install mugicli'

    elif app == 'mugisync':
        return 'where mugisync > NUL || pip install mugisync'
    
    raise ValueError("install({}) not implemented".format(app))

def macro_use(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    ver = None
    arch = None
    if len(args) == 3:
        app, ver, arch = args
    elif len(args) == 2:
        app, ver = args
    elif len(args) == 1:
        app, = args
    else:
        raise ValueError("use requires at least one arg")

    if app in ['conda', 'miniconda']:
        if ctx.github:
            opts.env_path.append('C:\Miniconda')
            opts.env_path.append('C:\Miniconda\\Scripts')
        else:
            opts.env_path.append('C:\Miniconda3')
            opts.env_path.append('C:\Miniconda3\\Scripts')
            opts.env_path.append('%USERPROFILE%\\Miniconda3')
            opts.env_path.append('%USERPROFILE%\\Miniconda3\\Scripts')
    elif app == 'psql':
        if ver is None:
            ver = '14'
        opts.env_path.append('C:\\Program Files\\PostgreSQL\\{}\\bin'.format(ver))
        opts.env_path.append('C:\\Program Files\\PostgreSQL\\{}\\bin'.format(ver))
    elif app == 'qwt':
        if ver is None:
            ver = '6.2.0'
        opts.env_path.append('C:\\Qwt-{}\\lib'.format(ver))
    elif app == 'mysql':
        if ver is None:
            ver = '8.2.0'
        opts.env_path.append('C:\\mysql-{}-winx64\\bin'.format(ver))
        opts.env_path.append('C:\\mysql-{}-winx64\\lib'.format(ver))
    elif app == '7z':
        opts.env_path.append('C:\\Program Files\\7-Zip')
    elif app == 'git':
        opts.env_path.append('C:\\Program Files\\Git\\cmd')
    elif app == 'sed':
        return 'set SED=C:\\Program Files\\Git\\usr\\bin\\sed.exe\n'
    elif app == 'diff':
        return 'set DIFF=C:\\Program Files\\Git\\usr\\bin\\diff.exe\n'
    elif app == 'perl':
        opts.env_path.append('C:\\Strawberry\\perl\\bin')
    elif app == 'cmake':
        if not ctx.github:
            opts.env_path.append('C:\\Program Files\\CMake\\bin')
    elif app == 'ninja':
        if ctx.github:
            opts.env_path.append('C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\Common7\\IDE\\CommonExtensions\\Microsoft\\CMake\\Ninja')
            opts.env_path.append('C:\\Program Files (x86)\\Android\\android-sdk\\cmake\\3.22.1\\bin')
        else:
            opts.env_path.append('C:\\Program Files\\Meson')
    elif app == 'mingw':
        if ver in ['5', '5.4.0', '540_32']:
            opts.env_path.append('C:\\mingw540_32\\bin')
        elif ver in ['8', '8.1.0', '810_64']:
            opts.env_path.append('C:\\Qt\\Tools\\mingw810_64\\bin')
        elif ver in ['11', '11.2.0', '1120_64']:
            opts.env_path.append('C:\\mingw1120_64\\bin')
        else:
            raise ValueError("use not implemented for {} {}".format(app, ver))
    elif app == 'qt':
        if ver == '6':
            ver = '6.7.1'
        elif ver == '5':
            ver = '5.15.2'
        elif ver == '4':
            ver = '4.8.7'
        if ver.startswith('6.'):
            opts.env_path.append('C:\\Qt\\{}\\mingw1120_64\\bin'.format(ver))
        elif ver.startswith('5.'):
            opts.env_path.append('C:\\Qt\\{}\\mingw81_64\\bin'.format(ver))
        elif ver.startswith('4.'):
            opts.env_path.append('C:\\Qt-{}\\bin'.format(ver))
    else:
        raise ValueError("use not implemented for {}".format(app))

    return ''

def macro_add_path(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    #print("add_path args", args)
    for arg in args:
        opts.env_path.append(arg)
    return ''

def macro_clear_path(name, args, kwargs, ret, opts: Opts, ctx: Ctx, githubdata: GithubData):
    opts.clear_path = True
    return ''

def maybe_macro(line):
    if '(' not in line:
        return False
    if ')' not in line:
        return False
    for n in MACRO_NAMES + DEPRECATED_MACRO_NAMES:
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

def expand_macros(name, lines, opts: Opts, github: bool = False, githubdata: GithubData = None):
    res = list(lines)
    shell = 'cmd'
    if githubdata is None:
        githubdata = GithubData()
    for i, line in enumerate(lines):
        if maybe_macro(line):
            try:
                ret, macroname, args, kwargs = parse_macro(line)
                if macroname in DEPRECATED_MACRO_NAMES:
                    print("{} is deprecated".format(macroname))
                    continue
                ctx = Ctx(github, shell)
                exp = globals()['macro_' + macroname](name, args, kwargs, ret, opts, ctx, githubdata)
                res[i] = reindent(exp, line)
                continue
            except ParseMacroError as e:
                pass
    return res

def expand_macros_(defs, thens, shells, opts: Opts, github: bool = False, githubdata: GithubData = None):

    """
    if 'clean' not in defs:
        defs['clean'] = []
        shells['clean'] = 'cmd'
    """
    if githubdata is None:
        githubdata = GithubData()

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

                    if macroname in DEPRECATED_MACRO_NAMES:
                        print("{} is deprecated".format(macroname))
                        continue

                    ctx = Ctx(github, shell)
                    exp = globals()['macro_' + macroname](name, args, kwargs, ret, opts, ctx, githubdata)
                    defs[name][i] = reindent(exp, line)
                    continue
                except ParseMacroError as e:
                    pass

    """
    if len(defs['clean']) > 0:
        defs['clean'] = ['pushd %~dp0\n'] + defs['clean'] + ['popd\n']
    else:
        del defs['clean']
    """

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
        script = parse_script(src, github)
        if github:
            steps1 = []
            steps2 = []
            steps3 = []
            opts = script._opts
            githubdata = GithubData()

            keys, thens_ = script.compute_order()

            for name in keys:
                function = script.function(name)
                text = filter_empty_lines(render_function(function, opts, githubdata))
                text = dedent(text)
                github_check_cd(text)
                if text == '':
                    continue
                shell = 'cmd'
                condition = None
                step = GithubShellStep(text, shell, name, condition)
                steps2.append(make_github_step(step, opts, githubdata))

            # pre steps

            if githubdata.checkout:
                steps1.append(make_checkout_step())

            if githubdata.setup_msys2:
                steps1.append(make_setup_msys2_step(githubdata.setup_msys2, opts))

            if githubdata.setup_node:
                steps1.append(make_setup_node_step(githubdata.setup_node))

            if githubdata.setup_java:
                steps1.append(make_setup_java_step(githubdata.setup_java))

            for item in githubdata.cache:
                steps1.append(make_cache_step(item))

            # post steps

            for item in githubdata.upload:
                steps3.append(make_upload_step(item))

            if len(githubdata.release) > 0:
                steps3.append(make_release_step(githubdata.release))

            steps = steps1 + steps2 + steps3

            save_workflow(dst_workflow, steps, script._opts, githubdata)
            dst_paths.append(dst_workflow)
        else:
            opts = script._opts
            text, files = render_local_main(script, opts, src_name, echo_off, warning)

            text = dedent(text)

            write(dst_bat, text)
            dst_paths.append(dst_bat)

    if verbose and isinstance(src, str) and isinstance(dst_bat, str):
        print("{} -> \n {}".format(src, "\n ".join(dst_paths)))

def read_compile_write_(src, dst_bat, dst_workflow, verbose=True, echo_off=True, warning=True):

    if isinstance(src, str):
        src_name = os.path.basename(src)
    else:
        src_name = 'untitled'

    dst_paths = []

    for github in [False, True]:
        githubdata = GithubData()
        
        defs, deps, thens, top, order, shells, opts, conditions = parse_script(src, github)

        if github and not opts.github_workflow:
            continue

        if github:
            os.makedirs(os.path.dirname(dst_workflow), exist_ok=True)

        expand_macros(defs, thens, shells, opts, github, githubdata)

        if github:
            
            steps = []
            if githubdata.checkout:
                steps.append(make_checkout_step())

            if githubdata.setup_msys2:
                steps.append(make_setup_msys2_step(githubdata.setup_msys2, opts))

            if githubdata.setup_node:
                steps.append(make_setup_node_step(githubdata.setup_node))

            if githubdata.setup_java:
                steps.append(make_setup_java_step(githubdata.setup_java))

            #if githubdata.cache:
            for item in githubdata.cache:
                steps.append(make_cache_step(item))

            keys, thens_ = compute_order(defs, deps, thens, order)

            for name in keys:
                text = filter_empty_lines(render_function(name, defs, thens, shells, top, order, opts, src_name, echo_off = False, warning = False))
                text = dedent(text)
                github_check_cd(text)
                if text == '':
                    continue
                step = GithubShellStep(text, shells[name], name, conditions.get(name))
                steps.append(make_github_step(step, opts, githubdata))

            for item in githubdata.upload:
                steps.append(make_upload_step(item))

            if len(githubdata.release) > 0:
                steps.append(make_release_step(githubdata.release))

            save_workflow(dst_workflow, steps, opts, githubdata)
            dst_paths.append(dst_workflow)
        else:

            text, files = render_local_main(defs, deps, thens, shells, top, order, opts, src_name, echo_off, warning)

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

