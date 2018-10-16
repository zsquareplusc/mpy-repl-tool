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
import binascii
import fnmatch
import queue
import io
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
re_oserror = re.compile('OSError: (\[Errno )?(\d+)(\] )?')


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
        if lines[0].startswith('Traceback'):
            m = re_oserror.match(lines[-1])
            if m:
                err_num = int(m.group(2))
                if err_num == 2:
                    raise FileNotFoundError(2, 'File not found')
                elif err_num == 13:
                    raise PermissionError(13, 'Permission Error')
                elif err_num == 17:
                    raise FileExistsError(17, 'File Already Exists Error')
                elif err_num == 19:
                    raise OSError(err_num, 'No Such Device Error')
                elif err_num:
                    raise OSError(err_num, 'OSError')

    def exec_raw(self, string, timeout=3):
        """Exec code, returning (stdout, stderr)"""
        if self.verbose:
            sys.stderr.write(prefix(string, 'I: '))
        self.transport.write(string.encode('utf-8'))
        if self.response.qsize():
            self.response.get_nowait()
        self.transport.write(b'\x04')
        if timeout != 0:
            try:
                try:
                    data = self.response.get(timeout=timeout)
                except KeyboardInterrupt:
                    # forward to board, read output again to get the expected traceback message
                    self.transport.write(b'\x03')  # CTRL+C
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
                        sys.stderr.write(prefix(err.decode('utf-8'), 'E: '))
                return out[2:].decode('utf-8'), err.decode('utf-8')

    def exec(self, string, timeout=3):
        if not string.endswith('\n'):
            string += '\n'
        out, err = self.exec_raw(string, timeout)
        if err:
            self._parse_error(err)
            raise IOError('execution failed: {}: {}'.format(out, err))
        return out


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

    def interrupt(self):
        """Interrupt currently running code"""
        self.serial.write(b'\x03\x03')  # CTRL+C twice

    def close(self, interrupt=True):
        """Stop reader thread and close serial port"""
        if interrupt:
            self.serial.write(b'\x03\x02')  # exit raw repl mode, and interrupt
        else:
            self.serial.write(b'\x02')  # exit raw repl mode
        self._thread.close()

    def exec_raw(self, *args, **kwargs):
        """Execute the string on the target and return its stdout and stderr."""
        return self.protocol.exec_raw(*args, **kwargs)

    def exec(self, *args, **kwargs):
        """\
        Execute the string on the target and return its output.
        Raise Exception on remote errors.
        """
        return self.protocol.exec(*args, **kwargs)

    def evaluate(self, string):
        """
        Execute a string on the target and return its output parsed as python
        literal. Works for simple constructs such as numbers, lists,
        dictionaries.
        """
        return ast.literal_eval(self.exec(string))

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def soft_reset(self):
        self.protocol.transport.write(b'\x03\x04')
        # XXX read startup message

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
        # reading (lines * linesize) must not take more than 1sec and 2K target RAM!
        lines = max(1, self.serial.baudrate // 9600)
        linesize = 510  # must be multiple of 3 to avoid padding in base64
        # use the fact that Python joins adjacent consecutive strings
        # for the snippet here and for the remotely printed lines!
        self.exec(
            'import ubinascii; _f = open({!r}, "rb")\n'
            'def _b():\n'
            '  print("(b\'\'")\n'
            '  for _ in range({}):\n'
            '    block = _f.read({})\n'
            '    if not block: break\n'
            '    print(ubinascii.b2a_base64(block)[:-1])\n'
            '  print(")")'.format(str(path), lines, linesize))
        contents = b''
        while True:
            block = self.evaluate('_b()')
            if not block:
                break
            contents += binascii.a2b_base64(block)
        self.exec('_f.close(); del _f; del _b')
        return contents

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
        # writing (lines * linesize) must not take more than 1sec and 2K target RAM!
        lines = max(1, min(16, self.serial.baudrate // 2400))
        linesize = 72
        # linesize = 128
        self.exec('import ubinascii; _f = open({!r}, "wb")'.format(str(path)))
        with io.BytesIO(contents) as cfile:
            while True:
                block = cfile.read(linesize * lines)
                if not block:
                    break
                block_base64 = binascii.b2a_base64(block)
                byte_lines = [repr(block_base64[i:i + linesize]) for i in range(0, len(block_base64), linesize)]
                self.exec('_f.write(ubinascii.a2b_base64(\n' + '\n'.join(byte_lines) + '))')
        self.exec('_f.close(); del _f')

    def truncate(self, path, length):
        # MicroPython 1.9.3 has no file.truncate(), but open(...,"ab"); write(b"") seems to work.
        return self.evaluate(
            '_f = open({!r}, "ab")\n'
            'print(_f.seek({}))\n'
            '_f.write(b"")\n'
            '_f.close(); del _f'.format(str(path), int(length)))

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
        parts = pattern.split('/')
        if pattern.startswith('/'):
            parts = parts[1:]
        if pattern.endswith('/'):
            parts = parts[:-1]
        if not parts:
            yield ('/', self.stat('/'))
        if len(parts) == 2 and parts[0] == '**':
            #  include root
            yield from self._glob('/', parts[1:])
        # this is the main recursive search
        if parts:
            yield from self._glob('/', parts)

    def _glob(self, root, parts):
        """recursive search yielding matches"""
        dirnames = []
        scandirnames = []
        filenames = []
        try:
            for name, st in self.listdir(root):
                if (st.st_mode & stat.S_IFDIR) != 0:
                    if len(parts) == 1 and parts[0] != '**' and fnmatch.fnmatch(name, parts[0]):
                        dirnames.append((name, st))
                    if parts[0] == '**' or fnmatch.fnmatch(name, parts[0]):
                        scandirnames.append((name, st))
                else:
                    if len(parts) == 1 and parts[0] != '**':
                        if fnmatch.fnmatch(name, parts[0]):
                            filenames.append((name, st))
            if len(parts) > 1:
                # there are more parts in the pattern, scan subdirectories
                for dirname, st in scandirnames:
                    yield from self._glob(posixpath.join(root, dirname), parts[1:])
                if parts[0] == '**':
                    # the ** pattern means any depth, so also search with the pattern still included
                    for dirname, st in scandirnames:
                        yield from self._glob(posixpath.join(root, dirname), parts[:])
            else:
                yield from ((posixpath.join(root, name), st) for name, st in dirnames)
            yield from ((posixpath.join(root, name), st) for name, st in filenames)
        except OSError:
            pass
