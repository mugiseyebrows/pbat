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
    'copy', 'xcopy', 'mkdir', 'rmdir', 'move', 'del',
    'git_clone', 'git_pull', 'patch', 
    'github_matrix', 'github_matrix_include', 'github_matrix_exclude', 
    'github_checkout', 'github_upload', 'github_release', 'github_cache',
    'github_setup_msys2', 'github_setup_node', 'github_setup_java',
    'if_arg', 
    'log', 
    'where',
    'set_var',
    'substr', 
    'use_tool', 'install_tool', 'call_vcvars',
    'use', 'install', 'add_path',
    'if_exist_return', 'clear_path',
    'test_exist', 'return'
]

DEPRECATED_MACRO_NAMES = [
    'github_rmdir', 'rm', 'move_file', 'copy_file', 'copy_dir', 'untar', 'clean_dir', 'clean_file'
]

try:
    from .parsedef import parse_def
    from .Opts import Opts
except ImportError:
    from parsedef import parse_def
    from Opts import Opts

def pat_spacejoin(*pat):
    SPACE = "\\s*"
    return SPACE.join(pat)

def parse_statement(line, opts: Opts) -> bool:

    m = re.match('^\\s*(env[_-]policy|debug|clean|download[_-]test|unzip[_-]test|zip[_-]test|github|github[_-]workflow)\\s+(off|on|true|false|1|0)\\s*$', line)
    if m is not None:
        optname = m.group(1).replace("-","_")
        optval = m.group(2) in ['on','true','1']
        setattr(opts, optname, optval)
        return True

    m = re.match('^\\s*([a-z0-9_]+[_-]in[_-]path)\\s+(off|on|true|false|1|0)\\s*$', line, re.IGNORECASE)
    if m:
        optname = m.group(1).replace("-","_")
        if hasattr(opts, optname):
            setattr(opts, optname, m.group(2) in ['on','true','1'])
            return True
    
    ID = "([0-9a-z_-]+)"
    START = "^"
    END = "\\s*$"

    pat = pat_spacejoin(START, 'msys2[_-]msystem', ID)
    m = re.match(pat, line, re.IGNORECASE)
    if m:
        opts.msys2_msystem = m.group(1).strip()
        return True

    pat = pat_spacejoin(START, 'github[_-]image', ID)
    m = re.match(pat, line)
    if m:
        opts.github_image = m.group(1).strip()
        return True
    
    pat = pat_spacejoin(START, 'github[_-]on', ID)
    m = re.match(pat, line)
    if m:
        trigger = m.group(1).strip()
        opts.github_on = {
            "push": ON_PUSH,
            "release": ON_RELEASE,
            "tag": ON_TAG
        }[trigger]
        return True

    m = re.match('^curl_user_agent\\s+(safari|chrome|mozilla)$', line)
    if m is not None:
        opts.curl_user_agent = m.group(1)
        return True
    
    m = re.search('^curl_proxy\\s+(.*)$', line)
    if m is not None:
        opts.curl_proxy = m.group(1).rstrip()
        return True
    
    return False

def parse_order(line):
    m = re.match('^\\s*order\\s+(.*)$', line)
    if m:
        return [n.strip() for n in re.split('\\s+', m.group(1)) if n.strip() != ""]

def update_chain(script, chain, tested):
    name = next(filter(lambda n: n not in tested, chain), None)
    if name is None:
        return False
    tested.add(name)
    def get_deps(name):
        return script.function(name)._deps
    ins = [n for n in get_deps(name) if n not in chain]
    ix = chain.index(name)
    for i, n in enumerate(ins):
        chain.insert(ix + i, n)
    return True

class Function:
    def __init__(self, name, then, deps, shell, condition):
        self._name = name
        self._then = then
        self._deps = deps
        self._shell = shell
        self._condition = condition
        self._body = []
        self._macro_names = None
        
    def append(self, line):
        self._body.append(line)

class Script:

    def __init__(self):
        self._functions = dict()
        #self._statements = []
        self._opts = Opts()
        self._function = None
        self._order = None

    def function(self, name) -> Function:
        return self._functions[name]

    def append(self, i, line):
        # todo redefinitions
        if re.match('\\s*#', line):
            print("# comments are deprecated, use :: or rem, line {}".format(i))
            return

        if parse_statement(line, self._opts):
            return
        order = parse_order(line)
        if order:
            self._order = order
            return
        def_ = parse_def(line)
        if def_ is not None:
            name, then, deps_, shell, condition = def_
            function = Function(name, then, deps_, shell, condition)
            self._function = function
            self._functions[name] = function
            return
        if self._function:
            self._function.append(line)
        else:
            if line.strip() != '':
                print("not used line: ", line)

    def compute_order(self):
        thens_ = dict()
        if self._order is None:
            main = self._function._name
            chain = [main]
            tested = set()
            while update_chain(self, chain, tested):
                pass
            for a, b in zip(chain, chain[1:]):
                thens_[a] = b
            keys = chain
        else:
            raise ValueError("not implemented")
        for i in range(1000):
            changed = False
            for a, b in thens_.items():
                if a in keys:
                    if b not in keys:
                        keys.append(b)
                        changed = True
            if not changed:
                break
        for n in self._functions.keys():
            if n not in keys:
                print("warning: not reachable {}".format(n))
        return keys, thens_

def load_lines(path):
    with open(path, encoding='utf-8') as f:
        return list(f)

def insert_includes(dirname, lines, included: set[str]):
    res = []
    changed = False
    for line in lines:
        m = re.match('\\s*include\((.*)\)', line)
        if m:
            name = m.group(1)
            if os.path.splitext(name)[1] == '':
                name = name + '.pbat'
            p = os.path.join(dirname, name)
            if p not in included:
                if not os.path.exists(p):
                    raise ValueError("{} ({}) not exist".format(p, name))
                res.extend(load_lines(p))
                included.add(p)
                changed = True
        else:
            res.append(line)
    return res, changed

def parse_script(src, github) -> Script:
    # todo includes
    dirname = os.path.dirname(src)
    lines = load_lines(src)
    included = set()
    included.add(src)
    while True:
        lines, changed = insert_includes(dirname, lines, included)
        if not changed:
            break
    lines[-1] = lines[-1] + "\n"
    script = Script()
    for i, line in enumerate(lines):
        script.append(i, line)
    script._opts.github = github
    return script
