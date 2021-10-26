#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2016-2021 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""
Remote code execution and file transfer support module for connections via a
REPL (Read Eval Print Loop) such as it is usual for MicroPython.

Note: The protocol uses MicroPython specific control codes to switch to a raw
REPL mode, so the current implementation is not generic for any Python REPL!
"""
import builtins
import ast
import binascii
import datetime
import queue
import io
import hashlib
import os
import pathlib
import re
import stat
import sys
import time
import traceback
import serial
import serial.threaded
from . import os_error_list
from .walk import walk


# match "OSError: [Errno 2] ENOENT" and "OSError: 2"
re_oserror = re.compile(r'OSError: (\[Errno )?(\d+)(\] )?')
re_exceptions = re.compile(r'(ValueError|KeyError|ImportError): (.*)')


def prefix(text, prefix):
    return ''.join('{} {}: {!r}\n'.format(prefix, n, line) for n, line in enumerate(text.splitlines(), 1))


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
            if self.verbose:
                traceback.print_exception(type(exc), exc, exc.__traceback__)
            else:
                sys.stderr.write(f'Error accessing serial port: {exc}\n')
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
                    raise OSError(
                        err_num,
                        os_error_list.os_error_mapping.get(err_num, (None, 'OSError'))[1])
            m = re_exceptions.match(lines[-1])
            if m:
                raise getattr(builtins, m.group(1))(m.group(2))

    def exec_raw(self, string, timeout=5):
        """Exec code, returning (stdout, stderr)"""
        if self.verbose:
            sys.stderr.write(prefix(string, 'I'))
        self.transport.write(string.encode('utf-8'))
        # self.buffer.clear()
        while self.response.qsize():
            garbage = self.response.get_nowait()
            sys.stderr.write(prefix(garbage, 'ignored'))
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
                try:
                    out, err = data.split(b'\x04')
                except ValueError:
                    raise IOError(f'CTRL-D missing in response: {data!r}')
                # if not out.startswith(b'OK'):
                if b'OK' not in out:
                    raise IOError(f'data was not accepted: {out}: {err}')
                if self.verbose:
                    sys.stderr.write(prefix(out[2:].decode('utf-8'), 'O'))
                    if err:
                        sys.stderr.write(prefix(err.decode('utf-8'), 'E'))
                return out[2:].decode('utf-8'), err.decode('utf-8')
        else:
            return '', ''  # dummy output if timeout=0 was specified

    def exec(self, string, timeout=3):
        if not string.endswith('\n'):
            string += '\n'
        out, err = self.exec_raw(string, timeout)
        if err:
            self._parse_error(err)
            raise IOError(f'execution failed: {out}: {err}')
        return out


class MicroPythonRepl(object):
    def __init__(self, port='hwgrep://USB', baudrate=115200, user=None, password=None):
        self.serial = None
        self.serial = serial.serial_for_url(port, baudrate=baudrate, timeout=1, exclusive=True)
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
        :param str code: code to execute
        :returns: all output as text
        :rtype: str
        :raises IOError: execution failed

        Execute the string and returns the output as string. It may contain
        multiple lines.

        The executed code should use ``print()`` to construct the answer, e.g.
        ``print(repr(obj))``. It is also possible to use multiple print statements
        to construct the response, e.g. to create a list with many entries. As
        printed lines are transferred immediately and the PC caches the data, it
        is possible to create very large responses.

        If the target raises an exception, this function will raise an
        exception too. The type depends on the exception. An ``IOError`` is
        raised by default, unless the Traceback can be parsed. If an
        ``OSError`` is recognized it or one of the subclasses
        (``FileNotFoundError``, ``PermissionError``,  ``FileExistsError``),
        then that one will be raised instead.
        """
        return self.protocol.exec(*args, **kwargs)

    def evaluate(self, string):
        """
        :param str code: code to execute
        :returns: Python object

        Execute the string (just like :meth:`eval`) and return the output
        parsed using ``ast.literal_eval`` so that numbers, strings, lists etc.
        can be handled as Python objects.
        """
        return ast.literal_eval(self.exec(string))

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def soft_reset(self, run_main=True):
        """
        :param bool run_main: select if program should be started

        Execute a soft reset of the target. if ``run_main`` is False, then
        the REPL connection will be maintained and ``main.py`` will not be
        executed. Otherwise a regular soft reset is made and ``main.py``
        is executed.
        """
        if run_main:
            # exit raw REPL for a reset that runs main.py
            self.protocol.transport.write(b'\x03\x03\x02\x04\x01')
        else:
            # if raw REPL is active, then MicroPython will not execute main.py
            self.protocol.transport.write(b'\x03\x03\x04')
            # execute empty line to get a new prompt and consume all the outputs form the soft reset
            self.exec(' ')
        # XXX read startup message

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def statvfs(self, path):
        """
        :param str path: Absolute path on target.
        :rtype: os.statvfs_result

        Return statvfs information (disk size, free space etc.) about remote
        filesystem.
        """
        st = self.evaluate(f'import os; print(os.statvfs({str(path)!r}))')
        return os.statvfs_result(st)
        #~ f_bsize, f_frsize, f_blocks, f_bfree, f_bavail, f_files, f_ffree, f_favail, f_flag, f_namemax

    def truncate(self, path, length):
        # MicroPython 1.9.3 has no file.truncate(), but open(...,"ab"); write(b"") seems to work.
        return self.evaluate(
            f'_f = open({str(path)!r}, "ab")\n'
            f'print(_f.seek({int(length)}))\n'
            '_f.write(b"")\n'
            '_f.close(); del _f')

    def read_rtc(self):
        """Read RTC and return a datetime object"""
        year, month, day, weekday, hour, minute, second, subsecond = self.evaluate('import pyb; print(pyb.RTC().datetime())')
        # subseconds are 1/256th of a second counting down
        return datetime.datetime(year, month, day, hour, minute, second, (999999 * (255 - subsecond)) // 256)

    def set_rtc(self, board_time=None):
        """Set the targets RTC from given datetime object"""
        if board_time is None: 
            board_time = datetime.datetime.now()
        self.exec('import pyb; print(pyb.RTC().datetime(({0:%Y},{0:%m},{0:%d},{1},{0:%H},{0:%M},{0:%S},{2})))'.format(
            board_time,
            board_time.weekday() + 1,
            255 - (255 * board_time.microsecond) // 999999
        ))

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def read_flash_as_stream(self, offset, length):
        """
        :returns: Iterator
        :rtype: Iterator of bytes

        Iterate over blocks (`bytes`) of Flash memory.
        """
        self.exec(
            'import ubinascii, pyb;\n'
            'def _b():\n'
            f'  f = pyb.Flash(start={offset!r}, len={length!r})\n'
            '  f.ioctl(1, 1)\n'  # switch to new BDEV API
            '  blk = f.ioctl(5, 0)\n'  # get block size
            '  mem = memoryview(bytearray(blk))\n'
            f'  n_blocks = ({length!r} // blk) if {length!r} > 0 else f.ioctl(4, 0)\n'
            f'  for n in range(0, n_blocks):\n'
            '    f.readblocks(n, mem, 0)\n'
            '    print(ubinascii.b2a_base64(mem))\n'
            '    yield\n'
            '  print(b"")\n'
            '  yield\n'
            '_b = _b()\n')
        while True:
            block = self.evaluate('next(_b)')
            if not block:
                break
            yield binascii.a2b_base64(block)
        self.exec('del _b')


def _override_stat(st):
    """
    Override stat object with some fake attributes, uid/gui of the current
    user, mode flags.
    """
    # XXX fake some attributes: rw, uid/gid
    st = list(st)
    st[stat.ST_MODE] |= 0o660
    try:
        st[stat.ST_GID] = os.getgid()
        st[stat.ST_UID] = os.getuid()
    except AttributeError:
        pass  # Windows
    return st


class MpyPath(pathlib.PurePosixPath):  # pathlib.PosixPath
    """
    The path object represents a file or directory (existing or not) on the
    target board. To actually modify the target, `connect_repl()` must be
    called first (many functions will do this automatically).
    """
    __slots__ = ('_repl', '_stat_cache')

    def connect_repl(self, repl):
        """Connect object to remote connection."""
        self._repl = repl
        return self  # allow method joining

    def _with_stat(self, st):
        self._stat_cache = os.stat_result(st)
        return self

    # methods to override to connect to repl

    def with_name(self, name):
        return super().with_name(name).connect_repl(self._repl)

    def with_suffix(self, suffix):
        return super().with_suffix(suffix).connect_repl(self._repl)

    def relative_to(self, *other):
        return super().relative_to(*other).connect_repl(self._repl)

    def joinpath(self, *args):
        return super().joinpath(*args).connect_repl(self._repl)

    def __truediv__(self, key):
        return super().__truediv__(key).connect_repl(self._repl)

    def __rtruediv__(self, key):
        return super().__rtruediv__(key).connect_repl(self._repl)

    @property
    def parent(self):
        return super().parent.connect_repl(self._repl)

    # methods that access files

    def stat(self, fake_attrs=False) -> os.stat_result:
        """
        :param bool fake_attrs: When true, use dummy user and group info.
        :returns: stat information about path on remote
        :rtype: os.stat_result
        :raises FileNotFoundError:

        Return stat information about path on remote. The information is cached
        to speed up operations.

        If ``fake_attrs`` is true, UID, GID and R/W flags are overridden. This
        is used for the mount feature.
        """
        if getattr(self, '_stat_cache', None) is None:
            st = self._repl.evaluate(f'import os; print(os.stat({self.as_posix()!r}))')
            if fake_attrs:
                st = _override_stat(st)
            self._stat_cache = os.stat_result(st)
        return self._stat_cache

    def exists(self):
        """Return True if target exists"""
        try:
            self.stat()
        except FileNotFoundError:
            return False
        else:
            return True

    def is_dir(self):
        """Return True if target exists and is a directory"""
        try:
            return (self.stat().st_mode & stat.S_IFDIR) != 0
        except FileNotFoundError:
            return False

    def is_file(self):
        """Return True if target exists and is a regular file"""
        try:
            return (self.stat().st_mode & stat.S_IFREG) != 0
        except FileNotFoundError:
            return False

    def unlink(self):
        """
        :raises FileNotFoundError:

        Delete file. See also :meth:`rmdir`.
        """
        self._stat_cache = None
        self._repl.evaluate(f'import os; print(os.remove({self.as_posix()!r}))')

    def rename(self, path_to):
        """
        :param path_to: new name
        :return: new path object
        :raises FileNotFoundError: Source is not found
        :raises FileExistsError: Target already exits

        Rename file or directory. Source and target path need to be on the same
        filesystem.
        """
        self._stat_cache = None
        if isinstance(path_to, pathlib.PurePath):
            if self.parent != path_to.parent:
                raise NotImplementedError('currently only rename within the same directory is supported')
        self._repl.evaluate(f'import os; print(os.rename({self.as_posix()!r}, {path_to.as_posix()!r}))')
        return self.with_name(path_to.name)  # XXX, moves across dirs

    def mkdir(self, parents=False, exist_ok=False):
        """
        :param parents: When true, create parent directories
        :param exist_ok: No error if the directory does not exist
        :raises FileNotFoundError:

        Create new directory.
        """
        try:
            return self._repl.evaluate(f'import os; print(os.mkdir({self.as_posix()!r}))')
        except FileExistsError as e:
            if exist_ok:
                pass
            else:
                raise

    def rmdir(self):
        """
        :raises FileNotFoundError:

        Remove (empty) directory
        """
        self._repl.evaluate(f'import os; print(os.rmdir({self.as_posix()!r}))')
        self._stat_cache = None

    def read_as_stream(self):
        """
        :returns: Iterator
        :rtype: Iterator of bytes

        Iterate over blocks (`bytes`) of a remote file.
        """
        # reading (lines * linesize) must not take more than 1sec and 2kB target RAM!
        n_blocks = max(1, self._repl.serial.baudrate // 5120)
        self._repl.exec(
            f'import ubinascii; _f = open({self.as_posix()!r}, "rb"); _mem = memoryview(bytearray(512))\n'
            'def _b(blocks=8):\n'
            '  print("[")\n'
            '  for _ in range(blocks):\n'
            '    n = _f.readinto(_mem)\n'
            '    if not n: break\n'
            '    print(ubinascii.b2a_base64(_mem[:n]), ",")\n'
            '  print("]")')
        while True:
            blocks = self._repl.evaluate(f'_b({n_blocks})')
            if not blocks:
                break
            yield from [binascii.a2b_base64(block) for block in blocks]
        self._repl.exec('_f.close(); del _f, _b')

    def read_bytes(self) -> bytes:
        """
        :returns: file contents
        :rtype: bytes

        Return the contents of a remote file as byte string.
        """
        return b''.join(self.read_as_stream())

    def write_bytes(self, data) -> int:
        """
        :param bytes contents: Data

        Write contents (expected to be bytes) to a file on the target.
        """
        self._stat_cache = None
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(f'contents must be bytes/bytearray, got {type(data)} instead')
        self._repl.exec(f'from ubinascii import a2b_base64 as a2b; _f = open({self.as_posix()!r}, "wb")')
        # write in chunks
        with io.BytesIO(data) as local_file:
            while True:
                block = local_file.read(512)
                if not block:
                    break
                self._repl.exec(f'_f.write(a2b({binascii.b2a_base64(block).rstrip()!r}))')
        self._repl.exec('_f.close(); del _f, a2b')
        return len(data)

    # read_text(), write_text()

    def iterdir(self):
        """
        :param bool fake_attrs: override uid and gid in stat
        :return: generator over items in directory (MpyPath objects)

        Return iterator over items in given remote path.

        If ``fake_attrs`` is true, UID, GID and R/W flags are overridden. This
        is used for the mount feature.
        """
        if not self.is_absolute():
            raise ValueError(f'only absolute paths are supported (beginning with "/"): {self!r}')
        # simple version
        # remote_paths = self._repl.evaluate(f'import os; print(os.listdir({self.as_posix()!r}))')
        # return [(self / p).connect_repl(self._repl) for p in remote_paths]
        # variant with pre-loading stat info
        posix_path_slash = self.as_posix()
        if not posix_path_slash.endswith('/'):
            posix_path_slash += '/'
        remote_paths_stat = self._repl.evaluate(
            'import os; print("[")\n'
            f'for n in os.listdir({self.as_posix()!r}): print("[", repr(n), ",", os.stat({posix_path_slash!r} + n), "],")\n'
            'print("]")')
        return [(self / p)._with_stat(st) for p, st in remote_paths_stat]

    def glob(self, pattern: str):
        """
        :param str pattern: string with optional wildcards.
        :return: generator over matches (MpyPath objects)

        Pattern match files on remote.
        """
        if pattern.startswith('/'):
            pattern = pattern[1:]   # XXX
        parts = pattern.split('/')
        # print('glob', self, pattern, parts)
        if not parts:
            return
        elif len(parts) == 1:
            yield from (p for p in self.iterdir() if p.match(pattern))
        else:
            remaining_parts = '/'.join(parts[1:])
            if parts[0] == '**':
                for dirpath, dirnames, filenames in walk(self):
                    for path in filenames:
                        if path.match(remaining_parts):
                            yield path
            else:
                for path in self.iterdir():
                    if path.is_dir() and path.relative_to(path.parent).match(parts[0]):  # XXX ?
                        yield from path.glob(remaining_parts)

    # custom extension methods

    def sha256(self):
        """
        :returns: hash over file contents
        :rtype: bytes

        Calculate a SHA256 over the file contents and return the digest.
        """
        try:
            self._repl.exec(
                'import uhashlib; _h = uhashlib.sha256(); _mem = memoryview(bytearray(512))\n'
                f'with open({self.as_posix()!r}, "rb") as _f:\n'
                '  while True:\n'
                '    n = _f.readinto(_mem)\n'
                '    if not n: break\n'
                '    _h.update(_mem[:n])\n'
                'del n, _f, _mem\n')
        except ImportError:
            # fallback if no hashlib is available, upload and hash here. silly...
            try:
                _h = hashlib.sha256()
                for block in self.read_as_stream():
                    _h.update(block)
                return _h.digest()
            except FileNotFoundError:
                return b''
        except OSError:
            hash_value = b''
        else:
            hash_value = self._repl.evaluate('print(_h.digest()); del _h')
        return hash_value
