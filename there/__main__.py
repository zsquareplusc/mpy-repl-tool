#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
import posixpath
import os
import sys
import stat
import time
import glob
import serial.tools.list_ports
from .speaking import nice_bytes, mode_to_chars
from .string_escape import escaped
from . import repl_connection
from . import miniterm_mpy


def make_connection(args, port=None):
    """make a conenction, port overrides args.port"""
    m = repl_connection.MicroPythonRepl(port or args.port,
                                        args.baudrate,
                                        user=args.user,
                                        password=args.password)
    m.protocol.verbose = args.verbose > 1
    if args.verbose:
        sys.stderr.write('connected to {} {}\n'.format(m.serial.port, m.serial.baudrate))
    return m


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def command_detect(m, args):
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
                m = make_connection(args, port=info.device)
                try:
                    mpy_info = m.exec('import sys; print(sys.implementation)').strip()
                finally:
                    m.close()
            except Exception as e:
                mpy_info = str(e)
            sys.stdout.write('{!s}: {}\n'.format(info, mpy_info))
        else:
            sys.stdout.write('{!s}\n'.format(info))


def command_run(m, args):
    """\
    Execute the contents of a (small) file on the target, without saving it to
    the targets file system.
    """
    # XXX set timeout / as argument?
    if args.timeout == 0:
        raise ValueError('use --interactive insteaf of --timeout=0')
    if args.verbose:
        sys.stderr.write('reading to {}\n'.format(args.FILE))
    code = open(args.FILE).read()
    if args.verbose:
        sys.stderr.write('executing...\n')
    if args.interactive:
        m.exec(code, timeout=0)
    else:
        sys.stdout.write(m.exec(code, timeout=args.timeout))


def command_ls(m, args):
    """\
    List files on the targets file system.
    """
    for path in args.PATH:
        if args.long:
            files_and_stat = list(m.glob(path))
            files_and_stat.sort()
            for filename, st in files_and_stat:
                sys.stdout.write('{} {:4} {:4} {:>7} {} {}\n'.format(
                    mode_to_chars(st.st_mode),
                    st.st_uid if st.st_uid is not None else 'NONE',
                    st.st_gid if st.st_gid is not None else 'NONE',
                    nice_bytes(st.st_size),
                    time.strftime('%Y-%m-%d %02H:%02M:%02S', time.localtime(st.st_mtime)),
                    escaped(filename)))
        else:
            sys.stdout.write(' '.join(n for n, st in sorted(m.glob(path))))
            sys.stdout.write('\n')


def command_cat(m, args):
    """\
    Print the contents of a file from the target to stdout.
    """
    sys.stdout.buffer.write(m.read_file(args.PATH))
    sys.stdout.buffer.write(b'\n')


def command_rm(m, args):
    """\
    Remove files on target.
    """
    # XXX --force option, --recursive option
    for pattern in args.PATH:
        matches = list(m.glob(pattern))
        if not matches and not args.force:
            raise FileNotFoundError(2, 'File not found: {}'.format(pattern))
        for path, st in matches:
            if st.st_mode & stat.S_IFDIR:
                # XXX dive down if --recursive
                if args.verbose:
                    sys.stderr.write('remove directory {}/\n'.format(path))
                if not args.dry_run:
                    m.rmdir(path)
            else:
                if args.verbose:
                    sys.stderr.write('remove {}\n'.format(path))
                if not args.dry_run:
                    m.remove(path)


EXCLUDE_DIRS = ['__pycache__']


def ensure_dir(m, path):
    try:
        st = m.stat(path)
    except FileNotFoundError:
        m.mkdir(path)
    else:
        if (st.st_mode & stat.S_IFDIR) == 0:
            raise FileExistsError('there is a file in the way: {}'.format(path))


def command_put(m, args):
    """\
    Copy a file from here to there.
    """
    dst = args.DST[0]
    try:
        dst_dir = (m.stat(dst).st_mode & stat.S_IFDIR) != 0
        dst_exists = True
    except FileNotFoundError:
        dst_dir = False
        dst_exists = False
    # expand the patterns for our windows users ;-)
    paths = sum((glob.glob(src) for src in args.SRC), [])
    if len(paths) > 1:
        if not dst_dir:
            raise ValueError('destination must be a directory')
        if not dst_exists:
            raise ValueError('destination directory must exist')
    for path in paths:
        if os.path.isdir(path):
            if os.path.basename(path) in EXCLUDE_DIRS:
                continue
            if args.recursive:
                root = os.path.dirname(path)
                for dirpath, dirnames, filenames in os.walk(path):
                    relpath = os.path.relpath(dirpath, root)
                    if not args.dry_run:
                        ensure_dir(m, posixpath.join(dst, relpath))
                    for dir in EXCLUDE_DIRS:
                        try:
                            dirnames.remove(dir)
                        except ValueError:
                            pass
                    for filename in filenames:
                        if args.verbose:
                            sys.stderr.write('{} -> {}\n'.format(
                                os.path.join(dirpath, filename),
                                posixpath.join(dst, relpath, filename)))
                        if not args.dry_run:
                            m.write_file(os.path.join(dirpath, filename),
                                         posixpath.join(dst, relpath, filename))
            else:
                sys.stderr.write('skiping directory {}\n'.format(path))
        else:
            if dst_dir:
                if args.verbose:
                    sys.stderr.write('{} -> {}\n'.format(path, posixpath.join(dst, os.path.basename(path))))
                if not args.dry_run:
                    m.write_file(path, posixpath.join(dst, os.path.basename(path)))
            else:
                if args.verbose:
                    sys.stderr.write('{} -> {}\n'.format(path, dst))
                if not args.dry_run:
                    m.write_file(path, dst)


def command_mount(m, args):
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
        if args.verbose:
            sys.stderr.write('mounting to {}\n'.format(args.MOUNTPOINT))
        fuse_drive.mount(m, args.MOUNTPOINT, args.verbose)
    except RuntimeError:
        sys.stderr.write('ERROR: Could not mount - note: directory must exist\n')


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def main():
    import argparse

    global_options = argparse.ArgumentParser(add_help=False)
    global_options.add_argument('-p', '--port',
        default=os.environ.get('MPY_PORT', 'hwgrep://USB'),
        help='set the serial port')
    global_options.add_argument('-b', '--baudrate', type=int,
        default=os.environ.get('MPY_BAUDRATE', '115200'),
        help='set the baud rate')
    global_options.add_argument('-c', '--command',
        help='execute given code on target')
    global_options.add_argument('-i', '--interactive', action='store_true',
        help='drop to interactive shell at the end')
    global_options.add_argument('-u', '--user',
        default=os.environ.get('MPY_USER'),
        help='response to login prompt')
    global_options.add_argument('-w', '--password',
        default=os.environ.get('MPY_PASSWORD'),
        help='response to password prompt')
    global_options.add_argument('-v', '--verbose', action='count', default=0,
        help='show diagnostic messages, repeat for more')
    global_options.add_argument('--develop', action='store_true',
        help='show tracebacks on errors (development of this tool)')

    parser = argparse.ArgumentParser(
        description='Do stuff via the MicroPython REPL',
        parents=[global_options])
    parser.set_defaults(connect=False, func=lambda m, args: 0)

    subparsers = parser.add_subparsers(help='sub-command help')

    parser_detect = subparsers.add_parser('detect', help='help locating a board', parents=[global_options])
    parser_detect.add_argument('-t', '--test', action='store_true', help='open and test each port')
    parser_detect.set_defaults(func=command_detect)

    parser_run = subparsers.add_parser('run', help='execute file contents on target', parents=[global_options])
    parser_run.add_argument('FILE', nargs='?', help='load this file contents')
    parser_run.add_argument('-t', '--timeout', type=float, default='10', help='wait x seconds for completion')
    parser_run.set_defaults(func=command_run, connect=True)

    parser_ls = subparsers.add_parser('ls', help='list files', parents=[global_options])
    parser_ls.add_argument('PATH', nargs='*', default='/', help='paths to list')
    parser_ls.add_argument('-l', '--long', action='store_true', help='show more info')
    parser_ls.set_defaults(func=command_ls, connect=True)

    parser_cat = subparsers.add_parser('cat', help='print contents of one file', parents=[global_options])
    parser_cat.add_argument('PATH', help='filename on target')
    parser_cat.set_defaults(func=command_cat, connect=True)


    parser_put = subparsers.add_parser('put', help='file(s) to copy onto target', parents=[global_options])
    parser_put.add_argument('SRC', nargs='+', help='one or more source files/directories')
    parser_put.add_argument('DST', nargs=1, help='destination directory')
    parser_put.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
    parser_put.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
    parser_put.set_defaults(func=command_put, connect=True)

    parser_rm = subparsers.add_parser('rm', help='remove files on target', parents=[global_options])
    parser_rm.add_argument('PATH', nargs='+', help='filename on target')
    parser_rm.add_argument('-f', '--force', action='store_true', help='delete anyway / no error if not existing')
    parser_rm.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
    parser_rm.set_defaults(func=command_rm, connect=True)

    parser_mount = subparsers.add_parser('mount', help='Make target files accessible via FUSE', parents=[global_options])
    parser_mount.add_argument('MOUNTPOINT', help='local mount point, directory must exist')
    parser_mount.add_argument('-e', '--explore', action='store_true', help='auto open file explorer at mount point')
    parser_mount.set_defaults(func=command_mount, connect=True)

    args = parser.parse_args()

    if args.command or args.interactive:
        args.connect = True

    if args.connect:
        m = make_connection(args)
    else:
        m = None

    exitcode = 0
    try:
        if args.func:
            args.func(m, args)
        if args.command:
            sys.stdout.write(m.exec(args.command))
    except Exception as e:
        if args.develop:
            raise
        sys.stderr.write('ERROR: action or command failed: {}\n'.format(e))
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
