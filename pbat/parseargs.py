import os
from lark import Lark, Tree

def _unquote(s):
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s

def _norm(e):
    return _unquote(e.value.strip())

def _parse_list(tokens, args, kwargs):
    values = [_norm(e) for e in tokens]
    args.append(values)
    
def _parse_arg(tokens, args, kwargs):
    if isinstance(tokens[0], Tree):
        _parse_list(tokens[0].children, args, kwargs)
    else:
        values = [_norm(e) for e in tokens]
        if len(values) == 2:
            n, v = values
            n = n.lstrip('@')
            kwargs[n] = v
        elif len(values) == 1:
            n, = values
            if n.startswith('@'):
                n = n.lstrip('@')
                kwargs[n] = True
            else:
                args.append(n)

base = os.path.dirname(__file__)
path = os.path.join(base, "pbat.lark")
with open(path, encoding='utf-8') as f:
    GRAMMAR = f.read()

parser = Lark(GRAMMAR)

def parse_args(s):
    tree = parser.parse(s)
    if len(tree.children) == 3:
        tree_ret, tree_name, tree_args = tree.children
        ret = _norm(tree_ret.children[0])
    else:
        tree_name, tree_args = tree.children
        ret = None
    name = _norm(tree_name.children[0])
    args = []
    kwargs = dict()
    for tree in tree_args.children:
        _parse_arg(tree.children, args, kwargs)
    return ret, name, args, kwargs

def test():
    samples = [
        'foo = bar(1)',
        'bar(1)',
        'bar(1, 2, @keep = 3)',
        'bar(1, [foo, bar, baz], 2)'
    ]
    for sample in samples:
        print(sample, parse_args(sample))

if __name__ == "__main__":
    test()