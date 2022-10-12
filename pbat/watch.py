
import argparse
import os

import datetime
import subprocess
import glob
from . import read_compile_write, get_dst_bat, get_dst_workflow

try:
    from eventloop import on_file_changed, EventLoop
    from colorama import Fore, Back, Style, init as colorama_init
except ImportError as e:
    print("pbat.watch requires pyuv eventloop and colorama modules\nto install it run\n   python -m pip install pyuv eventloop colorama")
    exit(1)

def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class Logger:

    def print_info(self, msg):
        print(Fore.WHITE + now_str() + " " + Fore.YELLOW + Style.BRIGHT + msg + Fore.RESET + Style.NORMAL)

    def print_error(self, msg, with_date=True):
        if with_date:
            print(Fore.WHITE + now_str() + " " + Fore.RED + Style.BRIGHT + msg + Fore.RESET + Style.NORMAL)
        else:
            print(Fore.RED + Style.BRIGHT + msg + Fore.RESET + Style.NORMAL)

    def print_compiled(self, src, dst):
        print(Fore.WHITE + now_str() + " " + Fore.GREEN + Style.BRIGHT + src + Fore.WHITE + ' -> ' + Fore.GREEN + dst + Fore.RESET + Style.NORMAL)

def replace_ext(path, ext):
    path_ = os.path.splitext(path)
    return path_[0] + ext

def main():

    colorama_init()
    parser = argparse.ArgumentParser()

    parser.add_argument("path", nargs='*', help='file, directory or glob')
    parser.add_argument('-o', '--output')
    parser.add_argument('-c', '--compile', action='store_true')
    parser.add_argument('-n', '--not-recursive', action='store_true', help="do not watch subdirectories")
    args = parser.parse_args()
    paths = []

    logger = Logger()

    for path in args.path:

        if os.path.splitext(path)[1] == '.bat':
            msg ="{} is bat file, not pbat, did you meen {}".format(path, replace_ext(path, '.pbat'))
            logger.print_error(msg, with_date=False)

        if glob.has_magic(path):
            basename = os.path.basename(path)
            if basename in ['*', '*.pbat']:
                paths.append(path)
            else:
                for path_ in glob.glob(path):
                    paths.append(path_)
        else:
            paths.append(path)

    if len(args.path) == 0:
        paths.append('.')

    def handler(file_path):
        base = os.path.dirname(file_path)
        name = os.path.basename(file_path)
        ext = os.path.splitext(name)[1]
        if ext != '.pbat':
            return
        src = file_path
        try:
            dst_bat = get_dst_bat(src)
            dst_workflow = get_dst_workflow(src)
            read_compile_write(src, dst_bat, dst_workflow, verbose=False)
            logger.print_compiled(file_path, dst_bat)
            logger.print_compiled(file_path, dst_workflow)
        except Exception as e:
            logger.print_error(str(e))

    loop = EventLoop()

    recursive = not args.not_recursive

    decorated = [on_file_changed(path, recursive=recursive, loop=loop)(handler) for path in paths]

    def is_pbat(n):
        return os.path.splitext(n)[1].lower() == '.pbat'

    if args.compile:
        for path in paths:
            if recursive:
                for root, dirs, files in os.walk(path):
                    for f in files:
                        if is_pbat(f):
                            handler(os.path.join(root, f))
            else:
                for f in os.listdir(path):
                    if is_pbat(f):
                        handler(os.path.join(path, f))

    loop.start()
    
if __name__ == "__main__":
    main()