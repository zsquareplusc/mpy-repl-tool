#!/usr/bin/env python3
# encoding: utf-8
#
# (C) 2012-2021 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""\
Functions to make things human readable.
"""
import stat
from math import log10

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

EXPONENTS = ('', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y')


def nice_bytes(value):
    """\
    Return a string for a number representing bytes in a human readable form
    (1kB=1000B as usual for storage devices nowdays).

    >>> nice_bytes(1024)
    '1.024 kB'
    >>> nice_bytes(21e9)
    '21.00 GB'
    >>> nice_bytes(123e12)
    '123.0 TB'
    >>> nice_bytes(48)
    '48 B'
    """
    if value < 0:
        raise ValueError(f'Byte count can not be negative: {value}')
    elif value == 0:
        exp = 0
        precision = 0
    else:
        exp = min(int(log10(value) // 3), len(EXPONENTS))
        value /= 10**(3 *exp)
        precision = max(1, min(3, 3 - int(log10(value))))
    return f'{value:.{precision}f} {EXPONENTS[exp]}B'


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def mode_to_chars(mode):
    """\
    'ls' like mode as character sequence.

    >>> mode_to_chars(0o700 | 32768)
    '-rwx------'
    >>> mode_to_chars(0o070 | 32768)
    '----rwx---'
    >>> mode_to_chars(0o007 | 32768)
    '-------rwx'
    """
    if mode is None:
        return '----------'
    flags = []
    # file type
    if stat.S_ISDIR(mode):
        flags.append('d')
    elif stat.S_ISCHR(mode):
        flags.append('c')
    elif stat.S_ISBLK(mode):
        flags.append('b')
    elif stat.S_ISREG(mode):
        flags.append('-')
    elif stat.S_ISFIFO(mode):
        flags.append('p')
    elif stat.S_ISLNK(mode):
        flags.append('l')
    elif stat.S_ISSOCK(mode):
        flags.append('s')
    else:
        flags.append('?')
    # user permissions
    flags.append('r' if (mode & stat.S_IRUSR) else '-')
    flags.append('w' if (mode & stat.S_IWUSR) else '-')
    if mode & stat.S_ISUID:
        flags.append('s' if (mode & stat.S_IXUSR) else 'S')
    else:
        flags.append('x' if (mode & stat.S_IXUSR) else '-')
    # group permissions
    flags.append('r' if (mode & stat.S_IRGRP) else '-')
    flags.append('w' if (mode & stat.S_IWGRP) else '-')
    if mode & stat.S_ISGID:
        flags.append('s' if (mode & stat.S_IXGRP) else 'S')
    else:
        flags.append('x' if (mode & stat.S_IXGRP) else '-')
    # others permissions
    flags.append('r' if (mode & stat.S_IROTH) else '-')
    flags.append('w' if (mode & stat.S_IWOTH) else '-')
    if mode & stat.S_ISGID:
        flags.append('s' if (mode & stat.S_IXGRP) else 'S')
    elif mode & stat.S_ISVTX:
        flags.append('T' if (mode & stat.S_IXOTH) else 't')
    else:
        flags.append('x' if (mode & stat.S_IXOTH) else '-')
    # XXX alternate access character omitted

    return ''.join(flags)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    import doctest
    doctest.testmod()
