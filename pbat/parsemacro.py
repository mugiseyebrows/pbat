import os
from lark import Lark, Tree, Token
from lark.exceptions import LarkError
import unittest
import re

if os.environ.get("DEV_PBAT") == "1":
    base = os.path.dirname(__file__)
    path = os.path.join(base, "macro.lark")
    with open(path, encoding='utf-8') as f:
        GRAMMAR = f.read()
else:
    GRAMMAR = """
start: (ret_name "=")? fn_name ( "(" arg ("," arg)* ")" | "(" ")" )

name: NAME

ret_name: NAME

fn_name: NAME

?arg: parg | kwarg

parg: ARG | list

kwarg: ":" name ("=" parg)?

list: "[" parg ("," parg)* "]" | "[" "]"

NAME: /[a-z0-9_-]+/i

ARG: /([^",()\\[\\]:\\s][^",()\\[\\]]*)|("[^"]*")/

WS: /[ \\t\\f\\r\\n]/+

%ignore WS    
"""

parser = Lark(GRAMMAR)

def _unquote(s):
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s

def find_data(tree, data, trace = False):
    if trace:
        print([child.data for child in tree.children])

    return [child for child in tree.children if hasattr(child, 'data') and child.data == data]

def find_tokens(tree, type):
    return [child for child in tree.children if isinstance(child, Token) and child.type == type]

def parse_kwarg(tree):
    name = None
    value = True
    for item in find_data(tree, 'name'):
        name = item.children[0].value.strip()
    for item in find_data(tree, 'parg'):
        value = parse_parg(item)
    return name, value

def parse_list(tree):
    return [parse_parg(item) for item in find_data(tree, 'parg')]

def parse_parg(tree):
    for item in find_tokens(tree, 'ARG'):
        return _unquote(item.value.strip())
    for item in find_data(tree, 'list'):
        return parse_list(item)

class ParseMacroError(Exception):
    pass

def parse_macro2(s):

    try:
        tree = parser.parse(s)
    except LarkError as e:
        raise ParseMacroError(e)

    ret_name = None
    fn_name = None

    for item in find_data(tree, 'ret_name'):
        ret_name = item.children[0].value.strip()
    for item in find_data(tree, 'fn_name'):
        fn_name = item.children[0].value.strip()

    pargs = [parse_parg(item) for item in find_data(tree, 'parg')]
    kwargs = {}

    for item in find_data(tree, 'kwarg'):
        k, v = parse_kwarg(item)
        kwargs[k] = v

    return ret_name, fn_name, pargs, kwargs

def parse_args(s: str):
    args: list[str] = []
    arg = []
    in_str = False
    for c in s:
        if c == '"':
            in_str = not in_str
            arg.append(c)
        elif c == ',':
            if not in_str:
                if len(arg) > 0:
                    args.append(''.join(arg))
                arg = []
            else:
                arg.append(c)
        else:
            arg.append(c)

    if len(arg) > 0:
        args.append(''.join(arg))
    arg = []
    
    posargs = []
    kwargs = dict()
    for arg in args:
        m = re.match('\\s*:(.*)=(.*)', arg)
        if m:
            n = m.group(1).strip()
            v = m.group(2).strip()
            kwargs[n] = _unquote(v)
            continue
        m = re.match('\\s*:(.*)', arg)
        if m:
            n = m.group(1).strip()
            kwargs[n] = True
            continue
        posargs.append(_unquote(arg.strip()))
    return posargs, kwargs

def parse_macro(line: str):
    """
    returns retname fnname posargs kwargs
    """
    RXID = '\\s*([a-zA-Z0-9_]+)\\s*'
    m = re.match(RXID + '=' + RXID + '\\((.*)\\)\\s*', line)
    if m:
        retname = m.group(1).strip()
        fnname = m.group(2).strip()
        args = m.group(3).strip()
    if m is None:
        m = re.match(RXID + '\\((.*)\\)\\s*', line)
        if m is None:
            raise ValueError("invalid macro", line)
        retname = None
        fnname = m.group(1).strip()
        args = m.group(2).strip()
    posargs, kwargs = parse_args(args)
    return retname, fnname, posargs, kwargs

class TestParseArgs(unittest.TestCase):
    def test_1(self):
        expected = ["foo", "bar"], dict()
        self.assertEqual(parse_args(' foo, "bar" '), expected)

    def test_2(self):
        expected = ["foo", "b,ar"], dict()
        self.assertEqual(parse_args('foo,"b,ar"'), expected)

    def test_3(self):
        expected = ['one', 't w o', 'three', 'f o u r '], {'kw': '7', 'kw2': True}
        self.assertEqual(parse_args('one, t w o, :kw = 7, three, "f o u r ", :kw2'), expected)
    
class TestParse(unittest.TestCase):

    def test_ret(self):
        expected = "res", "fn", [], {}
        self.assertEqual(parse_macro('res = fn()'), expected)

    def test_kwargs_bool(self):
        expected = None, "fn", [], {"foo": True, "bar": True, "baz": True}
        self.assertEqual(parse_macro('fn ( :foo , :bar , :baz )'), expected)

    def test_kwargs_value(self):
        expected = None, "fn", [], {"foo": "one", "bar": "two", "baz": "three"}
        self.assertEqual(parse_macro('fn ( :foo = one , :bar = two , :baz = "three" )'), expected)
        
    def test_pargs(self):
        expected = None, "fn", ["foo","bar","baz"], {}
        self.assertEqual(parse_macro('fn ( foo , bar , "baz" )'), expected)

    def test_kwargs_pargs(self):
        expected = None, "fn", ["foo","baz"], {"bar": "three"}
        self.assertEqual(parse_macro('fn ( foo , :bar = "three" , "baz" )'), expected)

    def test_cyrillic(self):
        expected = None, "fn", ["раз", "два"], {"foo": "три"}
        self.assertEqual(parse_macro('fn ( раз , :foo = три , "два")'), expected)

    """
    def test_whitespace(self):
        expected = None, "fn", ["foo", "bar"], {"baz": '1 \t\n \t\n2'}
        self.assertEqual(parse_macro('fn \t\n \t\n( \t\n \t\nfoo \t\n \t\n, \t\n \t\nbar \t\n \t\n, \t\n \t\n:baz \t\n \t\n= \t\n \t\n1 \t\n \t\n2 \t\n \t\n)'), expected)
    """

    """
    def test_par_and_br(self):
        expected = None, "fn", ["()", ["foo","[]", "bar"]], {"baz": "[]"}
        self.assertEqual(parse_macro('fn("()", :baz = "[]", [foo , "[]" , bar])'), expected)
    """

if __name__ == '__main__':
    unittest.main()