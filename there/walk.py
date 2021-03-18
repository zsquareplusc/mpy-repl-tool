#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2021 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""
Recursive directory walk function that works with Paths from pathlib and
MpyPath objects.
"""

def walk(dirpath, topdown=True):
    """
    :param str dirpath:Path to start search.
    :param bool topdown: Reverse order.
    :return: iterator over tuples ``(root, dirs, files)`` where ``dirs``
                and ``files`` are lists of Path/MpyPath objects

    Recursively scan local or remote path and yield tuples of (path, dirs, files).
    Where dirs and files are lists of Path/MpyPath objects.

    This function works locally with pathlib.Path as dirpath or remotely with
    MpyPath as dirpath (must be connected to target).

    If ``topdown`` is true then the top directory is yielded as first item,
    if it is false, then the sub-directories are yielded first.

    If ``topdown`` is true, it is allowed to remove items from the ``dirs``
    list, so that they are not searched.
    """
    dirnames = []
    filenames = []
    for path in dirpath.iterdir():
        if path.is_dir():
            dirnames.append(path)
        else:
            filenames.append(path)
    if topdown:
        yield dirpath, dirnames, filenames
        for dirname in dirnames:
            yield from walk(dirname)
    else:
        for dirname in dirnames:
            yield from walk(dirname, topdown=False)
        yield dirpath, dirnames, filenames
