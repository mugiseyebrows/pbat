import os
from lark import Lark, Tree, Token
import unittest
import re

base = os.path.dirname(__file__)
path = os.path.join(base, "def.lark")
with open(path, encoding='utf-8') as f:
    GRAMMAR = f.read()

parser = Lark(GRAMMAR)

def find_data(tree, data, trace = False):
    return [child for child in tree.children if hasattr(child, 'data') and child.data == data]

DEF_RX = re.compile('\\s*def\\s+([0-9a-z_]+)', re.IGNORECASE)

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
            depends = [s for s in arg[2:] if s != 'and']
    condition = None
    return name, then, depends, shell, condition

def parse_def2(line):

    m = DEF_RX.match(line)
    if m is None:
        return None

    name = None
    then = None
    depends = []
    shell = None
    tree = parser.parse(line)

    for item in find_data(tree, 'defname'):
        name = item.children[0].value
    for item in find_data(tree, 'then'):
        then = item.children[0].value
    for item in find_data(tree, 'depends'):
        values = [ch.value for ch in item.children if ch.value != 'and']
        #print("depends values", values)
        depends += values
    for item in find_data(tree, 'shell'):
        shell = item.children[0].value
    condition = None
    for item in find_data(tree, "if"):
        for cond in find_data(item, "cond"):
            pos1 = cond.children[0].start_pos
            pos2 = cond.children[-1].end_pos
            condition = line[pos1:pos2]
    return name, then, depends, shell, condition

class TestParse(unittest.TestCase):
    def test1(self):
        def_ = 'def baz depends on foo bar then qux shell corge'
        expected = 'baz', 'qux', ['foo', 'bar'], 'corge'
        self.assertEqual(expected, parse_def(def_))
    def test2(self):
        def_ = 'def third depends on second'
        expected = 'third', None, ['second'], None
        self.assertEqual(expected, parse_def(def_))
    def test3(self):
        def_ = 'def second shell msys2'
        expected = 'second', None, [], 'msys2'
        self.assertEqual(expected, parse_def(def_))
    def test4(self):
        def_= 'def main then second'
        expected = 'main', 'second', [], None
        self.assertEqual(expected, parse_def(def_))

if __name__ == '__main__':
    unittest.main()