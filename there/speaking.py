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
import sys
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
    >>> nice_bytes(999)
    '999 B'
    >>> nice_bytes(1000)
    '1.000 kB'
    >>> nice_bytes(48)
    '48 B'
    >>> nice_bytes(0)
    '0 B'
    """
    if value < 0:
        raise ValueError(f'Byte count can not be negative: {value}')
    elif 0 <= value < 1000:
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
class UserMessages:
    """
    Provide a class with methods to interact with user. Makes it simpler to
    track verbosity flag.
    """
    def __init__(self, verbosity: int) -> None:
        self.verbosity = verbosity
        self.file_counter = FileCounter(self)

    def output_binary(self, message: str) -> None:
        """output bytes, typically stdout"""
        sys.stdout.buffer.write(message)
        sys.stdout.buffer.flush()

    def output_text(self, message: str) -> None:
        """output text, typically stdout"""
        sys.stdout.write(message)
        sys.stdout.flush()

    def error(self, message: str) -> None:
        """error messages to stderr"""
        sys.stderr.write(message)
        sys.stderr.flush()

    def notice(self, message: str) -> None:
        """informative messages to stderr"""
        if self.verbosity > 0:
            sys.stderr.write(message)
            sys.stderr.flush()

    def info(self, message: str) -> None:
        """informative messages to stderr, only if verbose flag is set"""
        if self.verbosity > 1:
            sys.stderr.write(message)
            sys.stderr.flush()


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
class FileCounter:
    """Class to keep track of files processed, e.g. for push or pull operations"""

    def __init__(self, user: UserMessages):
        self.user = user
        self.files = 0
        self.skipped = 0

    def add_file(self):
        self.files += 1

    def skip_file(self):
        self.skipped += 1

    def print_summary(self, action_verb: str, skipped_verb='skipped'):
        message = [f'{self.files} files {action_verb}']
        if self.skipped:
            message.append(f'{self.skipped} {skipped_verb}')
        self.user.notice('{}\n'.format(', '.join(message)))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    import doctest
    doctest.testmod()
