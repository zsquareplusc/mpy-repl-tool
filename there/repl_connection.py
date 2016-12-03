#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
import ast
import queue
import os
import re
import stat
import sys
import time
import traceback
import serial
import serial.threaded

# match "OSError: [Errno 2] ENOENT" and "OSError: 2"
re_oserror = re.compile(b'OSError: (\[Errno )?(\d+)(\] )?')


def prefix(text, prefix):
    return ''.join('{}{}\n'.format(prefix, line) for line in text.splitlines())


class MicroPythonReplProtocol(serial.threaded.Packetizer):

    TERMINATOR = b'\x04>'

    def __init__(self, *args, **kwargs):
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

    def _parse_error(self, text):
        """Read the error message and convert exceptions"""
        lines = text.splitlines()
        if lines[0].startswith(b'Traceback'):
            m = re_oserror.match(lines[-1])
            if m:
                err_num = int(m.group(2))
                if err_num == 2:
                    raise FileNotFoundError(2)
                elif err_num == 13:
                    raise PermissionError(13)
                elif err_num == 17:
                    raise FileExistsError(17)
                elif err_num:
                    raise OSError(err_num)

    def exec(self, string, timeout=3):
        if self.verbose:
            sys.stderr.write(prefix(string, 'I: '))
        self.transport.write(string.encode('utf-8'))
        if self.response.qsize():
            self.response.get_nowait()
        self.transport.write(b'\x04')
        if timeout != 0:
            try:
                data = self.response.get(timeout=timeout)
            except queue.Empty:
                raise IOError('timeout')
            else:
                out, err = data.split(b'\x04')
                if not out.startswith(b'OK'):
                    raise IOError('data was not accepted: {}: {}'.format(out, err))
                if self.verbose:
                    sys.stderr.write(prefix(out[2:].decode('utf-8'), 'O: '))
                if err:
                    if self.verbose:
                        sys.stderr.write(prefix(err.decode('utf-8'), 'E: '))
                    self._parse_error(err)
                    raise IOError('execution failed: {}: {}'.format(out, err))
                return out[2:].decode('utf-8')


class MicroPythonRepl(object):
    def __init__(self, port='hwgrep://VID:PID=1A86:7523', baudrate=115200, user=None, password=None):
        self.serial = None
        self.serial = serial.serial_for_url(port, baudrate=baudrate, timeout=1)
        if user is not None:
            time.sleep(0.1)
            self.serial.read_until(b'Login as: ')
            time.sleep(0.1)
            self.serial.write(user.encode('utf-8'))
            self.serial.write(b'\r\n')
        if password is not None:
            self.serial.read_until(b'Password: ')
            time.sleep(0.1)
            self.serial.write(password.encode('utf-8'))
            self.serial.write(b'\r\n')
            time.sleep(0.1)
        self.serial.write(b'\x03\x02')  # CTRL+C, exit raw repl
        time.sleep(0.2)
        self.serial.write(b'\x03\x01')  # CTRL+C, enter raw repl mode
        time.sleep(0.2)
        if port.startswith('socket://'):
            # hack as reset_input_buffer does not clear anything on socket connections as of pySerial 3.1
            self.serial._socket.recv(10000)  # clear input, use timeout
        else:
            self.serial.reset_input_buffer()

        self._thread = serial.threaded.ReaderThread(self.serial, MicroPythonReplProtocol)
        self._thread.daemon = True
        self._thread.start()
        self.transport, self.protocol = self._thread.connect()

    def stop(self, interrupt=True):
        if interrupt:
            self.serial.write(b'\x03\x02')  # exit raw repl mode, and interrupt
        else:
            self.serial.write(b'\x02')  # exit raw repl mode
        self._thread.stop()

    def close(self, interrupt=True):
        if interrupt:
            self.serial.write(b'\x03\x02')  # exit raw repl mode, and interrupt
        else:
            self.serial.write(b'\x02')  # exit raw repl mode
        self._thread.close()

    def exec(self, *args, **kwargs):
        """execute the string on the target and return its output"""
        return self.protocol.exec(*args, **kwargs)

    def evaluate(self, string):
        """execute string on the target and return its output parsed as python literal"""
        return ast.literal_eval(self.exec(string))

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def statvfs(self, path):
        st = self.evaluate('import os; print(os.statvfs({!r}))'.format(str(path)))
        return os.statvfs_result(st)
        #~ f_bsize, f_frsize, f_blocks, f_bfree, f_bavail, f_files, f_ffree, f_favail, f_flag, f_namemax

    def stat(self, path, fake_attrs=False):
        st = self.evaluate('import os; print(os.stat({!r}))'.format(str(path)))
        if fake_attrs:
            # XXX fake some attributes: rw, uid/gid
            st = list(st)
            st[stat.ST_MODE] |= 0o660
            try:
                st[stat.ST_GID] = os.getgid()
                st[stat.ST_UID] = os.getuid()
            except AttributeError:
                pass  # Windwos
        return os.stat_result(st)

    def remove(self, path):
        return self.evaluate('import os; print(os.remove({!r}))'.format(str(path)))

    def rename(self, path, path_to):
        return self.evaluate('import os; print(os.rename({!r}, {!r}))'.format(str(path), str(path_to)))

    def mkdir(self, path):
        return self.evaluate('import os; print(os.mkdir({!r}))'.format(str(path)))

    def rmdir(self, path):
        return self.evaluate('import os; print(os.rmdir({!r}))'.format(str(path)))

    def read_file(self, path):
        # use the fact that Python joins adjacent consecutive strings
        # for the snippet here as well as for the data returned from target
        return b''.join(self.evaluate(
            '_f = open({!r}, "rb")\n'
            'print("[")\n'
            'while True:\n'
            '    _b = _f.read()\n'
            '    if not _b: break\n'
            '    print(_b, ",")\n'
            'print("]")\n'
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
        self.exec('_f = open({!r}, "wb")'.format(str(path)))
        for i in range(0, len(contents), blocksize):
            self.exec('_f.write({!r})'.format(contents[i:i+blocksize]))
        self.exec('_f.close(); del _f;')

    def truncate(self, path, length):
        return self.evaluate(
            '_f = open({!r}, "rw")\n'
            '_f.seek({})\n'
            'print(_f.truncate())\n'
            '_f.close(); del _f; del _b'.format(str(path), int(length)))

    def ls(self, path, fake_attrs=False):
        files_and_stat = self.evaluate('import os; print([(n, os.stat({path!r} + "/" + n)) for n in os.listdir({path!r})])'.format(path=path))
        return [(n, os.stat_result(st)) for (n, st) in files_and_stat]
