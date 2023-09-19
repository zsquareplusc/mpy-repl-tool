#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2021 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""
File and directory sync functionality.

This functionality works locally with pathlib.Path or remotely with MpyPath
(must be connected to target).
"""
import hashlib
from pathlib import Path
from typing import Union
from .repl_connection import MpyPath
from .speaking import UserMessages
from .walk import walk


EXCLUDE_DIRS = [
    '__pycache__',
    '.git',
]


class Sync:
    """
    Helper for file and directory sync from and to remote.

    Because paths on the target and locally are both Path/MpyPath objects, 
    the sync is working in both directions with the same function.
    It would even support syncing local-local or remote-remote.
    """

    def __init__(self, user: UserMessages, dry_run=False, force=False, no_uhashlib=False):
        self.user = user
        self.dry_run = dry_run
        self.force = force
        self.use_uhashlib = not no_uhashlib

    def _hash_path(self, path):
        """Return a sha256 hash over the contents of a file"""
        if isinstance(path, MpyPath):
            return path.sha256()
        else:
            _h = hashlib.sha256()
            with path.open('rb') as f:
                while True:
                    block = f.read(512)
                    if not block:
                        break
                    _h.update(block)
            return _h.digest()

    def _files_are_different(self, source_path: Union[Path, MpyPath], destination_path: Union[Path, MpyPath]):
        try:
            if source_path.stat().st_size != destination_path.stat().st_size:
                return True
        except FileNotFoundError:
            return True
        if self.use_uhashlib and self._hash_path(source_path) != self._hash_path(destination_path):
            return True
        return False

    def sync_file(self, source_path: Union[Path, MpyPath], destination_path: Union[Path, MpyPath]):
        """\
        Copy a file from or to the target, if it is not already up to date. check with
        hash if copy is needed.

        If remote_path is a directory, the name from the source file is used.
        """
        if not self.dry_run:
            # support target being a directory (or a file)
            if destination_path.is_dir():
                destination_path = destination_path / source_path.name
            if self.force or self._files_are_different(source_path, destination_path):
                self.user.file_counter.add_file()
                self.user.notice(f'{source_path!s} -> {destination_path!s}\n')
                destination_path.write_bytes(source_path.read_bytes())
            else:
                self.user.file_counter.skip_file()
                self.user.info(f'{destination_path!s}: already up to date\n')
        else:
            self.user.file_counter.skip_file()
            self.user.notice(f'dry run: {source_path!s} -> {destination_path!s}\n')


    def sync_directory(self, source_path: Union[Path, MpyPath], destination_path: Union[Path, MpyPath], recursive=True):
        """\
        Copy a directory from source to destination. Can be local or remote.
        """
        if not self.dry_run:
            if not destination_path.is_dir():
                raise ValueError(f'destination must be a directory: {destination_path!s}')
            if not destination_path.exists():
                raise ValueError(f'destination directory must exist: {destination_path!s}')
            if not source_path.is_dir():
                raise ValueError(f'source must be a directory: {source_path!s}')
        if recursive:
            for source_dirpath, dirpaths, filepaths in walk(source_path):
                destination_dirpath = destination_path / source_dirpath.relative_to(source_path.parent)
                if not self.dry_run:
                    destination_dirpath.mkdir(parents=True, exist_ok=True)
                for path in list(dirpaths):  # iterate copy as we modify
                    if path.name in EXCLUDE_DIRS:
                        dirpaths.remove(path)
                for path in filepaths:
                    self.sync_file(path, destination_dirpath)
                # XXX support removing files and dirs from destination that are not in source
        else:
            destination_dirpath = destination_path / source_path.name
            for path in source_path.iterdir():
                if path.is_file():
                    self.sync_file(path, destination_dirpath)
                # else:
                #     user.notice(f'skiping directory: {path!s}\n')

    def remove_file(self, path: Union[Path, MpyPath]):
        """Delete single file"""
        self.user.info(f'rm {path!s}\n')
        if not self.dry_run:
            self.user.file_counter.add_file()
            path.unlink()
        else:
            self.user.file_counter.skip_file()

    def remove_directory(self, path: Union[Path, MpyPath], recursive=False):
        """
        Delete directory. Must be empty if recursive is false. If recursive is
        true, it will erase all files and sub directories.
        """
        self.user.info(f'rmdir {path!s}\n')
        if recursive:
            for dirpath, dirpaths, filepaths in walk(path, topdown=False):
                for current_path in filepaths:
                    self.remove_file(current_path)
                self.remove_directory(dirpath, recursive=False)
        else:
            if not self.dry_run:
                path.rmdir()
