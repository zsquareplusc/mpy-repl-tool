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


class MicroPythonRawRepl(serial.threaded.Packetizer):

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
            sys.stderr.write('> {}\n'.format(string))  # XXX debug output
        self.transport.write(string.encode('utf-8'))
        if self.response.qsize():
            self.response.get_nowait()
        self.transport.write(b'\x04')
        data = self.response.get(timeout)
        out, err = data.split(b'\x04')
        if not out.startswith(b'OK'):
            raise IOError('data was not accepted: {}: {}'.format(out, err))
        if err:
            sys.stderr.write(err.decode('utf-8'))
            raise IOError('execution failed: {}: {}'.format(out, err))
        return out[2:].decode('utf-8')


class MicroPythonSync(object):
    def __init__(self, port='hwgrep://VID:PID=1A86:7523'):
        self.serial = None
        self.serial = serial.serial_for_url(port, baudrate=115200, timeout=1)
        self.serial.write(b'\x03')  # CTRL+C
        time.sleep(0.2)
        self.serial.write(b'\x03\x01')  # enter raw repl mode
        time.sleep(0.2)
        self.serial.reset_input_buffer()

        self._thread = serial.threaded.ReaderThread(self.serial, MicroPythonRawRepl)
        self._thread.daemon = True
        self._thread.start()
        self.transport, self.protocol = self._thread.connect()

    def close(self):
        self.serial.write(b'\x03\x02') # enter raw repl mode
        self._thread.close()

    def exec(self, string):
        return self.protocol.exec(string)

    def read_file(self, path):
        # use the fact that python joins adjacent consecutive strings
        # for the snippet here as well as for the data returned from target
        return ast.literal_eval(self.protocol.exec(
            '_f = open({!r}, "rb")\n'
            'while True:\n'
            '    _b = _f.read()\n'
            '    if not _b: break\n'
            '    print(_b)\n'
            '_f.close(); del _f; del _b'.format(str(path))))

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

    def mkdir(self, path):
        self.protocol.exec('import os; os.mkdir({path!r})'.format(path=path))

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
    sys.stdout.write(m.exec(open(args.FILE).read()))


def command_ls(m, args):
    """\
    List files on the targets file system.
    """
    # XXX support --long format
    for path in args.path:
        sys.stdout.write(' '.join(m.ls(path)))
    sys.stdout.write('\n')


def command_cat(m, args):
    """\
    Print the contents of a file from the target to stdout.
    """
    sys.stdout.buffer.write(m.read_file(args.path))
    sys.stdout.buffer.write(b'\n')


def command_put(m, args):
    """\
    Copy a file from here to there.
    """
    for path in args.path:
        # XXX smarter handling of directories, just cutting the path away is not so good.
        m.write_file(path, os.path.basename(path))


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Do stuff via the MicroPython REPL')

    parser.add_argument('-c', '--command', help='execute given code on target')
    parser.add_argument('-i', '--interactive', action='store_true', help='drop to interactive shell at the end')
    parser.add_argument('-v', '--verbose', action='store_true', help='show diagnostic messages')
    parser.set_defaults(connect=True)

    subparsers = parser.add_subparsers(help='sub-command help')

    parser_detect = subparsers.add_parser('detect', help='help locating a board')
    parser_detect.set_defaults(func=command_detect, connect=False)

    parser_run = subparsers.add_parser('run', help='execute file contents on target')
    parser_run.add_argument('FILE', nargs='?', help='load this file contents')
    parser_run.set_defaults(func=command_run)

    parser_ls = subparsers.add_parser('ls', help='list files')
    parser_ls.add_argument('path', nargs='*', default='/', help='paths to list')
    parser_ls.set_defaults(func=command_ls)

    parser_cat = subparsers.add_parser('cat', help='print content of one file')
    parser_cat.add_argument('path', help='filename on target')
    parser_cat.set_defaults(func=command_cat)

    parser_put = subparsers.add_parser('put', help='file(s) to copy onto target')
    parser_put.add_argument('path', nargs='+', help='files to copy')
    parser_put.set_defaults(func=command_put)

    args = parser.parse_args()

    if args.connect:
        m = MicroPythonSync()
    else:
        m = None

    if args.verbose and m:
        m.protocol.verbose = args.verbose

    if args.func:
        args.func(m, args)

    if args.command:
        sys.stdout.write(m.exec(args.command))

    if args.interactive:
        port = m.serial.name
        baudrate = m.serial.baudrate
        m.close()
        sys.argv = ['n/a']
        serial.tools.miniterm.main(port, baudrate)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    main()
