from dataclasses import dataclass, field
import enum
import os
import re
import argparse
import random
import textwrap
import glob
import yaml

ON_PUSH = 1
ON_TAG = 2
WINDOWS_2019 = "windows-2019"
WINDOWS_2022 = "windows-2022"

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

def make_upload_step(name, artifacts):
    return {
        "name": "upload",
        "uses": "actions/upload-artifact@v3",
        "with": {
            "name": name,
            "path": str_or_literal(artifacts)
        }
    }

def save_workflow(path, steps, on = ON_TAG, runs_on = WINDOWS_2019):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if on == ON_TAG:
        on_ = {"push":{"tags":"*"}}
    else:
        on_ = "push"
    data = {"name":"main","on":on_,"jobs":{"main": {"runs-on":runs_on,"steps":steps}}}
    with open(path, 'w', encoding='utf-8') as f:
        f.write(yaml.dump(data, None, Dumper=Dumper, sort_keys=False))

MACRO_NAMES = ['find_app', 'find_file', 'download', 'download2', 'unzip', 'mkdir', 'rmdir', 'log', 
'find_app2', 'clean_dir', 'clean_file', 'find_app3', 'zip', 'git_clone', 'git_pull', 'set_path', 'set_var', 
'copy_dir', 'use_tool', 'install_tool', 'call_vcvars', 'github_checkout', 'github_release', 'github_upload']

class Data:
    def __init__(self) -> None:
        self.arg = ''
        self.res = []
        self.array = []
        self.in_array = False
        self.in_str = False
        self.ignore_comma = False

    def flush_arg(self):
        if self.in_array:
            self.array.append(unquoted(self.arg))
            self.arg = ''
        else:
            self.res.append(unquoted(self.arg))
            self.arg = ''

    def begin_array(self):
        self.in_array = True

    def end_array(self):
        self.flush_arg()
        self.res.append(self.array)
        self.array = []
        self.in_array = False
        self.ignore_comma = True

    def comma(self):
        if self.in_str:
            self.arg += ','
        elif self.ignore_comma:
            self.ignore_comma = False
        else:
            self.flush_arg()

    def quotes(self):
        self.in_str = not self.in_str

    def char(self, c):
        self.arg += c

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

@dataclass
class GitHubData:
    checkout: bool = False
    release: list = field(default_factory=list)
    upload: list = field(default_factory=list)

def parse_args(s):
    data = Data()
    for c in s:
        if c == '[':
            data.begin_array()
        elif c == ']':
            data.end_array()
        elif c == ',':
            data.comma()
        elif c == '"':
            data.quotes()
        else:
            data.char(c)
    data.comma()
    return data.res

def test_parse_args():
    s = "[foo, bar, \"baz\"], qix"
    r = parse_args(s)
    assert r == [["foo","bar","baz"],"qix"]
    s = "[foo, bar, \"baz\"]"
    r = parse_args(s)
    assert r == [["foo","bar","baz"]]
    s = "foo, \"bar, baz\""
    r = parse_args(s)
    assert r == [["foo","bar, baz"]]

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

def read(src):

    def_line = dict()

    defs = dict()

    deps = dict()

    thens = dict()
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

    # unwrap
    for i, line in enumerate(lines):
        if i in skip:
            continue
        m = re.match('^\\s*([0-9a-z_]+)', line)
        if m and m.group(1) in MACRO_NAMES:
            op, cl = count_parenthesis(line)
            if op == cl:
                lines_.append(line)
            else:
                for j in range(i+1, len(lines)):
                    skip.add(j)
                    op_, cl_ = count_parenthesis(lines[j])
                    op += op_
                    cl += cl_
                    if op == cl:
                        line = " ".join([lines[k].strip() for k in range(i, j+1)]) + "\n"
                        lines_.append(line)
                        break
        else:
            lines_.append(line)

    lines = lines_
    #print(lines)

    name = None
    for i, line in enumerate(lines):
        line = line.strip()
        m = re.match('^(debug|clean|curl_in_path|download_test|unzip_test|zip_test|github)\\s+(off|on|true|false|1|0)$', line)
        if m is not None:
            setattr(opts, m.group(1), m.group(2) in ['on','true','1'])
            continue

        m = re.match('^curl_user_agent\\s+(safari|chrome|mozilla)$', line)
        if m is not None:
            opts.curl_user_agent = m.group(1)
            continue
        m = re.search('^curl_proxy\\s+(.*)$', line)
        if m is not None:
            opts.curl_proxy = m.group(1).rstrip()
            continue
        
        m = re.match('^def\\s+([a-z0-9_]+)\\s*(then\\s*[a-z0-9_]+)?\\s*(depends\\s*on\\s*[a-z0-9_ ]+)?', line)
        if m is not None:
            name = m.group(1)
            then = m.group(2).split(' ')[-1] if m.group(2) else None
            deps_ = re.split('\\s+', m.group(3))[2:] if m.group(3) else None

            if deps_ is not None:
                deps[name] = deps_

            if name in defs:
                print("redefinition {} on line {}, first defined on line {}".format(name, i+1, def_line[name]))
            def_line[name] = i
            defs[name] = []

            if then is not None:
                thens[name] = then
            continue
        """
        m = re.match('^def\\s+([a-z0-9_]+)$', line)
        if m is not None:
            name = m.group(1)
            defs[name] = []
            thens[name] = "end"
            continue
        """
        m = re.match('^order\\s+(.*)$', line)
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

    for k, v in thens.items():
        m = re.match('next\((.*)\)', v)
        if m is not None:
            n = m.group(1).strip()
            if n in thens:
                thens[k] = thens[n]
                #print("{} is {}".format(v, thens[n]))
            else:
                print("cannot expand {}".format(v))

    for n1, n2 in thens.items():
        if n1 not in defs:
            if n1 != "end":
                print("missing def {}".format(n1))
        if n2 not in defs:
            if n2 != "end":
                print("missing def {}".format(n2))

    return defs, thens, opts

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

def find_file(name, items, label):
    label_success = "{}_find_app_found".format(name)
    tests = ["if exist \"{}\" goto {}\n".format(item, label_success) for item in items]
    puts = []
    return "".join(tests) + "goto {}_begin\n".format(label) + ":" + label_success + "\n" + "".join(puts)

def without(vs, v):
    return [e for e in vs if e != v]

def render(defs, thens, opts: Opts, src_name, echo_off=True, warning=True):
    res = []
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
        res.append("".join(lines))
        res.append(":{}_end\n".format(name))
        res.append("goto {}\n".format(thens[name] + "_begin" if name in thens and thens[name] not in ["end","exit"] else "end"))
        res.append("\n")

    while(True):
        ok1 = remove_unused_labels(res)
        ok2 = remove_redundant_gotos(res)
        if not ok1 and not ok2:
            break

    return "".join(res)

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

def macro_find_app(name, args, opts):
    #print(args)
    return macro_find_app3(name, args, opts)
    """
    app = args[0]
    items = args[1]
    label = args[2]
    label_success = "{}_find_app_found".format(name)
    label_append = "{}_find_app_append".format(name)
    test = "where {} && goto {}\n".format(app, label_success)
    tests = ["if exist \"{}\" goto {}\n".format(item, label_append) for item in items]
    puts = ["if exist \"{}\" set PATH={};%PATH%\n".format(item, os.path.dirname(item)) for item in items]
    return test + "".join(tests) + "goto {}_begin\n".format(label) + ":" + label_append + "\n" + "".join(puts) + ":" + label_success + "\n"
    """

def macro_find_app2(name, args, opts):
    env_name = args[0]
    app = args[1]
    items = args[2]
    label = args[3]

    label_success = "{}_find_app_found".format(name)

    tests = ["if exist \"{}\" goto {}_find_app_found_{}\n".format(item, name, i+1) for i,item in enumerate(items)]
    
    founds = [
        "".join([":{}_find_app_found_{}\n".format(name, i+1), 
        "set {}={}\n".format(env_name, item),
        "goto {}\n".format(label_success)]) for i,item in enumerate(items)]

    test0 = "where {} && goto {}_find_app_found_0\n".format(app, name)

    found0 = "".join([":{}_find_app_found_{}\n".format(name, 0), 
        "set {}={}\n".format(env_name, app),
        "goto {}\n".format(label_success)])

    return test0 + "".join(tests) + "goto {}_begin\n".format(label) + found0 + "".join(founds) + ":{}\n".format(label_success)

def macro_find_app3(name, args, opts):
    env_name = args[0]
    items = args[1]
    label = args[2]
    tests = ["if exist \"{}\" set {}={}\n".format(item, env_name, item) for i,item in enumerate(reversed(items))]
    tests = tests + ['if not defined {} goto {}_begin\n'.format(env_name, label)]
    return "".join(tests)

def macro_find_file(name, args, opts):
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

def macro_download(name, args, opts: Opts):
    url = args[0]
    dest = args[1]
    force = "force" in args
    keep = "keep" in args
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
        clean_exp = macro_clean_file(None, [dest], opts)
    return exp, clean_exp

def macro_download2(name, args, opts, checksums):
    url = args[0]
    dest = args[1]
    keep = "keep" in args
    if dest not in checksums:
        print("cant find {} in checksums, validation skipped".format(dest))
        return macro_download(name, args)
    if keep:
        clean_exp = ""
    else:
        clean_exp = macro_clean_file(None, [dest], opts)
    exp = """if not exist \"{}\" (
\"%CURL%\" -L -o \"{}\" {}
call :verify_checksum_sha1 \"{}\" {}
if errorlevel 1 exit /b 1
)
""".format(dest, dest, url, dest, checksums[dest], dest)
    return exp, clean_exp

def macro_unzip(name, args, opts: Opts):
    src = args[0]
    test = args[1] if len(args) > 1 and args[1] != 'keep' else None
    force = "force" in args
    keep = "keep" in args
    if force or opts.unzip_test == False:
        exp = "7z x -y {}\n".format(quoted(src))
    elif test is not None:
        exp = "if not exist {} 7z x -y {}\n".format(quoted(test), quoted(src))
    else:
        exp = "7z x -y {}\n".format(quoted(src))
    if keep:
        clean_exp = ""
    else:
        #print(os.path.splitext(src)[1])

        guess_dest = os.path.splitext(src)[0]
        is_file = os.path.splitext(guess_dest)[1] in ['.tar', '.lzma', '.gz', '.zip']
        if is_file:
            clean_exp = macro_clean_file(None, [guess_dest], opts)
        else:
            #clean_exp = "if exist \"{}\" ".format(guess_dest) + macro_clean_dir(None, [guess_dest])
            clean_exp = macro_clean_dir(None, [guess_dest], opts)
    return exp, clean_exp

def macro_zip(name, args, opts: Opts):
    src, dst = args
    cmd = "7z a -y {} {}\n".format(quoted(dst), quoted(src))
    test = "if not exist {}".format(quoted(dst))
    if opts.zip_test:
        return test + ' ' + cmd
    else:
        return cmd

def macro_mkdir(name, args, opts):
    arg = args[0]
    return "if not exist \"{}\" mkdir \"{}\"\n".format(arg, arg)

def macro_log(name, args, opts):
    arg = args[0]
    return "echo %DATE% %TIME% {} >> %~dp0log.txt\n".format(arg)

def macro_clean_dir(name, args, opts):
    arg = args[0]
    return "rmdir /s /q \"{}\"\n".format(arg)

def macro_rmdir(name, args, opts):
    return macro_clean_dir(name, args, opts)

def macro_clean_file(name, args, opts):
    arg = args[0]
    return "del /q \"{}\"\n".format(arg)

def macro_git_clone(name, args, opts):
    url, branch = args
    basename = os.path.splitext(os.path.basename(url))[0]
    return textwrap.dedent("""\
    if not exist {} (
    git clone {}
    pushd {}
    git checkout {}
    popd
    )
    """).format(basename, url, basename, branch)

def macro_git_pull(name, args, opts):
    base = args[0]
    return textwrap.dedent("""\
    pushd {}
    git pull
    popd
    """).format(base)

def macro_set_path(name, args, opts):
    if opts.github:
        return "echo PATH={}>> %GITHUB_ENV%\n".format(";".join(args))
    return "set PATH=" + ";".join(args) + "\n"

def macro_set_var(name, args, opts):
    n, v = args
    if opts.github:
        return "echo {}={}>> %GITHUB_ENV%\n".format(n,v)
    else:
        return "set {}={}\n".format(n,v)

def macro_copy_dir(name, args, opts):
    src, dst = args
    return "xcopy /s /q /y /i {} {}\n".format(quoted(src), quoted(dst))

def macro_use_tool(name, args, opts):
    #print("opts", opts)
    paths = set()
    for n in args:
        if n == 'xz':
            paths.add('C:\\Program Files\\Git\\usr\\bin')
        elif n == 'tar':
            paths.add('C:\\Program Files\\Git\\mingw64\\bin')
        elif n == 'ninja':
            if opts.github:
                pass
            else:
                paths.add('C:\\Ninja')

    if len(paths) > 0:
        return "set PATH=" + ";".join(list(paths) + ['%PATH%']) + "\n"
    return ""

def macro_install_tool(name, args, opts):
    return ''

def macro_call_vcvars(name, args, opts: Opts):
    if opts.github:
        return 'call "{}"\n'.format('C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise\\VC\\Auxiliary\\Build\\vcvars64.bat')
    else:
        return 'call "{}"\n'.format('C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat')

def macro_untar(name, args, opts):
    print(args)
    return ''

def macro_github_release(name, args, opts, githubdata: GitHubData):
    githubdata.release = args
    return ''

def macro_github_checkout(name, args, opts, githubdata: GitHubData):
    githubdata.checkout = True
    return ''

def macro_github_upload(name, args, opts, githubdata: GitHubData):
    githubdata.upload = args
    return ''

def expand_macros(defs, thens, opts, checksums, githubdata: GitHubData):

    if 'clean' not in defs:
        defs['clean'] = []

    for name in defs.keys():
        for i, line in enumerate(defs[name]):
            for n in MACRO_NAMES:
                m = re.match('^' + n + '\\s*\((.*)\)$', line)
                if m is not None:
                    args = parse_args(m.group(1))
                    if n.split("_")[0] == 'github':
                        exp = globals()['macro_' + n](name, args, opts, githubdata)
                    elif n in ['download', 'unzip']:
                        exp, clean_exp = globals()['macro_' + n](name, args, opts)
                        defs['clean'].append(clean_exp)
                    elif n == 'download2':
                        exp, clean_exp = globals()['macro_' + n](name, args, checksums)
                        defs['clean'].append(clean_exp)
                    else:
                        exp = globals()['macro_' + n](name, args, opts)

                    if n in ['clean_dir', 'clean_file']:
                        defs[name][i] = ""
                        defs['clean'].append(exp)
                    else:
                        defs[name][i] = exp
                    continue
    defs['clean'] = ['pushd %~dp0\n'] + defs['clean'] + ['popd\n']

def write(path, defs, thens, opts, src_name, echo_off, warning):
    text = render(defs, thens, opts, src_name, echo_off, warning)
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

def append_verify_checksum(defs, thens):
    tmpfile = '%TEMP%\\checksum_{}.txt'.format(create_id())
    exp = [line + "\n" for line in """:verify_checksum_sha1
if not defined SHA1SUM (
    echo SHA1SUM not defined
    exit /b 1
)
"%SHA1SUM%" "%1" > {}
for /f %%i in ({}) do if "%%i" equ "%2" exit /b 0
echo checksum fail "%1"
del /q "%1"
exit /b 1
""".format(tmpfile, tmpfile).split("\n")]
    defs['verify_checksum_sha1'] = exp

def read_checksums(path):
    if isinstance(path, str):
        base = os.path.dirname(path)
    else:
        base = os.getcwd()
    checksums = dict()
    path = os.path.join(base, "sha1sum.txt")
    if not os.path.exists(path):
        return checksums
    try:
        with open(path) as f:
            for line in f:
                s, n = line.split(" ", 1)
                n = unquoted(n.lstrip("*"))
                checksums[n] = s
    except Exception as e:
        print(e)
    return checksums


class Dumper(yaml.Dumper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # disable resolving on as tag:yaml.org,2002:bool (disable single quoting)
        cls = self.__class__
        cls.yaml_implicit_resolvers['o'] = []


def pack_step(cmds, name, local):
    if local:
        return "rem {}\n".format(name) + "\n".join(cmds) + "\n"
    else:
        return {
            "name": name, 
            "shell": "cmd", 
            "run": literal_str("\n".join(cmds) + "\n")
        }

def read_compile_write(src, dst_bat, dst_workflow, verbose=True, echo_off=True, warning=True):

    #print("dst_workflow", dst_workflow)
    os.makedirs(os.path.dirname(dst_workflow), exist_ok=True)

    if isinstance(src, str):
        src_name = os.path.basename(src)
    else:
        src_name = 'untitled'

    for github in [False, True]:
        githubdata = GitHubData()
        defs, thens, opts = read(src)
        checksums = read_checksums(src)
        opts.github = github
        release = []
        expand_macros(defs, thens, opts, checksums, githubdata)
        append_verify_checksum(defs, thens)
            
        if github:
            if verbose and isinstance(src, str) and isinstance(dst_workflow, str):
                print("{} -> {}".format(src, dst_workflow))
            text = [l for l in render(defs, thens, opts, src_name, echo_off = False, warning = False).split('\n') if l != '']
            build_step = pack_step(text, os.path.splitext(src_name)[0], local=False)
            steps = []
            if githubdata.checkout:
                steps.append({"uses": "actions/checkout@v3", "name": "checkout"})
            steps.append(build_step)
            if len(githubdata.upload) > 0:
                name = githubdata.upload[0]
                artifacts = githubdata.upload[1:]
                steps.append(make_upload_step(name, artifacts))
            if len(githubdata.release) > 0:
                steps.append(make_release_step(githubdata.release))
            save_workflow(dst_workflow, steps, ON_PUSH, WINDOWS_2022)
        else:
            if verbose and isinstance(src, str) and isinstance(dst_bat, str):
                print("{} -> {}".format(src, dst_bat))
            write(dst_bat, defs, thens, opts, src_name, echo_off, warning)

    #print("dst_bat", dst_bat)
    #print("dst_workflow", dst_workflow)
