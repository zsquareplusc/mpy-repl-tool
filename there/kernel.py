#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2017 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""\
Provide a kernel for IPython/Jupyter that executes micropython on an attached
microcontroller.

The board must be preprogrammed with a recent micropython firmware.

Features:
- transmits stdout and stderr
- configure the connection via "ipython magic" commands:
    - %connect [port [baudrate]]
    - %timeout [timeout]
    - %reset
    - %info
- "kernel->interrupt" works (while something is executed)

Original idea: Tony D! https://github.com/adafruit/jupyter_micropython_kernel
"""
import argparse
import shlex
import sys
import traceback
from ipykernel.kernelbase import Kernel
from . import repl_connection
from . import __main__ as commands
import serial.tools.list_ports


class MicroPythonKernel(Kernel):
    implementation = 'micropython'
    implementation_version = '0.1'
    language = 'micropython'
    language_version = '3.5'
    language_info = {
        'name': 'python',
        'mimetype': 'text/x-python',
        'file_extension': '.py',
    }
    banner = 'MicroPython Kernel'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.repl = None
        self.timeout = 30

    def write(self, message, stream='stdout'):
        self.send_response(
            self.iopub_socket,
            'stream',
            {'name': stream, 'text': message})

    def handle_meta_command(self, code):
        self.body = code.splitlines()
        commandline = self.body.pop(0)
        args = shlex.split(commandline)
        command = args.pop(0)
        try:
            streams = sys.stdout, sys.stderr
            sys.stdout = self
            sys.stderr = self
            try:
                getattr(self, 'meta_{}'.format(command[1:]))(*args)
            finally:
                sys.stdout, sys.stderr = streams
        except SystemExit as e:
            if e.code != 0:
                self.write('mpy-repl-tool: command exited: {}'.format(e), stream='stderr')
        except Exception as e:
            self.write('mpy-repl-tool: internal error', stream='stderr')
            traceback.print_exception(e, e, e.__traceback__, file=self)

    def meta_info(self):
        if self.repl is not None:
            self.write('mpy-repl-tool: connected to {0.port}: '
                       '{0.baudrate},{0.bytesize},{0.parity},{0.stopbits}\n'.format(self.repl.serial))
        else:
            self.write('mpy-repl-tool: is not connected')

    def meta_ports(self):
        for info in serial.tools.list_ports.comports():
            self.write('{}\n'.format(info))

    def meta_connect(self, port='hwgrep://USB', baudrate='115200'):
        baudrate = int(baudrate)
        if self.repl is not None:
            self.repl.close()
            self.repl = None
        self.repl = repl_connection.MicroPythonRepl(port, baudrate)
        #~ self.repl.protocol.verbose = True
        self.write('mpy-repl-tool: connected to {0.port}: '
                   '{0.baudrate},{0.bytesize},{0.parity},{0.stopbits}\n'.format(self.repl.serial))
        try:
            mpy_info = self.repl.exec('import sys; print(sys.implementation)').strip()
        except IOError:
            self.write('mpy-repl-tool: WARNING: version check failed! Is the port and baudrate correct?\n')
        else:
            self.write('mpy-repl-tool: implementation: {}\n'.format(mpy_info))

    def meta_disconnect(self):
        if self.repl is not None:
            self.repl.close()
            self.repl = None
        self.write('mpy-repl-tool: diconnected')

    def meta_timeout(self, args=None):
        if args:
            self.timeout = float(args[0])
            self.write('mpy-repl-tool: timeout set to {} seconds'.format(self.timeout))
        else:
            self.write('mpy-repl-tool: timeout is {} seconds'.format(self.timeout))

    def meta_reset(self):
        self.write('mpy-repl-tool: soft-reset board')
        self.repl.soft_reset()

    def meta_ls(self, *str_args):
        #~ self.write('mpy-repl-tool: listdir {}:\n{}'.format(path, self.repl.listdir(path)))
        parser = argparse.ArgumentParser(prog='%ls')
        parser.add_argument('PATH', nargs='*', default='/', help='paths to list')
        parser.add_argument('-l', '--long', action='store_true', help='show more info')
        parser.add_argument('-r', '--recursive', action='store_true', help='list contents of directories')
        #~ self.write('mpy-repl-tool: {}\n'.format(str_args))
        args = parser.parse_args(str_args)
        commands.command_ls(self, self.repl, args)

    def meta_pull(self, *str_args):
        parser = argparse.ArgumentParser(prog='%pull')
        parser.add_argument('REMOTE', nargs='+', help='one or more source files/directories')
        parser.add_argument('LOCAL', nargs=1, help='destination directory')
        parser.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
        parser.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
        args = parser.parse_args(str_args)
        commands.command_pull(self, self.repl, args)

    def meta_push(self, *str_args):
        parser = argparse.ArgumentParser(prog='%push')
        parser.add_argument('LOCAL', nargs='+', help='one or more source files/directories')
        parser.add_argument('REMOTE', nargs=1, help='destination directory')
        parser.add_argument('-r', '--recursive', action='store_true', help='copy recursively')
        parser.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
        args = parser.parse_args(str_args)
        commands.command_push(self, self.repl, args)

    def meta_cat(self, *str_args):
        parser = argparse.ArgumentParser(prog='%cat')
        parser.add_argument('PATH', help='filename on target')
        args = parser.parse_args(str_args)
        commands.command_cat(self, self.repl, args)

    def meta_write(self, *str_args):
        parser = argparse.ArgumentParser(prog='%write')
        parser.add_argument('PATH', help='filename on target')
        args = parser.parse_args(str_args)
        self.repl.write_to_file(args.PATH, '\n'.join(self.body).encode('utf-8'))

    def meta_rm(self, *str_args):
        parser = argparse.ArgumentParser(prog='%rm')
        parser.add_argument('PATH', nargs='+', help='filename on target')
        parser.add_argument('-f', '--force', action='store_true', help='delete anyway / no error if not existing')
        parser.add_argument('-r', '--recursive', action='store_true', help='remove directories recursively')
        parser.add_argument('--dry-run', action='store_true', help='do not actually create anything on target')
        args = parser.parse_args(str_args)
        commands.command_rm(self, self.repl, args)

    def meta_df(self, *str_args):
        parser = argparse.ArgumentParser(prog='%df')
        parser.add_argument('PATH', nargs='?', default='/', help='remote path')
        args = parser.parse_args(str_args)
        commands.command_df(self, self.repl, args)

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        status = {
            'execution_count': self.execution_count,
            'payload': [],
            'user_expressions': {}}
        if code.startswith('%'):  # handle magic commands
            try:
                self.handle_meta_command(code)
            except Exception as e:
                status['status'] = 'error'
                self.write(str(e))
            else:
                status['status'] = 'ok'
            return status
        if self.repl is None:
            self.write(
                'Please use "%connect [port[baudrate]]" first.\n'
                'Defaults are first USB-serial device and 115200 baud. '
                '"%ports" will list available serial ports.',
                stream='stderr')
            status['status'] = 'error'
            return status
        # Run the specified code on the connected MicroPython board.
        try:
            response = self.repl.exec(code, timeout=self.timeout)
            #~ response += self.repl.exec('if _ is not None: print(_)', timeout=3)
        except IOError as e:
            self.repl.interrupt()
            status['status'] = 'error'
            response = str(e)
            if not silent:
                self.write(response, stream='stderr')
        else:
            status['status'] = 'ok'
            if not silent:
                self.write(response)
        return status

    def do_shutdown(self, restart):
        try:
            self.repl.close()
        except:
            pass

    # -- interface UserMessages

    def output_binary(self, message):
        """output bytes, typically stdout"""
        self.write(message.decode('utf-8', 'replace'))   # XXX convert to hexdump or escape non printable characters??

    def output_text(self, message):
        """output text, typically stdout"""
        self.write(message)

    def error(self, message):
        """error messages to stderr"""
        self.write(message)

    def notice(self, message):
        """informative messages to stderr"""
        self.write(message)

    def info(self, message):
        """informative messages to stderr, only if verbose flag is set"""
        #~ if self.verbosity > 0:
            #~ self.write(message)

if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=MicroPythonKernel)
