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
        try:
            st = ast.literal_eval(self.protocol.exec('import os; print(os.stat({!r}))'.format(str(path))))
        except IOError as e:
            if 'ENOENT' in str(e):
                raise FileNotFoundError(path)
            raise
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

