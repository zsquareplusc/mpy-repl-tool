#!/usr/bin/env python

import os
import sys
import errno

from fuse import FUSE, FuseOSError, Operations

class FileBuffer(object):
    def __init__(self, path, contents=b''):
        self.path = path
        self.buffer = bytearray(contents)
        self.modified = False

S_IFDIR = 0x4000
S_IFREG = 0x8000

class ReplFileTransfer(Operations):
    def __init__(self, file_interface):
        self.file_interface = file_interface
        self.files = {}
        self.handle_counter = 0

    # file system methods

    def access(self, path, mode):
        return
        #~ st = self.file_interface.stat(path)
        #~ if not os.access(full_path, mode):
            #~ raise FuseOSError(errno.EACCES)

    def chmod(self, path, mode):
        raise FuseOSError(errno.EPERM)
        #~ return os.chmod(full_path, mode)

    def chown(self, path, uid, gid):
        raise FuseOSError(errno.EPERM)
        #~ return os.chown(full_path, uid, gid)

    def getattr(self, path, fh=None):
        try:
            st = self.file_interface.stat(path)
        except IOError as e:
            raise FuseOSError(errno.ENOENT)
        else:
            return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                         'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    def readdir(self, path, fh):
        st = self.file_interface.ls(path)
        dirents = ['.', '..']
        if (self.file_interface.stat(path).st_mode & S_IFDIR) != 0:
            dirents.extend(self.file_interface.ls(path))
        for r in dirents:
            yield r

    def readlink(self, path):
        raise FuseOSError(errno.EPERM)
        #~ pathname = os.readlink(self._full_path(path))
        #~ if pathname.startswith("/"):
            #~ # Path name is absolute, sanitize it.
            #~ return os.path.relpath(pathname, self.root)
        #~ else:
            #~ return pathname

    def mknod(self, path, mode, dev):
        raise FuseOSError(errno.EPERM)

    def rmdir(self, path):
        return self.file_interface.rmdir(path)

    def mkdir(self, path, mode):
        return self.file_interface.mkdir(path)

    def statfs(self, path):
        stv = self.file_interface.statvfs(path)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))

    def unlink(self, path):
        return self.file_interface.remove(path)

    def symlink(self, name, target):
        raise FuseOSError(errno.EPERM)
        #~ return os.symlink(name, self._full_path(target))

    def rename(self, old, new):
        try:
            return self.file_interface.rename(old, new)
        except IOError as e:
            if 'EEXIST' in str(e):
                self.file_interface.remove(new)
                return self.file_interface.rename(old, new)


    def link(self, target, name):
        raise FuseOSError(errno.EPERM)

    def utimens(self, path, times=None):
        raise FuseOSError(errno.EPERM)
        #~ return os.utime(self._full_path(path), times)

    # file methods

    def open(self, path, flags):
        fileno = self.handle_counter
        self.handle_counter += 1
        self.files[fileno] = FileBuffer(path, self.file_interface.read_file(path))
        return fileno

    def create(self, path, mode, fi=None):
        fileno = self.handle_counter
        self.handle_counter += 1
        self.files[fileno] = f = FileBuffer(path)
        # XXX inefficient to write it here, could delay. but need to answer stat calls
        self.file_interface.write_to_file(f.path, f.buffer)
        return fileno

    def read(self, path, length, offset, fh):
        return bytes(self.files[fh].buffer[offset:offset+length])

    def write(self, path, buf, offset, fh):
        length = len(buf)
        self.files[fh].modified = True
        self.files[fh].buffer[offset:offset+length] = buf
        return length

    def truncate(self, path, length, fh=None):
        if fh is not None:
            self.files[fh].modified = True
            del self.files[fh].buffer[length:]
        else:
            self.file_interface.truncate(f.path, length)


    def flush(self, path, fh):
        f = self.files[fh]
        if f.modified:
            self.file_interface.write_to_file(f.path, f.buffer)

    def release(self, path, fh):
        del self.files[fh]

    def fsync(self, path, fdatasync, fh):
        for f in self.files.values():
            if f.modified:
                self.file_interface.write_to_file(f.path, f.buffer)
                f.modified = False


def mount(file_interface, mountpoint):
    FUSE(ReplFileTransfer(file_interface), mountpoint, nothreads=True, foreground=True)

