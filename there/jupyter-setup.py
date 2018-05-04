#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2017 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""\
Install a json kernel specification into the users settings of Jupyter.

see also http://jupyter-client.readthedocs.io/en/latest/kernels.html#kernel-specs
"""

KERNEL_JSON = """\
{
 "argv": ["python3",
          "-m", "there.kernel",
          "-f", "{connection_file}"],
 "display_name": "MicroPython",
 "language": "micropython"
}
"""


def confirm(message):
    if input(message) not in ['y', 'yes']:
        raise Exception('user reponded "no"')


if __name__ == '__main__':
    import sys
    import os

    try:
        if sys.platform.startswith('win32'):
            path = r'%APPDATA%\jupyter\kernels'
        elif sys.platform.startswith('linux'):
            path = '~/.local/share/jupyter/kernels'
        elif sys.platform.startswith('darwin'):
            path = '~/Library/Jupyter/kernels'
        else:
            raise OSError('Dont know how to handle this on this platform')

        path = os.path.expanduser(os.path.expandvars(os.path.join(path, 'micropython-mpy-repl')))
        filename = os.path.join(path, 'kernel.json')

        if not os.path.exists(path):
            confirm('Create {}? [y/N] '.format(path))
            os.makedirs(path)

        if os.path.exists(filename):
            confirm('Overwrite {}? [y/N] '.format(filename))

        with open(filename, 'w') as f:
            f.write(KERNEL_JSON)
    except Exception as e:
        sys.stderr.write('ERROR: {}\n'.format(e))
        sys.exit(1)
