import os
import unittest
import re

def _unquote(s):
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s

class ParseMacroError(Exception):
    pass

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