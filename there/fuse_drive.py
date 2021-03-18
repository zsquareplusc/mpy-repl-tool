#!/usr/bin/env python

import os
import errno
import stat
import time
import posixpath

from fuse import FUSE, FuseOSError, Operations


class FileBuffer(object):
    def __init__(self, path, contents=b''):
        self.path = path
        self.buffer = bytearray(contents)
        self.modified = False


class Cache(object):
    def __init__(self, max_age=10):
        self._max_age = max_age
        self._entries = {}

    def __setitem__(self, key, item):
        self._entries[key] = item, time.time()

    def __getitem__(self, key):
        value, timestamp = self._entries[key]  # may raise KeyError, that's OK
        if timestamp + self._max_age < time.time():
            # too old, discard
            raise KeyError('entry {} too old'.format(key))
        return value

    def __delitem__(self, key):
        del self._entries[key]

    def forget(self, key):
        """Remove key, no error if not present"""
        try:
            del self._entries[key]
        except KeyError:
            pass


class ReplFileTransfer(Operations):
    def __init__(self, remote_path, verbose):
        self.remote_path = remote_path
        self.verbose = verbose
        self.files = {}
        self.handle_counter = 0
        self._max_age = 10  # seconds
        self._stat_cache = Cache(self._max_age)
        self._listdir_cache = Cache(self._max_age)
        # XXX currently there is no cleanup of old entries in those caches

    def _remote(self, path):
        return self.remote_path / path[1:]

    # file system methods

    def _stat(self, path):
        try:
            st = self._stat_cache[path]
        except KeyError:
            try:
                st = self._remote(path).stat(fake_attrs=True)
            except (IOError, FileNotFoundError):
                raise FuseOSError(errno.ENOENT)
            else:
                self._stat_cache[path] = st
        return st

    def getattr(self, path, fh=None):
        if fh is not None:
            path = self.files[fh].path
        st = self._stat(path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                    'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    def readdir(self, path, fh):
        try:
            dirents = self._listdir_cache[path]
        except KeyError:
            dirents = ['.', '..']
            if (self._stat(path).st_mode & stat.S_IFDIR) != 0:
                for remote_path in self._remote(path).iterdir():
                    dirents.append(remote_path.name)
                    self._stat_cache[posixpath.join(path, remote_path.name)] = remote_path.stat()
            self._listdir_cache[path] = dirents
        for r in dirents:
            yield r

    def rmdir(self, path):
        self._stat_cache.forget(path)
        self._listdir_cache.forget(path)
        return self._remote(path).rmdir()

    def mkdir(self, path, mode):
        return self._remote(path).mkdir()

    def statfs(self, path):
        stv = self.remote_path._repl.statvfs(path)
        return dict((key, getattr(stv, key)) for key in (
            'f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))

    def unlink(self, path):
        self._stat_cache.forget(path)
        self._listdir_cache.forget(os.path.dirname(path))
        return self._remote(path).unlink()

    def rename(self, old, new):
        self._stat_cache.forget(old)
        self._listdir_cache.forget(os.path.dirname(old))
        try:
            return self._remote(old).rename(new)
        except FileExistsError:
            self._remote(new).unlink()
            return self._remote(old).rename(new)

    # file methods

    def open(self, path, flags):
        fileno = self.handle_counter
        self.handle_counter += 1
        self.files[fileno] = FileBuffer(path, self._remote(path).read_bytes())
        return fileno

    def create(self, path, mode, fi=None):
        fileno = self.handle_counter
        self.handle_counter += 1
        self.files[fileno] = f = FileBuffer(path)
        # XXX inefficient to write it here, could delay. but need to answer stat calls
        self._remote(path).write_bytes(f.buffer)
        return fileno

    def read(self, path, length, offset, fh):
        return bytes(self.files[fh].buffer[offset:offset + length])

    def write(self, path, buf, offset, fh):
        length = len(buf)
        self.files[fh].modified = True
        self.files[fh].buffer[offset:offset + length] = buf
        return length

    def truncate(self, path, length, fh=None):
        if fh is not None:
            self.files[fh].modified = True
            del self.files[fh].buffer[length:]
            self._stat_cache.forget(self.files[fh].path)
        else:
            self.remote_path.truncate(self._remote(path), length)  # XXX
            self._stat_cache.forget(path)

    def flush(self, path, fh):
        f = self.files[fh]
        if f.modified:
            self._remote(path).write_bytes(f.buffer)

    def release(self, path, fh):
        del self.files[fh]

    def fsync(self, path, fdatasync, fh):
        for f in self.files.values():
            if f.modified:
                self._remote(path).write_bytes(f.buffer)
                f.modified = False


def mount(remote_path, mountpoint, verbosity):
    FUSE(ReplFileTransfer(remote_path, verbose=verbosity), mountpoint, nothreads=True, foreground=True, debug=verbosity > 0)
