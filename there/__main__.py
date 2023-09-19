#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016-2021 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
import binascii
import datetime
import pathlib
import os
import sys
import time
import serial.tools.list_ports
from typing import List, Union
from .speaking import nice_bytes, mode_to_chars, UserMessages
from .string_escape import escaped
from .repl_connection import MicroPythonRepl, MpyPath
from .walk import walk
from .sync import Sync, EXCLUDE_DIRS
from . import miniterm_mpy

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def make_connection(user: UserMessages, args, port=None) -> MicroPythonRepl:
    """make a connection, port overrides args.port"""
    m = MicroPythonRepl(port or args.port,
                        args.baudrate,
                        user=args.user,
                        password=args.password)
    m.protocol.verbose = args.verbose > 2
    user.notice(f'port {m.serial.port} opened with {m.serial.baudrate} baud\n')
    return m

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def connect_repl(path_list: List[MpyPath], m: MicroPythonRepl) -> List[MpyPath]:
    for path in path_list:
        path.connect_repl(m)
        # there is no "current directory" concept for remote path, force them to be absolute
        if not path.is_absolute():
            path = MpyPath('/').connect_repl(m) / path
        yield path


def is_pattern(path_string: str):
    return '*' in path_string or '?' in path_string or '[' in path_string


def expand_pattern(path_list: List[Union[pathlib.Path, MpyPath]]):
    """
    :return: iterator over Path objects

    Expand a list of strings with paths or patterns.

    For MpyPath objects, the remote connection must be established for working.
    """
    for path in path_list:
        if is_pattern(str(path)):
            # snip away until pattern is gone so that we have a base directory to use glob
            root = path.parent
            while root and is_pattern(str(root)):
                root = root.parent
            path = path.relative_to(root)
            yield from root.glob(str(path))
        else:
            yield path


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def command_detect(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Help finding MicroPython boards.

    By default it simply lists all serial ports. If --test is used, each of
    the ports is opened (with the given --baudrate) and tested for a Python
    prompt. If there is no response it runs in a timeout, so this option is
    quite a bit slower that just listing the ports.
    """
    # list all serial ports
    for info in serial.tools.list_ports.comports():
        if args.test:
            try:
                m = make_connection(user, args, port=info.device)
                try:
                    mpy_info = m.exec('import sys; print(sys.implementation)').strip()
                finally:
                    m.close()
            except Exception as e:
                mpy_info = str(e)
            user.output_text(f'{info!s}: {mpy_info}\n')
        else:
            user.output_text(f'{info!s}\n')


def command_run(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Execute the contents of a (small) file on the target, without saving it to
    the targets file system.
    """
    # XXX set timeout / as argument?
    if args.timeout == 0:
        raise ValueError('use --interactive instead of --timeout=0')
    user.info(f'reading {args.FILE}\n')
    code = args.FILE.read()
    user.info('executing...\n')
    if args.interactive:
        m.exec(code, timeout=0)
    else:
        user.output_text(m.exec(code, timeout=args.timeout))


class ListPrinter:
    """This object can print lists of Path objects in a "ls" style format."""
    def __init__(self, user: UserMessages, long: bool) -> None:
        self.user = user
        self.long = long

    def __call__(self, paths, root=None):
        if self.long:
            self.print_long_list(paths, root=root)
        else:
            self.print_short_list(paths, root=root)

    def print_long_list(self, paths: List[MpyPath], root=None):
        """output function for the --long format of ls"""
        for path in paths:
            st = path.stat()
            if root is not None:
                filename = path.relative_to(root)
            else:
                filename = path
            self.user.output_text('{} {:4} {:4}  {:>8}  {} {}\n'.format(
                mode_to_chars(st.st_mode),
                st.st_uid if st.st_uid is not None else 'NONE',
                st.st_gid if st.st_gid is not None else 'NONE',
                '-' if path.is_dir() else nice_bytes(st.st_size),
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
                escaped(filename.as_posix())
                ))

    def print_short_list(self, paths, root=None):
        """output function for the short format of ls"""
        for path in paths:
            path.stat()
            if root is not None:
                filename = path.relative_to(root).as_posix()
            else:
                filename = path.as_posix()
            self.user.output_text(f'{escaped(filename)}\n')


def command_ls(user: UserMessages, m: MicroPythonRepl, args):
    """\
    List files on the targets file system.
    """
    print_list = ListPrinter(user, args.long)
    for path in expand_pattern(connect_repl(args.PATH, m)):
        if path.is_dir():
            if args.recursive:
                for dirpath, dirnames, filenames in walk(path):
                    user.output_text(f'files in {dirpath.as_posix()}:\n')
                    if dirnames:
                        print_list(dirnames, root=dirpath)
                    if filenames:
                        print_list(filenames, root=dirpath)
            else:
                print_list(path.iterdir())
        else:
            print_list([path])


def print_hash(user: UserMessages, path, hash_value):
    """output function for hashed file info"""
    user.output_text('{} {}\n'.format(
        binascii.hexlify(hash_value).decode('ascii'),
        escaped(path.as_posix())
        ))


def command_hash(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Get hash of files on the targets file system.
    """
    for path in expand_pattern(connect_repl(args.PATH, m)):
        if path.is_dir():
            if args.recursive:
                for dirpath, dirnames, filenames in walk(path):
                    for file_path in filenames:
                        print_hash(user, file_path, file_path.sha256())
        else:
            print_hash(user, path, path.sha256())


def command_cat(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Print the contents of a file from the target to stdout.
    """
    args.PATH.connect_repl(m)
    user.output_binary(args.PATH.read_bytes())


def command_rm(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Remove files on target.
    """
    sync = Sync(user, args.dry_run)
    for path in expand_pattern(connect_repl(args.PATH, m)):
        if path.is_dir():
            sync.remove_directory(path, args.recursive)
        else:
            sync.remove_file(path)
    user.file_counter.print_summary('removed')


def command_mkdir(user: UserMessages, m: MicroPythonRepl, args):
    """Make a directory remotely"""
    for path in expand_pattern(connect_repl(args.PATH, m)):
        path.mkdir(parents=args.parents, exist_ok=args.parents)


def command_mv(user: UserMessages, m: MicroPythonRepl, args):
    """Make a directory remotely"""
    args.SRC.connect_repl(m)
    args.DST.connect_repl(m)
    args.SRC.rename(args.DST)


def command_pull(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Copy file(s) from there to here.
    """
    dst = args.LOCAL[0]
    # expand the patterns
    paths = list(expand_pattern(connect_repl(args.REMOTE, m)))
    if not paths:
        raise FileNotFoundError(2, 'cannot find source: {}'.format(' '.join(args.REMOTE)))
    elif len(paths) > 1:
        if dst.exists():
            if not dst.is_dir():
                raise ValueError(f'destination must be a directory: {dst.as_posix()}')
        else:
            if not args.dry_run:
                dst.mkdir(exist_ok=True)
    sync = Sync(user, args.dry_run)
    for path in paths:
        if path.is_dir():
            if path.name in EXCLUDE_DIRS:
                continue
            sync.sync_directory(path, dst, recursive=args.recursive)
        else:
            sync.sync_file(path, dst)
    user.file_counter.print_summary('copied', 'already up to date')


def command_push(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Copy a file from here to there.
    """
    dst = args.REMOTE[0]
    dst.connect_repl(m)
    # expand the patterns for our windows users ;-)
    paths = list(expand_pattern(args.LOCAL))
    if not paths:
        raise FileNotFoundError(2, 'cannot find source: {}'.format(' '.join(args.LOCAL)))
    elif len(paths) > 1:
        if not dst.is_dir():
            raise ValueError(f'destination must be a directory: {dst!s}')
        if not dst.exists():
            raise ValueError(f'destination directory must exist: {dst!s}')
    sync = Sync(user, args.dry_run, args.force, args.no_uhashlib)
    for path in paths:
        if path.is_dir():
            if path.name in EXCLUDE_DIRS:
                continue
            sync.sync_directory(path, dst, recursive=args.recursive)
        else:
            sync.sync_file(path, dst)
    user.file_counter.print_summary('copied', 'already up to date')


def command_df(user: UserMessages, m: MicroPythonRepl, args):
    """print filesystem information (size/free)"""
    for path in expand_pattern(connect_repl(args.PATH, m)):
        st = m.statvfs(path)
        user.output_text('Location: {}  Total Size: {}, used: {}, free: {}\n'.format(
            path,
            nice_bytes(st.f_bsize * st.f_blocks),
            nice_bytes(st.f_bsize * (st.f_blocks - st.f_bfree)),
            nice_bytes(st.f_bsize * st.f_bfree),
            ))


def command_read_flash(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Read from pyb.Flash() bdev (internal, on some boards SPI Flash).
    """
    for block in m.read_flash_as_stream(args.start, args.length):
        args.output.write(block)


def command_mount(user: UserMessages, m: MicroPythonRepl, args):
    """\
    Mount the target as file system via FUSE.
    """
    from . import fuse_drive
    import subprocess
    if args.explore:
        if os.name == 'nt':
            os.startfile(args.MOUNTPOINT)
        else:
            subprocess.call(["xdg-open", args.MOUNTPOINT])
    try:
        user.info(f'mounting to {args.MOUNTPOINT}\n')
        args.base.connect_repl(m)
        fuse_drive.mount(args.base, args.MOUNTPOINT, args.verbose)
    except RuntimeError:
        user.error('ERROR: Could not mount - note: directory must exist\n')


def command_rtc(user: UserMessages, m: MicroPythonRepl, args):
    """read the real time clock (RTC)"""
    t1 = m.read_rtc()
    user.output_text(f'{t1:%Y-%m-%d %H:%M:%S.%f}\n')
    if args.test:
        time.sleep(1)
        t2 = m.read_rtc()
        user.output_text(f'{t2:%Y-%m-%d %H:%M:%S.%f}\n')
        if not datetime.timedelta(seconds=0.9) <  t2 - t1 < datetime.timedelta(seconds=1.1):
            raise IOError('clock not running')


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def main():
    import argparse

    global_options = argparse.ArgumentParser(add_help=False)

    group = global_options.add_argument_group("port settings")

    group.add_argument(
        '-p', '--port',
        default=os.environ.get('MPY_PORT', 'hwgrep://USB'),
        help='set the serial port')
    group.add_argument(
        '-b', '--baudrate', type=int,
        default=os.environ.get('MPY_BAUDRATE', '115200'),
        help='set the baud rate')

    group = global_options.add_argument_group("operations before running action")

    group.add_argument(
        '--set-rtc',
        action='store_true',
        help='set the RTC to "now" before command is executed')
    group.add_argument(
        '--reset-on-connect',
        action='store_true',
        help='do a soft reset as first operation (main.py will not be executed)')

    group = global_options.add_argument_group("operations after running action")

    group.add_argument(
        '-c', '--command',
        help='execute given code on target')
    group.add_argument(
        '--command-timeout',
        type=float,
        default=5,
        help='timeout in seconds for --command', metavar='T')
    group.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='drop to interactive shell at the end')
    group.add_argument(
        '--reset',
        action='store_true',
        help='do a soft reset on the end')

    group = global_options.add_argument_group("login")

    group.add_argument(
        '-u', '--user',
        default=os.environ.get('MPY_USER'),
        help='response to login prompt')
    group.add_argument(
        '-w', '--password',
        default=os.environ.get('MPY_PASSWORD'),
        help='response to password prompt')


    group = global_options.add_argument_group("diagnostics")

    group.add_argument(
        '-v', '--verbose',
        action='count', default=0,
        help='show diagnostic messages, repeat for more')
    group.add_argument(
        '--develop',
        action='store_true',
        help='show tracebacks on errors (development of this tool)')
    group.add_argument(
        "--timeit",
        action="store_true",
        help="measure command run time",
        default=False)

    parser = argparse.ArgumentParser(
        description='Do stuff via the MicroPython REPL',
        parents=[global_options])
    parser.set_defaults(connect=False, func=lambda user, m, args: 0)

    subparsers = parser.add_subparsers(
        help='sub-command help',
        metavar='ACTION',
        description='use "%(prog)s ACTION --help" for more on each sub-command')

    parser_detect = subparsers.add_parser('detect', help='help locating a board')
    parser_detect.add_argument('-t', '--test', action='store_true', help='open and test each port')
    parser_detect.set_defaults(func=command_detect)

    parser_run = subparsers.add_parser('run', help='execute file contents on target')
    parser_run.add_argument('FILE', type=argparse.FileType('r', encoding='UTF-8'), help='load this file contents')
    parser_run.add_argument('-t', '--timeout', type=float, default='10', help='wait x seconds for completion')
    parser_run.set_defaults(func=command_run, connect=True)

    parser_ls = subparsers.add_parser('ls', help='list files')
    parser_ls.add_argument('PATH', nargs='*', type=MpyPath, default=[MpyPath('/')], help='paths to list')
    parser_ls.add_argument('-l', '--long', action='store_true', help='show more info')
    parser_ls.add_argument('-r', '--recursive', action='store_true', help='list contents of directories')
    parser_ls.set_defaults(func=command_ls, connect=True)

    parser_hash = subparsers.add_parser('hash', help='hash files')
    parser_hash.add_argument('PATH', nargs='*', type=MpyPath, default=[MpyPath('/')], help='paths to list')
    parser_hash.add_argument('-r', '--recursive', action='store_true', help='list contents of directories')
    parser_hash.set_defaults(func=command_hash, connect=True)

    parser_cat = subparsers.add_parser('cat', help='print contents of one file')
    parser_cat.add_argument('PATH', type=MpyPath, help='filename on target')
    parser_cat.set_defaults(func=command_cat, connect=True)

    parser_pull = subparsers.add_parser('pull', help='file(s) to copy from target')
    parser_pull.add_argument('REMOTE', nargs='+', type=MpyPath, help='one or more source files/directories')
    parser_pull.add_argument('LOCAL', nargs=1, type=pathlib.Path, help='destination directory')
    parser_pull.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
    parser_pull.add_argument('--dry-run', action='store_true', help='do not actually copy anything from target')
    parser_pull.set_defaults(func=command_pull, connect=True)

    parser_push = subparsers.add_parser('push', help='file(s) to copy onto target')
    parser_push.add_argument('LOCAL', nargs='+', type=pathlib.Path, help='one or more source files/directories')
    parser_push.add_argument('REMOTE', nargs=1, type=MpyPath, help='destination directory')
    parser_push.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
    parser_push.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
    parser_push.add_argument('--force', action='store_true', help='write always, skip up-to-date check')
    parser_push.add_argument('--no-uhashlib', action='store_true', help='do not attempt to use uhashlib')
    parser_push.set_defaults(func=command_push, connect=True)

    parser_rm = subparsers.add_parser('rm', help='remove files from target')
    parser_rm.add_argument('PATH', nargs='+', type=MpyPath, help='filename on target')
    parser_rm.add_argument('-f', '--force', action='store_true', help='delete anyway / no error if not existing')
    parser_rm.add_argument('-r', '--recursive', action='store_true', help='remove directories recursively')
    parser_rm.add_argument('--dry-run', action='store_true', help='do not actually delete anything on target')
    parser_rm.set_defaults(func=command_rm, connect=True)

    parser_mkdir = subparsers.add_parser('mkdir', help='create directory')
    parser_mkdir.add_argument('PATH', nargs='+', type=MpyPath, help='filename on target')
    parser_mkdir.add_argument('--parents', action='store_true', help='create parents')   # -p clashes with --port
    parser_mkdir.set_defaults(func=command_mkdir, connect=True)

    parser_mv = subparsers.add_parser('mv', help='move files')
    parser_mv.add_argument('SRC', type=MpyPath, help='source')
    parser_mv.add_argument('DST', type=MpyPath, help='destination')
    parser_mv.set_defaults(func=command_mv, connect=True)

    parser_read_flash = subparsers.add_parser('read_flash', help='Read Flash memory')
    parser_read_flash.add_argument('-s', '--start', type=lambda x: int(x, 0), default=0, help='start offset')
    parser_read_flash.add_argument('-l', '--length', type=lambda x: int(x, 0), default=-1, help='length')
    parser_read_flash.add_argument('-o', '--output', type=argparse.FileType('wb'), help='store flash to file')
    parser_read_flash.set_defaults(func=command_read_flash, connect=True)

    parser_df = subparsers.add_parser('df', help='Show filesystem information')
    parser_df.add_argument('PATH', nargs='*', default=[MpyPath('/')], type=MpyPath, help='remote path')
    parser_df.set_defaults(func=command_df, connect=True)

    parser_mount = subparsers.add_parser('mount', help='Make target files accessible via FUSE')
    parser_mount.add_argument('MOUNTPOINT', help='local mount point, directory must exist')
    parser_mount.add_argument('--base', type=MpyPath, default=MpyPath('/'), help='base path to mount on remote')
    parser_mount.add_argument('-e', '--explore', action='store_true', help='auto open file explorer at mount point')
    parser_mount.set_defaults(func=command_mount, connect=True)

    parser_rtc_read = subparsers.add_parser('rtc', help='Read the real time clock (RTC)')
    parser_rtc_read.add_argument('--test', action='store_true', help='test if the clock runs')
    parser_rtc_read.set_defaults(func=command_rtc, connect=True)

    namespace, remaining_args = global_options.parse_known_args()
    args = parser.parse_args(remaining_args, namespace=namespace)

    if args.develop:
        print(args)

    user = UserMessages(args.verbose)

    if args.command or args.interactive or args.reset:
        args.connect = True

    try:
        if args.connect:
            m = make_connection(user, args)
        else:
            m = None
    except Exception as e:
        if args.develop:
            raise
        user.error('ERROR: connection failed: {}\n'.format(e))
        sys.exit(2)

    exitcode = 0
    try:
        if m is not None:
            if args.reset_on_connect:
                m.soft_reset(run_main=False)
            else:
                m.exec(' ')  # run an empty line to "sync"
            if args.set_rtc:
                m.set_rtc()
        if args.func:
            if args.timeit:
                t_start = time.monotonic()
            args.func(user, m, args)
            if args.timeit:
                t_end = time.monotonic()
                sys.stderr.write('t = {:.3f} s\n'.format(t_end - t_start))
        if args.command:
            if args.interactive:
                m.exec(args.command, timeout=0)
            else:
                user.output_text(m.exec(args.command, timeout=args.command_timeout))
        if args.reset:
            m.soft_reset(run_main=True)
    except Exception as e:
        if args.develop:
            raise
        user.error('ERROR: action or command failed: {}\n'.format(e))
        exitcode = 1

    if args.interactive:
        if m:
            m.stop(interrupt=False)
        sys.argv = ['n/a', '-f', 'direct']
        miniterm_mpy.main(serial_instance=m.serial)
    elif m:
        m.close(interrupt=False)

    sys.exit(exitcode)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    main()
