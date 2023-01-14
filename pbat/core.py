from dataclasses import dataclass, field
import os
import re
import random
import textwrap
import yaml

# todo shell python

try:
    from .parsemacro import parse_macro
    from .parsedef import parse_def
except ImportError:
    from parsemacro import parse_macro
    from parsedef import parse_def

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
    patch_in_path = False
    github_workflow = False
    github_image: str = WINDOWS_LATEST
    github_on: int = ON_PUSH
    msys2_msystem: str = None

@dataclass
class GitHubDataUpload:
    name: str = None
    path: list = field(default_factory=list)

@dataclass
class GitHubDataSetupMsys2:
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
class GitHubData:
    checkout: bool = False
    release: list = field(default_factory=list)
    upload: GitHubDataUpload = None
    matrix: dict = field(default_factory=dict)
    setup_msys2: GitHubDataSetupMsys2 = None
    steps: list = field(default_factory=list)

MACRO_NAMES = [
    'pushd_cd', 'popd_cd', 
    'find_app',
    'download', 
    'zip', 'unzip',
    'set_path', 
    'copy_file', 'copy_dir', 'mkdir', 'rmdir', 
    'git_clone', 'git_pull', 'patch', 
    'github_matrix', 'github_checkout', 'github_upload', 'github_release', 'github_setup_msys2', 'github_run',
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
        "uses": "ncipollo/release-action@v1",
        "if": "startsWith(github.ref, 'refs/tags/')",
        "with": {
            "artifacts": str_or_literal(artifacts),
            "token": "${{ secrets.GITHUB_TOKEN }}"
        }
    }

def make_upload_step(data: GitHubDataUpload):
    return {
        "name": "upload",
        "uses": "actions/upload-artifact@v3",
        "with": {
            "name": data.name,
            "path": str_or_literal(data.path)
        }
    }

def save_workflow(path, steps, opts: Opts, github: GitHubData):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    on = opts.github_on
    if on == ON_TAG:
        on_ = {"push":{"tags":"*"}}
    elif on == ON_PUSH:
        on_ = "push"
    elif on == ON_RELEASE:
        on_ = {"release": {"types": ["created"]}}

    main = {"runs-on":opts.github_image}

    if github.matrix:
        main["strategy"] = {"matrix": github.matrix, "fail-fast": False}

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

def make_setup_msys2_step(data: GitHubDataSetupMsys2, opts: Opts):
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

def make_github_step(step: GithubShellStep, opts: Opts, githubdata: GitHubData):

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
            print("warning: you might forget to add github_setup_msys2() to script")
            shell = "C:\\msys64\\usr\\bin\\bash.exe {0}"

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

    def process_line(line, cwd):
        m = re.match('^include\\s+(.*[.]pbat)$', line)
        if m is not None:
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
        return " ".join([line.strip() for line in res]) + "\n"

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
        line = line.strip()
        m = re.match('^(debug|clean|download_test|unzip_test|zip_test|github|github_workflow)\\s+(off|on|true|false|1|0)$', line)
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

        def pattern_join(*args):
            return "".join(args)

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
        """
        m = re.match('^def\\s+([a-z0-9_]+)$', line)
        if m is not None:
            name = m.group(1)
            defs[name] = []
            thens[name] = "end"
            continue
        """
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
        if line.startswith('#'):
            continue

        if name is not None:
            defs[name].append(line + "\n")


    """
    for k, v in thens.items():
        m = re.match('next\((.*)\)', v)
        if m is not None:
            n = m.group(1).strip()
            if n in thens:
                thens[k] = thens[n]
                #print("{} is {}".format(v, thens[n]))
            else:
                print("cannot expand {}".format(v))
    """

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

    if 'msys2' in shells.values():
        if github:
            pass
        else:
            defs['main'] = [
                'MSYS2 = find_app([C:\\msys64\\usr\\bin\\bash.exe])\n',
                'set_var(CHERE_INVOKING, yes)\n'
            ] + defs['main']

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


def unquoted(s):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s

def parse_array(s):
    m = re.search("\[(.*)\]",s)
    if m is not None:
        items = [unquoted(e.strip()) for e in m.group(1).split(",")]
        return items

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
        res += ['rem This file is generated from {}, all edits will be lost\n'.format(src_name)]

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

        if shells[name] == 'cmd':
            res.append("".join(lines))
        elif shells[name] == 'msys2':
            file_name = "{}_{}.sh".format(os.path.splitext(src_name)[0], name)
            file_content = "#!/bin/bash\n" + "".join(lines) + "\n"
            files.append((file_name, file_content))
            if opts.msys2_msystem:
                res.append("set MSYSTEM={}\n".format(opts.msys2_msystem))
            res.append('"%MSYS2%" {}\n'.format(file_name))
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

def validate_args(fnname, args, kwargs, ret, argmin, argmax, kwnames, needret = False):
    if argmin > -1 and argmax > -1:
        if not (argmin <= len(args) <= argmax):
            if argmin == argmax:
                nargs = str(argmin)
            else:
                nargs = "{} to {}".format(argmin, argmax)
            raise Exception("{} expects {} args, got {}: {}".format(fnname, nargs, len(args), str(args)))
    for n in kwargs:
        if n not in kwnames:
            raise Exception("{} unknown option {}".format(fnname, n))
    if needret and ret is None:
        raise Exception("{} must be assigned to env variable".format(fnname))

def macro_find_app(name, args, kwargs, ret, opts):
    
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

def macro_find_file(name, args, kwargs, ret, opts):
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

def macro_download(name, args, kwargs, ret, opts):
    url = args[0]
    dest = args[1]

    force = kwargs.get('force')
    keep = kwargs.get('keep')
    if opts.curl_in_path:
        curl = "curl"
    else:
        curl = '"%CURL%"'

    #print("opts.curl_user_agent", opts.curl_user_agent)

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

    test = "if not exist {}".format(quoted(dest))

    if is_curl:
        cmd = " ".join([e for e in [curl,'-L', proxy, user_agent,'-o',quoted(dest), quoted(url)] if e != ""]) + "\n"
    elif is_wget:
        wget = "C:\\msys64\\usr\\bin\\wget.exe"
        cmd = " ".join([wget, '-O', quoted(dest), quoted(url)]) + "\n"

    if force or opts.download_test == False:
        exp = cmd
    else:
        exp = test + " " + cmd
    if keep:
        clean_exp = ""
    else:
        clean_exp = macro_clean_file(None, [dest], {}, None, opts)

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


def macro_unzip(name, args, kwargs, ret, opts):

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

        guess_dest = os.path.splitext(src)[0]
        is_file = os.path.splitext(guess_dest)[1] in ['.tar', '.lzma', '.gz', '.zip']
        if is_file:
            clean_exp = macro_clean_file(None, [guess_dest], {}, None, opts)
        else:
            #clean_exp = "if exist \"{}\" ".format(guess_dest) + macro_clean_dir(None, [guess_dest])
            clean_exp = macro_clean_dir(None, [guess_dest], {}, None, opts)

    return exp, clean_exp

def macro_zip(name, args, kwargs, ret, opts):
    src, dst = args
    if opts.zip_in_path:
        cmd = '7z'
    else:
        cmd = '"%P7Z%"'
    cmd = cmd + ' a -y {} {}\n'.format(quoted(dst), quoted(src))
    test = "if not exist {}".format(quoted(dst))
    if opts.zip_test:
        return test + ' ' + cmd
    else:
        return cmd

def macro_patch(name, args, kwargs, ret, opts: Opts):
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
    
def macro_mkdir(name, args, kwargs, ret, opts):
    arg = args[0]
    return "if not exist \"{}\" mkdir \"{}\"\n".format(arg, arg)

def macro_log(name, args, kwargs, ret, opts):
    arg = args[0]
    return "echo %DATE% %TIME% {} >> %~dp0log.txt\n".format(arg)

def macro_clean_dir(name, args, kwargs, ret, opts):
    arg = args[0]
    return "rmdir /s /q \"{}\"\n".format(arg)

def macro_rmdir(name, args, kwargs, ret, opts):
    return macro_clean_dir(name, args, opts)

def macro_clean_file(name, args, kwargs, ret, opts):
    arg = args[0]
    return "del /q \"{}\"\n".format(arg)


def if_group(cond, cmds):
    if len(cmds) == 1:
        return "if {} {}\n".format(cond, cmds[0])
    return """if {} (
{}
)
""".format(cond, "\n".join(cmds))


def macro_git_clone(name, args, kwargs, ret, opts: Opts):
    url = args[0]
    if len(args) > 1:
        dir = args[1]
    else:
        dir = None

    branch = kwargs.get('branch')
    
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
        cmds = [clone, "pushd {}".format(basename), checkout, "popd"]
    else:
        cmds = [clone]

    cmd = if_group(cond, cmds)
    if kwargs.get('pull'):
        cmd = cmd + """pushd {}
{} pull
popd
""".format(basename, git)

    return cmd

def macro_git_pull(name, args, kwargs, ret, opts):
    base = args[0]
    return textwrap.dedent("""\
    pushd {}
    git pull
    popd
    """).format(base)

def macro_set_path(name, args, kwargs, ret, opts):
    """
    if opts.github:
        return "echo PATH={}>> %GITHUB_ENV%\n".format(";".join(args))
    """
    return "set PATH=" + ";".join(args) + "\n"

def macro_set_var(name, args, kwargs, ret, opts):
    n, v = args
    if opts.github:
        return "echo {}={}>> %GITHUB_ENV%\n".format(n,v)
    else:
        return "set {}={}\n".format(n,v)

def macro_copy_file(name, args, kwargs, ret, opts):
    validate_args("copy_file", args, kwargs, ret, 2, 2, set(), False)
    src, dst = args
    return "copy /y {} {}\n".format(quoted(src), quoted(dst))

def macro_copy_dir(name, args, kwargs, ret, opts):
    validate_args("copy_dir", args, kwargs, ret, 2, 2, set(), False)
    src, dst = args
    return "xcopy /s /q /y /i {} {}\n".format(quoted(src), quoted(dst))

def macro_use_tool(name, args, kwargs, ret, opts):
    #print("opts", opts)
    paths1 = set()
    paths2 = set()
    for n in args:
        if n == 'xz':
            paths1.add('C:\\Program Files\\Git\\usr\\bin')
        elif n == 'tar':
            paths1.add('C:\\Program Files\\Git\\mingw64\\bin')
        elif n == 'ninja':
            if opts.github:
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
            if opts.github:
                paths1.add('C:\\Program Files\\CMake\\bin')
            else:
                paths1.add('C:\\cmake-3.23.2-windows-x86_64\\bin')
        elif n == 'patch':
            paths1.add('C:\\Program Files\\Git\\usr\\bin')
        elif n in ['python', 'aqt']:
            if opts.github:
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

def macro_install_tool(name, args, kwargs, ret, opts):
    res = []
    for n in args:
        if n == 'aqt':
            res.append('where aqt || pip install aqtinstall')
        elif n in ['mingw8', 'mingw81']:
            res.append('if not exist C:\\Qt\\Tools\\mingw810_64\\bin\\gcc.exe aqt install-tool --outputdir C:\\Qt windows desktop tools_mingw qt.tools.win64_mingw810')
        elif n == 'cmake':
            if opts.github:
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
            if opts.github:
                # windows-2022 C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe
                pass
            else:
                pass
        else:
            print("install_tool({}) not implemented".format(n))

    return "\n".join(res) + "\n"

def macro_call_vcvars(name, args, kwargs, ret, opts):
    if opts.github:
        return 'call "{}"\n'.format('C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\VC\\Auxiliary\\Build\\vcvars64.bat')
    else:
        return 'call "{}"\n'.format('C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat')

def macro_untar(name, args, kwargs, ret, opts):
    print(args)
    return ''

def macro_where(name, args, kwargs, ret, opts):
    res = []
    for n in args:
        res.append('echo where {}'.format(n))
        res.append('where {}'.format(n))
    return "\n".join(res) + "\n"

def macro_if_arg(name, args, kwargs, ret, opts):
    value, defname = args
    return 'if "%1" equ "{}" goto {}_begin\n'.format(value, defname)

def macro_github_release(name, args, kwargs, ret, opts, githubdata: GitHubData):
    githubdata.release = args
    return ''

def macro_github_checkout(name, args, kwargs, ret, opts, githubdata: GitHubData):
    githubdata.checkout = True
    return ''

def macro_github_upload(name, args, kwargs, ret, opts, githubdata: GitHubData):
    validate_args("github_upload", args, kwargs, ret, 1, 1, {"n", "name"})
    arg = args[0]
    if isinstance(arg, list):
        path = arg
    else:
        path = [arg]
    name = kwarg_value(kwargs, "n", "name")
    if name is None:
        name = os.path.splitext(os.path.basename(path[0]))[0]
    githubdata.upload = GitHubDataUpload(name, path)
    return ''

def macro_github_matrix(name, args, kwargs, ret, opts, githubdata: GitHubData):
    validate_args("github_matrix", args, kwargs, ret, 1, 1, set(), True)
    githubdata.matrix[ret] = args[0]
    #print("macro_github_matrix", githubdata.matrix)
    #print("macro_github_matrix", ret, githubdata.matrix)
    return ''

def macro_github_setup_msys2(name, args, kwargs, ret, opts, githubdata: GitHubData):
    validate_args("setup_msys2", args, kwargs, ret, 0, 0, {"m", "msystem", "i", "install", "u", "update"})
    msystem = kwarg_value(kwargs, "m", "msystem")
    install = kwarg_value(kwargs, "i", "install")
    update = kwarg_value(kwargs, "u", "update")
    if update is not None:
        update = {"false":False, "true":True}[update]
    githubdata.setup_msys2 = GitHubDataSetupMsys2(msystem, install, update)
    return ''

def macro_github_run(name, args, kwargs, ret, opts, githubdata: GitHubData):
    validate_args("github_run", args, kwargs, ret, -1, -1, {"s", "shell", "n", "name"})
    print(args)
    run = " ".join(args)
    shell = SHELL_CMD
    arg_shell = kwarg_value(kwargs, "s", "shell")
    name = kwarg_value(kwargs, "n", "name")
    if arg_shell:
        shell = {
            "cmd": SHELL_CMD,
            "msys2": SHELL_MSYS2,
        }[arg_shell]
    githubdata.steps.append(GithubShellStep(run, shell, name))
    return ''

def macro_pushd_cd(name, args, kwargs, ret, opts):
    if opts.github:
        return ''
    return 'pushd %~dp0\n'

def macro_popd_cd(name, args, kwargs, ret, opts):
    if opts.github:
        return ''
    return 'popd\n'

def macro_substr(name, args, kwargs, ret, opts):
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
    
def expand_macros(defs, thens, opts, githubdata: GitHubData):

    if 'clean' not in defs:
        defs['clean'] = []

    for name in defs.keys():
        for i, line in enumerate(defs[name]):
            for n in MACRO_NAMES:
                m = re.match('(.*=)?\\s*' + n + '\\s*\((.*)\)$', line)
                if m is not None:
                    ret, name_, args, kwargs = parse_macro(line)

                    if n.split("_")[0] == 'github':
                        exp = globals()['macro_' + n](name, args, kwargs, ret, opts, githubdata)
                    elif n in ['download', 'unzip']:
                        exp, clean_exp = globals()['macro_' + n](name, args, kwargs, ret, opts)
                        defs['clean'].append(clean_exp)
                    else:
                        exp = globals()['macro_' + n](name, args, kwargs, ret, opts)

                    if n in ['clean_dir', 'clean_file']:
                        defs[name][i] = ""
                        defs['clean'].append(exp)
                    else:
                        defs[name][i] = exp
                    continue

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

def create_id():
    alph0 = 'abcdefghijklmnopqrstuvwxyz'
    alph1 = 'abcdefghijklmnopqrstuvwxyz0123456789'
    id_ = None
    while id_ is None or id_ in used_ids:
        id_ = "".join([random.choice(alph0)] + [random.choice(alph1) for _ in range(3)])
    used_ids.add(id_)
    return id_

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
            print(line)
            return False
    return True

def defnames_ordered(defs, thens):
    res = ['main']
    """
    while len(res) < len(defs):
        if res[-1] in thens:
            res.append(thens[res[-1]])
        else:
            for n in defs.keys():
                if n not in res:
                    res.append(n)
                    break
    """

    #print("thens", thens)

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

def read_compile_write(src, dst_bat, dst_workflow, verbose=True, echo_off=True, warning=True):

    if isinstance(src, str):
        src_name = os.path.basename(src)
    else:
        src_name = 'untitled'

    dst_paths = []

    for github in [False, True]:
        githubdata = GitHubData()
        
        defs, thens, shells, opts = read(src, github)

        if github and not opts.github_workflow:
            continue

        if github:
            os.makedirs(os.path.dirname(dst_workflow), exist_ok=True)

        opts.github = github
        release = []
        expand_macros(defs, thens, opts, githubdata)

        if github:
            """
            if verbose and isinstance(src, str) and isinstance(dst_workflow, str):
                print("{} -> \n {}".format(src, "\n ".join([dst_workflow])))
            """
            
            #text = [l for l in render(defs, thens, opts, src_name, echo_off = False, warning = False).split('\n') if l != '']

            for i, line in enumerate(text):
                problem = '%~dp0'
                if problem in line:
                    raise Exception("{} does not work on github actions use %CD%, line {}".format(problem, line))

            steps = []
            if githubdata.checkout:
                steps.append({"uses": "actions/checkout@v3", "name": "checkout"})

            if githubdata.setup_msys2:
                steps.append(make_setup_msys2_step(githubdata.setup_msys2, opts))

            for name in defnames_ordered(defs, thens):
                text = filter_empty_lines(render_one(name, defs, thens, opts, src_name, echo_off = False, warning = False))
                #print(text)
                step = GithubShellStep(text, shells[name], name)
                #print("shells[name]", shells[name])
                steps.append(make_github_step(step, opts, githubdata))

            """
            if "\n".join(text).strip() != '':
                steps.append(make_main_step(text, os.path.splitext(src_name)[0], local=False))
            """

            """
            if len(githubdata.msys2) > 0:
                steps.append(make_msys2_step(githubdata.msys2, opts))
            """
            
            for step in githubdata.steps:
                steps.append(make_github_step(step, opts))

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
                #print("dst_path", dst_path)
                """
                with open(dst_path, 'w', encoding='utf=8') as f:
                    f.write(file_content)
                """
                write(dst_path, file_content)
                dst_paths.append(dst_path)

            """
            if verbose and isinstance(src, str) and isinstance(dst_bat, str):
                print("{} -> \n {}".format(src, "\n ".join(dst_paths)))
            """

            if githubdata.matrix:
                for key, values in githubdata.matrix.items():
                    #text[i] = text[i].replace(values[0], "${{ matrix." + key + " }}")
                    pattern = '[$][{][{]\\s*' + 'matrix.' + key + '\\s*[}][}]'
                    #print(pattern)
                    #print(">{}<".format(key))
                    
                    text = re.sub(pattern, values[0], text)

            #write(dst_bat, defs, thens, opts, src_name, echo_off, warning)
            write(dst_bat, text)
            dst_paths.append(dst_bat)

    if verbose and isinstance(src, str) and isinstance(dst_bat, str):
        print("{} -> \n {}".format(src, "\n ".join(dst_paths)))

    #print("dst_bat", dst_bat)
    #print("dst_workflow", dst_workflow)
