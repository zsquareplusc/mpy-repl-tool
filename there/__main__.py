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


class UserMessages(object):
    """
    Provide a class with methods to interact with user. Makes it simpler to
    track verbosity flag.
    """
    def __init__(self, verbosity):
        self.verbosity = verbosity

    def output_binary(self, message):
        """output bytes, typically stdout"""
        sys.stdout.buffer.write(message)

    def output_text(self, message):
        """output text, typically stdout"""
        sys.stdout.write(message)

    def error(self, message):
        """error messages to stderr"""
        sys.stderr.write(message)

    def notice(self, message):
        """informative messages to stderr"""
        sys.stderr.write(message)

    def info(self, message):
        """informative messages to stderr, only if verbose flag is set"""
        if self.verbosity > 0:
            sys.stderr.write(message)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def make_connection(user, args, port=None):
    """make a conenction, port overrides args.port"""
    m = repl_connection.MicroPythonRepl(port or args.port,
                                        args.baudrate,
                                        user=args.user,
                                        password=args.password)
    m.protocol.verbose = args.verbose > 1
    user.info('connected to {} {}\n'.format(m.serial.port, m.serial.baudrate))
    return m


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def command_detect(user, m, args):
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
            user.output_text('{!s}: {}\n'.format(info, mpy_info))
        else:
            user.output_text('{!s}\n'.format(info))


def command_run(user, m, args):
    """\
    Execute the contents of a (small) file on the target, without saving it to
    the targets file system.
    """
    # XXX set timeout / as argument?
    if args.timeout == 0:
        raise ValueError('use --interactive instead of --timeout=0')
    user.info('reading to {}\n'.format(args.FILE))
    code = open(args.FILE).read()
    user.info('executing...\n')
    if args.interactive:
        m.exec(code, timeout=0)
    else:
        user.output_text(m.exec(code, timeout=args.timeout))


def print_long_list(user, files_and_stat, root=None):
    """output function for the --long format of ls"""
    for filename, st in files_and_stat:
        user.output_text('{} {:4} {:4} {:>7} {} {}\n'.format(
            mode_to_chars(st.st_mode),
            st.st_uid if st.st_uid is not None else 'NONE',
            st.st_gid if st.st_gid is not None else 'NONE',
            nice_bytes(st.st_size),
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
            escaped(filename) if root is None else escaped(posixpath.join(root, filename))
            ))


def print_short_list(user, files_and_stat, root=None):
    """output function for the short format of ls"""
    user.output_text('\n'.join(
        escaped(n) if root is None else escaped(posixpath.join(root, n))
        for n, st in files_and_stat))
    user.output_text('\n')


def command_ls(user, m, args):
    """\
    List files on the targets file system.
    """
    if args.long:
        print_list = print_long_list
    else:
        print_list = print_short_list
    for pattern in args.PATH:
        for path, st in m.glob(pattern):
            if args.recursive:
                if st.st_mode & stat.S_IFDIR:
                    for dirpath, dir_stat, file_stat in m.walk(path):
                        print_list(user, file_stat + dir_stat, dirpath)
                else:
                    print_list(user, [(path, st)])
            else:
                if st.st_mode & stat.S_IFDIR:
                    print_list(user, m.listdir(path), path)
                else:
                    print_list(user, [(path, st)])


def command_cat(user, m, args):
    """\
    Print the contents of a file from the target to stdout.
    """
    user.output_binary(m.read_from_file(args.PATH))


def command_rm(user, m, args):
    """\
    Remove files on target.
    """
    for pattern in args.PATH:
        matches = list(m.glob(pattern))
        if not matches and not args.force:
            raise FileNotFoundError(2, 'File not found: {}'.format(pattern))
        for path, st in matches:
            if st.st_mode & stat.S_IFDIR:
                if args.recursive:
                    for dirpath, dir_stat, file_stat in m.walk(path, topdown=False):
                        for name, st in dir_stat:
                            user.info('rmdir {}/{}\n'.format(dirpath, name))
                            if not args.dry_run:
                                m.rmdir(posixpath.join(dirpath, name))
                        for name, st in file_stat:
                            user.info('rm {}/{}\n'.format(dirpath, name))
                            if not args.dry_run:
                                m.remove(posixpath.join(dirpath, name))
                    user.info('rmdir {}\n'.format(dirpath))
                    if not args.dry_run:
                        m.rmdir(dirpath)
                else:
                    user.info('rmdir {}/\n'.format(path))
                    if not args.dry_run:
                        m.rmdir(path)
            else:
                user.info('rm {}\n'.format(path))
                if not args.dry_run:
                    m.remove(path)


EXCLUDE_DIRS = ['__pycache__']


def ensure_dir(m, path):
    """ensure that path is a directory, make directory if needed"""
    try:
        st = m.stat(path)
    except FileNotFoundError:
        m.mkdir(path)
    else:
        if (st.st_mode & stat.S_IFDIR) == 0:
            raise FileExistsError('there is a file in the way: {}'.format(path))


def command_pull(user, m, args):
    """\
    Copy a file from here to there.
    """
    dst = args.LOCAL[0]
    dst_dir = os.path.isdir(dst)
    dst_exists = os.path.exists(dst)
    # expand the patterns for our windows users ;-)
    paths = sum((list(m.glob(src)) for src in args.REMOTE), [])
    if not paths:
        raise FileNotFoundError(2, 'cannot find source: {}'.format(' '.join(args.REMOTE)))
    elif len(paths) > 1:
        if dst_exists:
            if not dst_dir:
                raise ValueError('destination must be a directory')
        else:
            if not args.dry_run:
                os.makedirs(dst, exist_ok=True)
            dst_dir = True
    for path, st in paths:
        if (st.st_mode & stat.S_IFDIR) != 0:
            if args.recursive:
                root = os.path.dirname(path)
                for dirpath, dir_stat, file_stat in m.walk(path):
                    relpath = posixpath.relpath(dirpath, root)
                    if not args.dry_run:
                        os.makedirs(os.path.join(dst, relpath), exist_ok=True)
                    for filename, st in file_stat:
                        user.info('{} -> {}\n'.format(
                                  posixpath.join(dirpath, filename),
                                  os.path.join(dst, relpath, filename)))
                        if not args.dry_run:
                            m.read_file(posixpath.join(dirpath, filename),
                                        os.path.join(dst, relpath, filename))
            else:
                user.notice('skiping directory {}\n'.format(path))
        else:
            if dst_dir:
                user.info('{} -> {}\n'.format(path, os.path.join(dst, posixpath.basename(path))))
                if not args.dry_run:
                    m.read_file(path, os.path.join(dst, posixpath.basename(path)))
            else:
                user.info('{} -> {}\n'.format(path, dst))
                if not args.dry_run:
                    m.read_file(path, dst)


def command_push(user, m, args):
    """\
    Copy a file from here to there.
    """
    dst = args.REMOTE[0]
    try:
        dst_dir = (m.stat(dst).st_mode & stat.S_IFDIR) != 0
        dst_exists = True
    except FileNotFoundError:
        dst_dir = False
        dst_exists = False
    # expand the patterns for our windows users ;-)
    paths = sum((glob.glob(src) for src in args.LOCAL), [])
    if not paths:
        raise FileNotFoundError(2, 'cannot find source: {}'.format(' '.join(args.LOCAL)))
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
                        user.info('{} -> {}\n'.format(
                                  os.path.join(dirpath, filename),
                                  posixpath.join(dst, relpath, filename)))
                        if not args.dry_run:
                            m.write_file(os.path.join(dirpath, filename),
                                         posixpath.join(dst, relpath, filename))
            else:
                user.notice('skiping directory {}\n'.format(path))
        else:
            if dst_dir:
                user.info('{} -> {}\n'.format(path, posixpath.join(dst, os.path.basename(path))))
                if not args.dry_run:
                    m.write_file(path, posixpath.join(dst, os.path.basename(path)))
            else:
                user.info('{} -> {}\n'.format(path, dst))
                if not args.dry_run:
                    m.write_file(path, dst)


def command_df(user, m, args):
    """print filesystem information (size/free)"""
    st = m.statvfs(args.PATH)
    user.output_text('Total Size: {}, used: {}, free: {}\n'.format(
        nice_bytes(st.f_bsize * st.f_blocks),
        nice_bytes(st.f_bsize * (st.f_blocks - st.f_bfree)),
        nice_bytes(st.f_bsize * st.f_bfree),
        ))


def command_mount(user, m, args):
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
        user.info('mounting to {}\n'.format(args.MOUNTPOINT))
        fuse_drive.mount(m, args.MOUNTPOINT, args.verbose)
    except RuntimeError:
        user.error('ERROR: Could not mount - note: directory must exist\n')


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def main():
    import argparse

    global_options = argparse.ArgumentParser(add_help=False)
    global_options.add_argument(
        '-p', '--port',
        default=os.environ.get('MPY_PORT', 'hwgrep://USB'),
        help='set the serial port')
    global_options.add_argument(
        '-b', '--baudrate', type=int,
        default=os.environ.get('MPY_BAUDRATE', '115200'),
        help='set the baud rate')
    global_options.add_argument(
        '-c', '--command',
        help='execute given code on target')
    global_options.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='drop to interactive shell at the end')
    global_options.add_argument(
        '--reset',
        action='store_true',
        help='do a soft reset on the end')
    global_options.add_argument(
        '-u', '--user',
        default=os.environ.get('MPY_USER'),
        help='response to login prompt')
    global_options.add_argument(
        '-w', '--password',
        default=os.environ.get('MPY_PASSWORD'),
        help='response to password prompt')
    global_options.add_argument(
        '-v', '--verbose',
        action='count', default=0,
        help='show diagnostic messages, repeat for more')
    global_options.add_argument(
        '--develop',
        action='store_true',
        help='show tracebacks on errors (development of this tool)')

    parser = argparse.ArgumentParser(
        description='Do stuff via the MicroPython REPL',
        parents=[global_options])
    parser.set_defaults(connect=False, func=lambda user, m, args: 0)

    subparsers = parser.add_subparsers(help='sub-command help')

    parser_detect = subparsers.add_parser('detect', help='help locating a board')
    parser_detect.add_argument('-t', '--test', action='store_true', help='open and test each port')
    parser_detect.set_defaults(func=command_detect)

    parser_run = subparsers.add_parser('run', help='execute file contents on target')
    parser_run.add_argument('FILE', nargs='?', help='load this file contents')
    parser_run.add_argument('-t', '--timeout', type=float, default='10', help='wait x seconds for completion')
    parser_run.set_defaults(func=command_run, connect=True)

    parser_ls = subparsers.add_parser('ls', help='list files')
    parser_ls.add_argument('PATH', nargs='*', default='/', help='paths to list')
    parser_ls.add_argument('-l', '--long', action='store_true', help='show more info')
    parser_ls.add_argument('-r', '--recursive', action='store_true', help='list contents of directories')
    parser_ls.set_defaults(func=command_ls, connect=True)

    parser_cat = subparsers.add_parser('cat', help='print contents of one file')
    parser_cat.add_argument('PATH', help='filename on target')
    parser_cat.set_defaults(func=command_cat, connect=True)

    parser_pull = subparsers.add_parser('pull', help='file(s) to copy from target')
    parser_pull.add_argument('REMOTE', nargs='+', help='one or more source files/directories')
    parser_pull.add_argument('LOCAL', nargs=1, help='destination directory')
    parser_pull.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
    parser_pull.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
    parser_pull.set_defaults(func=command_pull, connect=True)

    parser_push = subparsers.add_parser('push', help='file(s) to copy onto target')
    parser_push.add_argument('LOCAL', nargs='+', help='one or more source files/directories')
    parser_push.add_argument('REMOTE', nargs=1, help='destination directory')
    parser_push.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
    parser_push.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
    parser_push.set_defaults(func=command_push, connect=True)

    parser_rm = subparsers.add_parser('rm', help='remove files on target')
    parser_rm.add_argument('PATH', nargs='+', help='filename on target')
    parser_rm.add_argument('-f', '--force', action='store_true', help='delete anyway / no error if not existing')
    parser_rm.add_argument('-r', '--recursive', action='store_true', help='remove directories recursively')
    parser_rm.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
    parser_rm.set_defaults(func=command_rm, connect=True)

    parser_df = subparsers.add_parser('df', help='Show filesytem information')
    parser_df.add_argument('PATH', nargs='?', default='/', help='remote path')
    parser_df.set_defaults(func=command_df, connect=True)

    parser_mount = subparsers.add_parser('mount', help='Make target files accessible via FUSE')
    parser_mount.add_argument('MOUNTPOINT', help='local mount point, directory must exist')
    parser_mount.add_argument('-e', '--explore', action='store_true', help='auto open file explorer at mount point')
    parser_mount.set_defaults(func=command_mount, connect=True)

    namespace, remaining_args = global_options.parse_known_args()
    args = parser.parse_args(remaining_args, namespace=namespace)

    user = UserMessages(args.verbose)

    if args.command or args.interactive:
        args.connect = True

    if args.connect:
        m = make_connection(user, args)
    else:
        m = None

    exitcode = 0
    try:
        if args.func:
            args.func(user, m, args)
        if args.command:
            if args.interactive:
                m.exec(args.command, timeout=0)
            else:
                user.output_text(m.exec(args.command))
        if args.reset:
            m.soft_reset()
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
