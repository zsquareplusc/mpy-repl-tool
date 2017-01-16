#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""
Remote code execution and file transfer support module for connections via a
REPL (Read Eval Print Loop) such as it is usual for MicroPython.

There are also helper functions like glob(), walk() and listdir(). These,
unlike their counterparts on the host, return tuples of names and stat
information, not just names. This done to make the data transfer more efficient
as most higher level operations will need stat info.

Note: The protocol uses MicroPython specific conrol codes to switch to a raw
REPL mode, so the current implementation is not generic for any Python REPL!
"""
import ast
import fnmatch
import queue
import os
import posixpath
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
                    raise FileNotFoundError(2, 'File not found')
                elif err_num == 13:
                    raise PermissionError(13, 'Permission Error')
                elif err_num == 17:
                    raise FileExistsError(17, 'File Already Exists Error')
                elif err_num:
                    raise OSError(err_num, 'OSError')

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
    def __init__(self, port='hwgrep://USB', baudrate=115200, user=None, password=None):
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
        """Stop reader thread keep serial port open"""
        if interrupt:
            self.serial.write(b'\x03\x02')  # exit raw repl mode, and interrupt
        else:
            self.serial.write(b'\x02')  # exit raw repl mode
        self._thread.stop()

    def close(self, interrupt=True):
        """Stop reader thread and close serial port"""
        if interrupt:
            self.serial.write(b'\x03\x02')  # exit raw repl mode, and interrupt
        else:
            self.serial.write(b'\x02')  # exit raw repl mode
        self._thread.close()

    def exec(self, *args, **kwargs):
        """Execute the string on the target and return its output."""
        return self.protocol.exec(*args, **kwargs)

    def evaluate(self, string):
        """
        Execute a string on the target and return its output parsed as python
        literal. Works for simple constructs such as numbers, lists,
        dictionaries.
        """
        return ast.literal_eval(self.exec(string))

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def statvfs(self, path):
        """return stat information about remote filesystem"""
        st = self.evaluate('import os; print(os.statvfs({!r}))'.format(str(path)))
        return os.statvfs_result(st)
        #~ f_bsize, f_frsize, f_blocks, f_bfree, f_bavail, f_files, f_ffree, f_favail, f_flag, f_namemax

    def _override_stat(self, st):
        # XXX fake some attributes: rw, uid/gid
        st = list(st)
        st[stat.ST_MODE] |= 0o660
        try:
            st[stat.ST_GID] = os.getgid()
            st[stat.ST_UID] = os.getuid()
        except AttributeError:
            pass  # Windwos
        return st

    def stat(self, path, fake_attrs=False):
        """return stat information about path on remote"""
        st = self.evaluate('import os; print(os.stat({!r}))'.format(str(path)))
        if fake_attrs:
            st = self._override_stat(st)
        return os.stat_result(st)

    def remove(self, path):
        return self.evaluate('import os; print(os.remove({!r}))'.format(str(path)))

    def rename(self, path, path_to):
        return self.evaluate('import os; print(os.rename({!r}, {!r}))'.format(str(path), str(path_to)))

    def mkdir(self, path):
        return self.evaluate('import os; print(os.mkdir({!r}))'.format(str(path)))

    def rmdir(self, path):
        return self.evaluate('import os; print(os.rmdir({!r}))'.format(str(path)))

    def read_file(self, path, local_filename):
        """copy a file from remote to local filesystem"""
        with open(local_filename, 'wb') as f:
            f.write(self.read_from_file(path))

    def read_from_file(self, path):
        """Return the contents of a remote file as byte string"""
        # use the fact that Python joins adjacent consecutive strings
        # for the snippet here
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
        """Copy a file from local to remote filesystem"""
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

    def listdir(self, path, fake_attrs=False):
        """
        Return a list of tuples of filenames and stat info of given remote
        path.
        """
        if not path.startswith('/'):
            raise ValueError('only absolute paths are supported (beginning with "/"): {!r}'.format(path))
        if path == '/':
            files_and_stat = self.evaluate(
                    'import os; print([(n, os.stat("/" + n)) for n in os.listdir("/")])')
        else:
            files_and_stat = self.evaluate(
                    'import os; print([(n, os.stat({path!r} + "/" + n)) for n in os.listdir({path!r})])'.format(path=path))
        if fake_attrs:
            files_and_stat = [(n, self._override_stat(st)) for (n, st) in files_and_stat]
        return [(n, os.stat_result(st)) for (n, st) in files_and_stat]

    def walk(self, dirpath, topdown=True):
        """
        Recursively scan remote path and yield tuples of (dirpath, dir_st, file_st).
        Where dir_st and file_st are lists of tuples of name and stat info.
        """
        dirnames = []
        filenames = []
        for name, st in self.listdir(dirpath):
            if (st.st_mode & stat.S_IFDIR) != 0:
                dirnames.append((name, st))
            else:
                filenames.append((name, st))
        if topdown:
            yield dirpath, dirnames, filenames
            for dirname, st in dirnames:
                yield from self.walk(posixpath.join(dirpath, dirname))
        else:
            for dirname, st in dirnames:
                yield from self.walk(posixpath.join(dirpath, dirname))
            yield dirpath, dirnames, filenames

    def glob(self, pattern):
        """Pattern match files on remote. Returns a list of tuples of name and stat info"""
        path, namepat = posixpath.split(pattern)
        # XXX does not handle patterns in path
        if not namepat:
            namepat = '*'
        entries = self.listdir(path)
        return ((posixpath.join(path, p), st) for p, st in entries if fnmatch.fnmatch(p, namepat))

