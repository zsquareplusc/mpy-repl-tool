#!/usr/bin/env python3
# encoding: utf-8
#
# (C) 2016 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""\
Link To The Past - a backup tool

Handle backslashes in strings.
"""
import re

ESCAPE_CONTROLS = dict((k, repr(chr(k))[1:-1]) for k in range(32))
ESCAPE_CONTROLS[0] = r'\0'
ESCAPE_CONTROLS[7] = r'\a'
ESCAPE_CONTROLS[8] = r'\b'
ESCAPE_CONTROLS[11] = r'\v'
ESCAPE_CONTROLS[12] = r'\f'
ESCAPE_CONTROLS[32] = r'\ '
ESCAPE_CONTROLS[35] = r'\x23'  # escape comment char #
ESCAPE_CONTROLS[ord('\\')] = '\\\\'


def escaped(text):
    """\
    Escape control, non printable characters and the space.

    >>> escaped(' ')
    '\\\\ '
    >>> escaped('\\n')
    '\\\\n'
    >>> escaped('\u2000')
    '\\u2000'
    """
    return text.translate(ESCAPE_CONTROLS)


re_unescape = re.compile('\\\\(\\\\|[0-7]{1,3}|x.[0-9a-f]?|[\'"abfnrt0]|.|$)')


def _replace(m):
    b = m.group(1)
    if len(b) == 0:
        raise ValueError("Invalid character escape: '\\'.")
    i = b[0]
    if i == 'x':
        v = chr(int(b[1:], 16))
    elif '0' <= i <= '9':
        v = chr(int(b, 8))
    elif i == '"':
        return '"'
    elif i == "'":
        return "'"
    elif i == '\\':
        return '\\'
    elif i == 'a':
        return '\a'
    elif i == 'b':
        return '\b'
    elif i == 'f':
        return '\f'
    elif i == 'n':
        return '\n'
    elif i == 'r':
        return '\r'
    elif i == 't':
        return '\t'
    elif i == '0':
        return '\0'
    else:
        raise UnicodeDecodeError(
            'unescape', m.group(0), m.start(), m.end(), "Invalid escape: {!r}".format(b)
        )
    return v


def unescape(text):
    """\
    Remove escape sequences from a string.

    >>> unescape('\\x41\\t\\u0042')
    'A\\tB'
    """
    return re_unescape.sub(_replace, text)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    import doctest
    doctest.testmod()
