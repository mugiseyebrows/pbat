import re
import os

ON_PUSH = 1
ON_TAG = 2
ON_RELEASE = 3

MACRO_NAMES = [
    'pushd_cd', 'popd_cd', 
    'find_app',
    'download', 
    'zip', 'unzip',
    'set_path', 
    'foreach',
    'copy_file', 'copy_dir', 'mkdir', 'rmdir', 'rm', 'move_file',
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
    'use_tool', 'install_tool', 'call_vcvars',
    'use', 'install', 'add_path',
    'if_exist_return', 'clear_path'
]

try:
    from .parsedef import parse_def
    from .Opts import Opts
except ImportError:
    from parsedef import parse_def
    from Opts import Opts

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

def pat_spacejoin(*pat):
    SPACE = "\\s*"
    return SPACE.join(pat)

# defs, deps, thens, top, order, shells, opts, conditions
def parse_script(src, github):
    
    def_line = dict()

    defs = dict()

    deps = dict()

    thens = dict()

    shells = dict()

    conditions = dict()

    opts = Opts()

    top = []

    order = None

    lines = []

    def pattern_join(*args):
        return "".join(args)

    def process_line(line, cwd):

        PBAT_FILE = "([0-9a-z_-]+[.]pbat)"
        START = "^"

        pat = pat_spacejoin(START, 'include', '\\(', PBAT_FILE, '\\)')

        m = re.match(pat, line, re.IGNORECASE)
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

    has_defs = False
    for line in lines:
        if re.match('^\\s*def\\s+', line):
            has_defs = True
            break
    if not has_defs:
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

        ID_NOCAP = "[0-9a-z_]+"
        ID = "([0-9a-z_]+)"
        SPACE = "\\s*"
        START = "^"

        pat_w_ret = pat_spacejoin(START,ID_NOCAP,"=",ID)
        pat_wo_ret = pat_spacejoin(START,ID)

        m1 = re.match(pat_w_ret, line, re.IGNORECASE)
        m2 = re.match(pat_wo_ret, line, re.IGNORECASE)

        name = None
        if m1:
            name = m1.group(1)
        elif m2:
            name = m2.group(1)

        if name in MACRO_NAMES:
            line = unsplit_line(lines, i, skip)
            lines_.append(line)
            used.add(name)
            """
            if name == 'download':
                m = re.search(':({})\\s*='.format("|".join(CHECKSUM_ALGS)), line)
                if m:
                    alg = m.group(1)
                    chksum_used.add(alg)
            """
        else:
            lines_.append(line)


    lines = lines_
    #print(lines)

    for i, line in enumerate(lines):
        if re.match("\\s*".join(["", "use", "\\(", "7z", "\\)"]), line):
            opts.zip_in_path = True
        if re.match("\\s*".join(["", "use", "\\(", "git", "\\)"]), line):
            opts.git_in_path = True
        if re.match("\\s*".join(["", "use", "\\(", "sed", "\\)"]), line):
            opts.use_sed = True
        if re.match("\\s*".join(["", "use", "\\(", "diff", "\\)"]), line):
            opts.use_diff = True

    name = None
    for i, line in enumerate(lines):
        #line = line.strip()
        m = re.match('^\\s*(debug|clean|download[_-]test|unzip[_-]test|zip[_-]test|github|github[_-]workflow)\\s+(off|on|true|false|1|0)\\s*$', line)
        if m is not None:
            optname = m.group(1).replace("-","_")
            optval = m.group(2) in ['on','true','1']
            setattr(opts, optname, optval)
            continue

        m = re.match('^\\s*([a-z0-9_]+[_-]in[_-]path)\\s+(off|on|true|false|1|0)\\s*$', line, re.IGNORECASE)
        if m:
            optname = m.group(1).replace("-","_")
            if hasattr(opts, optname):
                setattr(opts, optname, m.group(2) in ['on','true','1'])
                continue
        
        ID = "([0-9a-z_-]+)"
        START = "^"
        END = "\\s*$"

        pat = pat_spacejoin(START, 'msys2[_-]msystem', ID)
        m = re.match(pat, line, re.IGNORECASE)
        if m:
            opts.msys2_msystem = m.group(1).strip()
            continue

        pat = pat_spacejoin(START, 'github[_-]image', ID)
        m = re.match(pat, line)
        if m:
            opts.github_image = m.group(1).strip()
            continue
        
        pat = pat_spacejoin(START, 'github[_-]on', ID)
        m = re.match(pat, line)
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
        START = "^"

        pat = pat_spacejoin(START, 'def\\s+', ID)

        m = re.match(pat, line, re.IGNORECASE)
        if m is not None:
            
            name, then, deps_, shell, condition = parse_def(line)
            #print("name {} then {} deps_ {} shell {}".format(name, then, deps_, shell))

            #deps_ = []
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

            if condition is not None:
                conditions[name] = condition

            #print("line {} def {} depends on {} then {} shell {}".format(i, name, deps_, then, shell))
            
            continue
        
        # todo calculate order after parse
        m = re.match('^\\s*order\\s+(.*)$', line)
        if m is not None:
            order = [n.strip() for n in re.split('\\s+', m.group(1)) if n.strip() != ""]
            
            
            """
            names_ = insert_deps(names, deps)
            for n1, n2 in zip(names_, names_[1:]):
                thens[n1] = n2
            opts.main_def = names[0]
            """
            #print("main_def", main_def)
            continue
        if line == '':
            continue
        if re.match("^\\s*#", line):
            continue

        m = re.match('(\\s*)sed (.*)', line)
        if m and opts.use_sed:
            line = m.group(1) + '"%SED%" ' + m.group(2)
        
        m = re.match('(\\s*)diff (.*)', line)
        if m and opts.use_diff:
            line = m.group(1) + '"%DIFF%" ' + m.group(2)

        if name is not None:
            defs[name].append(line + "\n")

    #print("thens", thens)
    for n1, n2 in thens.items():
        if n1 not in defs:
            if n1 != "end":
                print("missing def {}".format(n1))
        if n2 not in defs:
            if n2 != "end":
                print("missing def {}".format(n2))
    
    #main_def = opts.main_def if opts.main_def else 'main'

    if 'download' in used and not opts.curl_in_path and not github:
        #defs[main_def] = ['CURL = find_app([C:\\Windows\\System32\\curl.exe, C:\\Program Files\\Git\\mingw64\\bin\\curl.exe, C:\\Program Files\\Git\\mingw32\\bin\\curl.exe])\n'] + defs['main']
        top.extend(['CURL = find_app([C:\\Windows\\System32\\curl.exe, C:\\Program Files\\Git\\mingw64\\bin\\curl.exe, C:\\Program Files\\Git\\mingw32\\bin\\curl.exe])\n'])
    
    
    """
    if ('zip' in used or 'unzip' in used) and not opts.zip_in_path and not github:
        defs['main'] = ['P7Z = find_app([C:\\Program Files\\7-Zip\\7z.exe])\n'] + defs['main']
    """

    if 'patch' in used and not opts.patch_in_path:
        top.extend(['PATCH = find_app([C:\\Program Files\\Git\\usr\\bin\\patch.exe])\n'])
    
    """
    if 'untar' in used and not opts.tar_in_path:
        append_top(['TAR = find_app([C:\\Program Files\\Git\\usr\\bin\\tar.exe])\n'])
        append_top(['GZIP = find_app([C:\\Program Files\\Git\\usr\\bin\\gzip.exe])\n'])
    """

    if 'msys2' in shells.values():
        if github:
            pass
        else:
            top.extend([
                'MSYS2 = find_app([C:\\msys64\\usr\\bin\\bash.exe])\n',
                'set_var(CHERE_INVOKING, yes)\n'
            ])
    if 'python' in shells.values():
        if github:
            pass
        else:
            top.extend(["""PYTHON = find_app([
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
"""])

    """
    if 'pwsh' in shells.values():
        if github:
            pass
        else:
            append_top(["PWSH = find_app([C:\\Program Files\\PowerShell\\7\\pwsh.exe])\n"])
    """

    if 'node' in shells.values():
        if github:
            pass
        else:
            append_top(["NODE = find_app([C:\\Program Files\\nodejs\\node.exe])\n"])

    """
    for alg in chksum_used:
        exe = alg + 'sum.exe'
        var = (alg + 'sum').upper()
        defs[main_def] = ['{} = find_app([C:\\Program Files\\Git\\usr\\bin\\{}])\n'.format(var, exe)] + defs[main_def]
    """
    
    return defs, deps, thens, top, order, shells, opts, conditions