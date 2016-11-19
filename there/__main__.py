#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
import ast
import posixpath
import queue
import os
import sys
import time
import traceback
import serial
import serial.threaded
import serial.tools.miniterm
from .speaking import nice_bytes, mode_to_chars
from .string_escape import escaped


def prefix(text, prefix):
    return ''.join('{}{}\n'.format(prefix, line) for line in text.splitlines())


class MicroPythonReplProtocol(serial.threaded.Packetizer):

    TERMINATOR = b'\x04>'

    def  __init__(self, *args, **kwargs):
         super().__init__(*args, **kwargs)
         self.response = queue.Queue()
         self.verbose = False

    def connection_made(self, transport):
        super().connection_made(transport)
        #~ sys.stderr.write('port opened\n')


    def handle_packet(self, data):
        #~ sys.stderr.write('response received: {!r}\n'.format(data))
        self.response.put(data)

    def connection_lost(self, exc):
        if exc:
            traceback.print_exc(exc)
        #~ sys.stderr.write('port closed\n')

    def exec(self, string, timeout=3):
        if self.verbose:
            sys.stderr.write(prefix(string, 'I: '))
        self.transport.write(string.encode('utf-8'))
        if self.response.qsize():
            self.response.get_nowait()
        self.transport.write(b'\x04')
        try:
            data = self.response.get(timeout=timeout)
        except queue.Empty:
            raise IOError('timeout')
        else:
            out, err = data.split(b'\x04')
            if not out.startswith(b'OK'):
                raise IOError('data was not accepted: {}: {}'.format(out, err))
            if self.verbose:
                sys.stderr.write(prefix(out[2:].decode('utf-8'), 'O: '))  # XXX indent
            if err:
                if self.verbose:
                    sys.stderr.write(prefix(err.decode('utf-8'), 'E: '))  # XXX indent
                raise IOError('execution failed: {}: {}'.format(out, err))
            return out[2:].decode('utf-8')


class MicroPythonRepl(object):
    def __init__(self, port='hwgrep://VID:PID=1A86:7523', baudrate=115200):
        self.serial = None
        self.serial = serial.serial_for_url(port, baudrate=baudrate, timeout=1)
        self.serial.write(b'\x03')  # CTRL+C
        time.sleep(0.2)
        self.serial.write(b'\x03\x01')  # enter raw repl mode
        time.sleep(0.2)
        self.serial.reset_input_buffer()

        self._thread = serial.threaded.ReaderThread(self.serial, MicroPythonReplProtocol)
        self._thread.daemon = True
        self._thread.start()
        self.transport, self.protocol = self._thread.connect()

    def close(self, interrupt=True):
        if interrupt:
            self.serial.write(b'\x03\x02')  # enter raw repl mode
        self._thread.close()

    def exec(self, string):
        return self.protocol.exec(string)

    def statvfs(self, path):
        st = ast.literal_eval(self.protocol.exec('import os; print(os.statvfs({!r}))'.format(str(path))))
        return os.statvfs_result(st)
        #~ f_bsize, f_frsize, f_blocks, f_bfree, f_bavail, f_files, f_ffree, f_favail, f_flag, f_namemax

    def stat(self, path):
        st = ast.literal_eval(self.protocol.exec('import os; print(os.stat({!r}))'.format(str(path))))
        return os.stat_result(st)

    def remove(self, path):
        return ast.literal_eval(self.protocol.exec('import os; print(os.remove({!r}))'.format(str(path))))

    def rename(self, path, path_to):
        return ast.literal_eval(self.protocol.exec('import os; print(os.rename({!r}, {!r}))'.format(str(path), str(path_to))))

    def mkdir(self, path):
        return ast.literal_eval(self.protocol.exec('import os; print(os.mkdir({!r}))'.format(str(path))))

    def rmdir(self, path):
        return ast.literal_eval(self.protocol.exec('import os; print(os.rmdir({!r}))'.format(str(path))))

    def read_file(self, path):
        # use the fact that Python joins adjacent consecutive strings
        # for the snippet here as well as for the data returned from target
        return b''.join(ast.literal_eval(self.protocol.exec(
            '_f = open({!r}, "rb")\n'
            'print("[")\n'
            'while True:\n'
            '    _b = _f.read()\n'
            '    if not _b: break\n'
            '    print(_b, ",")\n'
            'print("]")\n'
            '_f.close(); del _f; del _b'.format(str(path)))))

    def write_file(self, local_filename, path=None):
        if path is None:
            path = local_filename
        with open(local_filename, 'rb') as f:
            self.write_to_file(path, f.read())

    def write_to_file(self, path, contents):
        """\
        Write contents (expected to be bytes) to path on the target.
        """
        if not isinstance(contents, (bytes, bytearray)):
            raise TypeError('contents must be bytes/bytearray, got {} instead'.format(type(contents)))
        blocksize = 128
        self.protocol.exec('_f = open({!r}, "wb")'.format(str(path)))
        for i in range(0, len(contents), blocksize):
            self.protocol.exec('_f.write({!r})'.format(contents[i:i+blocksize]))
        self.protocol.exec('_f.close(); del _f;')

    def truncate(self, path):
        # use the fact that Python joins adjacent consecutive strings
        # for the snippet here as well as for the data returned from target
        return ast.literal_eval(self.protocol.exec(
            '_f = open({!r}, "rw")\n'
            '_f.seek({})\n'
            '_f.truncate()\n'
            '_f.close(); del _f; del _b'.format(str(path), int(length))))

    def ls(self, path):
        return ast.literal_eval(
            self.protocol.exec('import os; print(os.listdir({path!r}))'.format(path=path)))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def command_detect(m, args):
    """\
    Help finding MicroPython boards.
    """
    # list all serial ports
    for info in serial.tools.list_ports.comports():
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

    if args.connect:
        m = MicroPythonRepl(args.port, args.baudrate)
        if args.verbose:
            m.protocol.verbose = args.verbose
    else:
        m = None

    exitcode = 0
    try:
        if args.func:
            args.func(m, args)
        if args.command:
            if m is None:
                m = MicroPythonRepl(args.port, args.baudrate)
            sys.stdout.write(m.exec(args.command))
    except Exception as e:
        sys.stderr.write('ERROR: command failed: {}\n'.format(e))
        exitcode = 1

    if args.interactive:
        if m is None:
            m = MicroPythonRepl(args.port, args.baudrate)
        port = m.serial.name
        baudrate = m.serial.baudrate
        m.close(interrupt=False)
        sys.argv = ['n/a']
        serial.tools.miniterm.main(port, baudrate)

    sys.exit(exitcode)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    main()
