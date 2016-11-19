#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
import posixpath
import os
import sys
import time
import serial.tools.list_ports
import serial.tools.miniterm
from .speaking import nice_bytes, mode_to_chars
from .string_escape import escaped
from . import repl_connection


def make_connection(args, port=None):
    """make a conenction, port overrides args.port"""
    m = repl_connection.MicroPythonRepl(port or args.port, args.baudrate)
    m.protocol.verbose = args.verbose
    return m


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def command_detect(m, args):
    """\
    Help finding MicroPython boards.

    By default it simply lists all serial ports. If --test is used, each of
    the ports is opened (with the given --baudrate) and tested for a Python
    prompt. If there is no response it runs in a timout, so this option is
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
    sys.stdout.write(m.exec(open(args.FILE).read()))


def command_ls(m, args):
    """\
    List files on the targets file system.
    """
    for path in args.PATH:
        if args.long:
            files = m.ls(path)
            files.sort()
            for filename in files:
                st = m.stat(posixpath.join(path, filename))
                sys.stdout.write('{} {:4} {:4} {:>7} {} {}\n'.format(
                    mode_to_chars(st.st_mode),
                    st.st_uid if st.st_uid is not None else 'NONE',
                    st.st_gid if st.st_gid is not None else 'NONE',
                    nice_bytes(st.st_size),
                    time.strftime('%Y-%m-%d %02H:%02M:%02S', time.localtime(st.st_mtime)),
                    escaped(filename)))
        else:
            sys.stdout.write(' '.join(m.ls(path)))
            sys.stdout.write('\n')


def command_cat(m, args):
    """\
    Print the contents of a file from the target to stdout.
    """
    sys.stdout.buffer.write(m.read_file(args.PATH))
    sys.stdout.buffer.write(b'\n')


def command_rm(m, args):
    """\
    Remove files on target
    """
    for path in args.PATH:
        m.remove(path)


def command_put(m, args):
    """\
    Copy a file from here to there.
    """
    for path in args.PATH:
        # XXX smarter handling of directories, just cutting the path away is not so good.
        m.write_file(path, os.path.basename(path))


def command_mount(m, args):
    """\
    Mount the target as file system via FUSE.
    """
    from . import fuse_drive
    import subprocess
    if args.explore:
        subprocess.call(["xdg-open", args.MOUNTPOINT])
    try:
        fuse_drive.mount(m, args.MOUNTPOINT)
    except RuntimeError:
        sys.stderr.write('ERROR: Could not mount - note: directory must exist\n')

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Do stuff via the MicroPython REPL')

    parser.add_argument('-p', '--port', default=os.environ.get('MPY_PORT', 'hwgrep://USB'), help='set the serial port')
    parser.add_argument('-b', '--baudrate', default=os.environ.get('MPY_BAUDRATE', '115200'), type=int, help='set the baud rate')
    parser.add_argument('-c', '--command', help='execute given code on target')
    parser.add_argument('-i', '--interactive', action='store_true', help='drop to interactive shell at the end')
    parser.add_argument('-v', '--verbose', action='store_true', help='show diagnostic messages')
    parser.set_defaults(connect=False, func=lambda m, args: 0)

    subparsers = parser.add_subparsers(help='sub-command help')

    parser_detect = subparsers.add_parser('detect', help='help locating a board')
    parser_detect.add_argument('-t', '--test', action='store_true', help='open and test each port')
    parser_detect.set_defaults(func=command_detect)

    parser_run = subparsers.add_parser('run', help='execute file contents on target')
    parser_run.add_argument('FILE', nargs='?', help='load this file contents')
    parser_run.set_defaults(func=command_run, connect=True)

    parser_ls = subparsers.add_parser('ls', help='list files')
    parser_ls.add_argument('PATH', nargs='*', default='/', help='paths to list')
    parser_ls.add_argument('-l', '--long', action='store_true', help='show more info')
    parser_ls.set_defaults(func=command_ls, connect=True)

    parser_cat = subparsers.add_parser('cat', help='print content of one file')
    parser_cat.add_argument('PATH', help='filename on target')
    parser_cat.set_defaults(func=command_cat, connect=True)

    parser_put = subparsers.add_parser('put', help='file(s) to copy onto target')
    parser_put.add_argument('PATH', nargs='+', help='files to copy')
    parser_put.set_defaults(func=command_put, connect=True)

    parser_rm = subparsers.add_parser('rm', help='remove files on target')
    parser_rm.add_argument('PATH', nargs='+', help='filename on target')
    parser_rm.set_defaults(func=command_rm, connect=True)

    parser_mount = subparsers.add_parser('mount', help='Make target files accessible via FUSE')
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
        sys.stderr.write('ERROR: action or command failed: {}\n'.format(e))
        exitcode = 1

    if args.interactive:
        port = m.serial.name
        baudrate = m.serial.baudrate
        m.close(interrupt=False)
        sys.argv = ['n/a', '-f', 'direct']
        serial.tools.miniterm.main(port, baudrate)

    sys.exit(exitcode)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    main()
