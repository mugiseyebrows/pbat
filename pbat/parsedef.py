import unittest
import re

def parse_def(line: str):
    words = re.split('\\s+', line.lstrip())

    if words[0] != 'def':
        return None
    
    name = words[1]
    then = None
    depends = []
    shell = None
    STOP = ['depends', 'then', 'shell']
    args = []
    arg = []

    for word in words[2:]:
        if word in STOP:
            if len(arg) > 0:
                args.append(arg)
            arg = [word]
        else:
            arg.append(word)
    if len(arg) > 0:
        args.append(arg)
    arg = []

    for arg in args:
        if arg[0] == 'shell':
            if len(arg) < 2:
                raise ValueError(f'invalid syntax: expected "shell ID" got "{arg}", line "{line}"')
            shell = arg[1]
        elif arg[0] == 'then':
            if len(arg) < 2:
                raise ValueError(f'invalid syntax: expected "then ID" got "{arg}", line "{line}"')
            then = arg[1]
        elif arg[0] == 'depends':
            if len(arg) < 2 or arg[1] != 'on':
                raise ValueError(f'invalid syntax: expected "depends on ID" got "{arg}", line "{line}"')
            depends = [s for s in arg[2:] if s not in ['and','']]
    condition = None
    return name, then, depends, shell, condition

class TestParse(unittest.TestCase):
    def test1(self):
        def_ = 'def baz depends on foo bar then qux shell corge'
        expected = 'baz', 'qux', ['foo', 'bar'], 'corge', None
        self.assertEqual(expected, parse_def(def_))
    def test2(self):
        def_ = 'def third depends on second'
        expected = 'third', None, ['second'], None, None
        self.assertEqual(expected, parse_def(def_))
    def test3(self):
        def_ = 'def second shell msys2'
        expected = 'second', None, [], 'msys2', None
        self.assertEqual(expected, parse_def(def_))
    def test4(self):
        def_= 'def main then second'
        expected = 'main', 'second', [], None, None
        self.assertEqual(expected, parse_def(def_))

if __name__ == '__main__':
    unittest.main()