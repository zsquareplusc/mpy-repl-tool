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
import shlex
from ipykernel.kernelbase import Kernel
from . import repl_connection


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

    def handle_meta_command(self, commandline):
        args = shlex.split(commandline)
        command = args.pop(0)
        getattr(self, 'meta_{}'.format(command[1:]))(*args)

    def meta_info(self):
        self.write('mpy-repl-tool: connected to {}'.format(self.repl.serial))

    def meta_connect(self, port='hwgrep://USB', baudrate='115200'):
        baudrate = int(baudrate)
        if self.repl is not None:
            self.repl.close()
            self.repl = None
        self.repl = repl_connection.MicroPythonRepl(port, baudrate)
        self.repl.protocol.verbose = True
        self.write('mpy-repl-tool: connected to {}'.format(self.repl.serial))

    def meta_timeout(self, args=None):
        if args:
            self.timeout = float(args[0])
            self.write('mpy-repl-tool: timeout set to {} seconds'.format(self.timeout))
        else:
            self.write('mpy-repl-tool: timeout is {} seconds'.format(self.timeout))

    def meta_reset(self):
        self.write('mpy-repl-tool: soft-reset board')
        self.repl.soft_reset()

    #~ def meta_listdir(self, path):
        #~ self.write('mpy-repl-tool: listdir {}:\n{}'.format(path, self.repl.listdir(path)))


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
                'Please use %connect [port] [baudrate] first.\n'
                'Defaults are first USB device and 115200 baud.',
                stream='stderr')
            status['status'] = 'error'
            return status
        # Run the specified code on the connected MicroPython board.
        try:
            response = self.repl.exec(code, timeout=self.timeout)
        except IOError as e:
            status['status'] = 'error'
            response = str(e)
            if not silent:
                self.send_response(
                    self.iopub_socket,
                    'stream',
                    {'name': 'stderr', 'text': response})
        else:
            status['status'] = 'ok'
            if not silent:
                self.send_response(
                    self.iopub_socket,
                    'stream',
                    {'name': 'stdout', 'text': response})
        return status

    def do_shutdown(self, restart):
        try:
            self.repl.close()
        except:
            pass


if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=MicroPythonKernel)
