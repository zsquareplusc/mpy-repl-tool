#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016-2020 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
import binascii
import datetime
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


class FileCounter:
    """class to keep track of files processed, e.g. for push or pull operations"""

    def __init__(self):
        self.files = 0
        self.skipped = 0

    def add_file(self):
        self.files += 1

    def skip_file(self):
        self.skipped += 1

    def print_summary(self, user, action_verb, skipped_verb='skipped'):
        message = [
            '{files} files {action_verb}'.format(files=self.files, action_verb=action_verb)
        ]
        if self.skipped:
            message.append('{skipped} {skipped_verb}'.format(
                skipped=self.skipped,
                skipped_verb=skipped_verb))
        user.notice('{}\n'.format(', '.join(message)))


class UserMessages:
    """
    Provide a class with methods to interact with user. Makes it simpler to
    track verbosity flag.
    """
    def __init__(self, verbosity):
        self.verbosity = verbosity
        self.file_counter = FileCounter()

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
        if self.verbosity > 0:
            sys.stderr.write(message)

    def info(self, message):
        """informative messages to stderr, only if verbose flag is set"""
        if self.verbosity > 1:
            sys.stderr.write(message)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def make_connection(user, args, port=None):
    """make a connection, port overrides args.port"""
    m = repl_connection.MicroPythonRepl(port or args.port,
                                        args.baudrate,
                                        user=args.user,
                                        password=args.password)
    m.protocol.verbose = args.verbose > 2
    user.notice('port {} opened with {} baud\n'.format(m.serial.port, m.serial.baudrate))
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
    user.info('reading {}\n'.format(args.FILE))
    code = args.FILE.read()
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
    paths = sum((list(m.glob(src)) for src in args.PATH), [])
    if not paths:
        raise FileNotFoundError(2, 'cannot find: {}'.format(' '.join(args.PATH)))
    for path, st in paths:
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


def print_hash(user, path, st, hash_value):
    """output function for hashed file info"""
    user.output_text('{} {:>7} {} {}\n'.format(
        binascii.hexlify(hash_value).decode('ascii'),
        nice_bytes(st.st_size),
        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
        escaped(path)
        ))


def command_hash(user, m, args):
    """\
    Get hash of files on the targets file system.
    """
    paths = sum((list(m.glob(src)) for src in args.PATH), [])
    if not paths:
        raise FileNotFoundError(2, 'cannot find source: {}'.format(' '.join(args.PATH)))
    for path, st in paths:
        if args.recursive:
            if st.st_mode & stat.S_IFDIR:
                for dirpath, dir_stat, file_stat in m.walk(path):
                    for filename, st in file_stat:
                        path = posixpath.join(dirpath, filename)
                        print_hash(user, path, st, m.checksum_remote_file(path))
            else:
                print_hash(user, path, st, m.checksum_remote_file(path))
        else:
            if st.st_mode & stat.S_IFDIR:
                pass
            else:
                print_hash(user, path, st, m.checksum_remote_file(path))


def command_cat(user, m, args):
    """\
    Print the contents of a file from the target to stdout.
    """
    user.output_binary(m.read_from_file(args.PATH))


def remove_remote_file(user, m, remote_path, dry_run):
    user.info('rm {}\n'.format(remote_path))
    if not dry_run:
        user.file_counter.add_file()
        m.remove(remote_path)
    else:
        user.file_counter.skip_file()


def remove_remote_directory(user, m, remote_path, dry_run):
    user.info('rmdir {}\n'.format(remote_path))
    if not dry_run:
        m.rmdir(remote_path)


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
                            remove_remote_directory(user, m, posixpath.join(dirpath, name), args.dry_run)
                        for name, st in file_stat:
                            remove_remote_file(user, m, posixpath.join(dirpath, name), args.dry_run)
                    remove_remote_directory(user, m, path, args.dry_run)
                else:
                    remove_remote_directory(user, m, path, args.dry_run)
            else:
                remove_remote_file(user, m, path, args.dry_run)
    user.file_counter.print_summary(user, 'removed')


EXCLUDE_DIRS = [
    '__pycache__',
    '.git',
]


def ensure_dir(m, path):
    """ensure that path is a directory, make directory if needed"""
    try:
        st = m.stat(path)
    except FileNotFoundError:
        m.mkdir(path)
    else:
        if (st.st_mode & stat.S_IFDIR) == 0:
            raise FileExistsError('there is a file in the way: {}'.format(path))


def copy_remote_file(user, m, remote_path, local_path, dry_run):
    user.notice('{} -> {}\n'.format(remote_path, local_path))
    if not dry_run:
        user.file_counter.add_file()
        m.read_file(remote_path, local_path)
    else:
        user.file_counter.skip_file()


def command_pull(user, m, args):
    """\
    Copy a file from here to there.
    """
    dst = args.LOCAL[0]
    dst_dir = os.path.isdir(dst)
    dst_exists = os.path.exists(dst)
    # expand the patterns
    paths = sum((list(m.glob(src)) for src in args.REMOTE), [])
    if not paths:
        raise FileNotFoundError(2, 'cannot find source: {}'.format(' '.join(args.REMOTE)))
    elif len(paths) > 1:
        if dst_exists:
            if not dst_dir:
                raise ValueError('destination must be a directory: {}'.format(dst))
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
                        copy_remote_file(
                            user, m,
                            posixpath.join(dirpath, filename),
                            os.path.join(dst, relpath, filename),
                            args.dry_run)
            else:
                user.notice('skiping directory: {}\n'.format(path))
        else:
            if dst_dir:
                copy_remote_file(user, m, path, os.path.join(dst, posixpath.basename(path)), args.dry_run)
            else:
                copy_remote_file(user, m, path, dst, args.dry_run)
    user.file_counter.print_summary(user, 'copied', 'already up to date')


def push_file(user, m, local_path, remote_path, dry_run, force):
    """\
    copy a file to the target, if it is not already up to date. check with
    hash if copy is needed
    """
    if not dry_run:
        if force or m.checksum_local_file(local_path) != m.checksum_remote_file(remote_path):
            user.file_counter.add_file()
            user.notice('{} -> {}\n'.format(local_path, remote_path))
            m.write_file(local_path, remote_path)
        else:
            user.file_counter.skip_file()
            user.info('{}: already up to date\n'.format(remote_path))
    else:
        user.file_counter.skip_file()
        user.notice('dry run: {} -> {}\n'.format(local_path, remote_path))


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
    elif len(paths) > 1:
        if not dst_dir:
            raise ValueError('destination must be a directory: {}'.format(dst))
        if not dst_exists:
            raise ValueError('destination directory must exist: {}'.format(dst))
    for path in paths:
        if os.path.isdir(path):
            if os.path.basename(path) in EXCLUDE_DIRS:
                continue
            if args.recursive:
                root = os.path.dirname(path)
                for dirpath, dirnames, filenames in os.walk(path):
                    relpath = os.path.relpath(dirpath, root).split(os.path.sep)
                    if not args.dry_run:
                        ensure_dir(m, posixpath.join(dst, *relpath))
                    for dir in EXCLUDE_DIRS:
                        try:
                            dirnames.remove(dir)
                        except ValueError:
                            pass
                    for filename in filenames:
                        push_file(
                            user, m,
                            os.path.join(dirpath, filename),
                            posixpath.join(dst, *relpath, filename),
                            args.dry_run, args.force)
            else:
                user.notice('skiping directory: {}\n'.format(path))
        else:
            if dst_dir:
                push_file(
                    user, m,
                    path,
                    posixpath.join(dst, os.path.basename(path)),
                    args.dry_run, args.force)
            else:
                push_file(
                    user, m,
                    path,
                    dst,
                    args.dry_run, args.force)
    user.file_counter.print_summary(user, 'copied', 'already up to date')


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


def command_rtc(user, m, args):
    """read the real time clock (RTC)"""
    t1 = m.read_rtc()
    user.output_text('{:%Y-%m-%d %H:%M:%S.%f}\n'.format(t1))
    if args.test:
        time.sleep(1)
        t2 = m.read_rtc()
        user.output_text('{:%Y-%m-%d %H:%M:%S.%f}\n'.format(t2))
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
    parser_ls.add_argument('PATH', nargs='*', default='/', help='paths to list')
    parser_ls.add_argument('-l', '--long', action='store_true', help='show more info')
    parser_ls.add_argument('-r', '--recursive', action='store_true', help='list contents of directories')
    parser_ls.set_defaults(func=command_ls, connect=True)

    parser_hash = subparsers.add_parser('hash', help='hash files')
    parser_hash.add_argument('PATH', nargs='*', default='/', help='paths to list')
    parser_hash.add_argument('-r', '--recursive', action='store_true', help='list contents of directories')
    parser_hash.set_defaults(func=command_hash, connect=True)

    parser_cat = subparsers.add_parser('cat', help='print contents of one file')
    parser_cat.add_argument('PATH', help='filename on target')
    parser_cat.set_defaults(func=command_cat, connect=True)

    parser_pull = subparsers.add_parser('pull', help='file(s) to copy from target')
    parser_pull.add_argument('REMOTE', nargs='+', help='one or more source files/directories')
    parser_pull.add_argument('LOCAL', nargs=1, help='destination directory')
    parser_pull.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
    parser_pull.add_argument('--dry-run', action='store_true', help='do not actually copy anything from target')
    parser_pull.set_defaults(func=command_pull, connect=True)

    parser_push = subparsers.add_parser('push', help='file(s) to copy onto target')
    parser_push.add_argument('LOCAL', nargs='+', help='one or more source files/directories')
    parser_push.add_argument('REMOTE', nargs=1, help='destination directory')
    parser_push.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
    parser_push.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
    parser_push.add_argument('--force', action='store_true', help='write always, skip up-to-date check')
    parser_push.set_defaults(func=command_push, connect=True)

    parser_rm = subparsers.add_parser('rm', help='remove files from target')
    parser_rm.add_argument('PATH', nargs='+', help='filename on target')
    parser_rm.add_argument('-f', '--force', action='store_true', help='delete anyway / no error if not existing')
    parser_rm.add_argument('-r', '--recursive', action='store_true', help='remove directories recursively')
    parser_rm.add_argument('--dry-run', action='store_true', help='do not actually delete anything on target')
    parser_rm.set_defaults(func=command_rm, connect=True)

    parser_df = subparsers.add_parser('df', help='Show filesystem information')
    parser_df.add_argument('PATH', nargs='?', default='/', help='remote path')
    parser_df.set_defaults(func=command_df, connect=True)

    parser_mount = subparsers.add_parser('mount', help='Make target files accessible via FUSE')
    parser_mount.add_argument('MOUNTPOINT', help='local mount point, directory must exist')
    parser_mount.add_argument('-e', '--explore', action='store_true', help='auto open file explorer at mount point')
    parser_mount.set_defaults(func=command_mount, connect=True)

    parser_rtc_read = subparsers.add_parser('rtc', help='Read the real time clock (RTC)')
    parser_rtc_read.add_argument('--test', action='store_true', help='test if the clock runs')
    parser_rtc_read.set_defaults(func=command_rtc, connect=True)

    namespace, remaining_args = global_options.parse_known_args()
    args = parser.parse_args(remaining_args, namespace=namespace)

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
