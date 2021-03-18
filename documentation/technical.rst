===========
 Technical
===========

REPL connection
===============
:mod:`there.repl_connection` implements a Protocol_ for pySerial_ so that statements
can be executed on a remote Python prompt (REPL). MicroPython_ has a special
"machine mode" where it does not echo input and clearly marks the output and
error response, so that it is easy to parse with a machine.

The class :class:`there.repl_connection.MicroPythonRepl` provides two functions
for remote code execution. :class:`MpyPath` is an :class:`pathlib.Path` like
object that performs operations on remote files.


.. autoclass:: there.repl_connection.MicroPythonRepl
    :members:
    :undoc-members:

.. autoclass:: there.repl_connection.MpyPath
    :members:
    :undoc-members:


Sync functionality
==================
The command line tool implements push and pull commands that sync files.
The underlying logic is available in the sync module.

.. autoclass:: there.sync.Sync
    :members:
    :undoc-members:


Mount Action
============
FUSE is a feature of the GNU/Linux kernel that allows to implement file system
in user space programs. There are compatible libraries for MacOS and even for
Windows.

``fuse_drive.py`` implements an class for ``fusepy``. It gets a connection which
it's using to execute commands on the target.

See also :ref:`mount_windows`, it currently requires a hack to get it working there.


Miniterm-MPY
============
This project uses a modified version of pySerial_'s miniterm. This version
handles the special keys on Windows and translates them to escape sequences. It
also uses the Python module colorama_ to get support for receiving some
escape sequences.


.. note::

    ``colorama`` does currently not support (or recognize, when split accross
    multiple writes) all escape sequences sent by MicroPython, so some quirks
    may be visible under Windows.

.. note::

    An alternative to ``colorama`` is to get ``ansi.sys`` working.


.. _Protocol: https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.threaded.Protocol
.. _MicroPython: https://micropython.org/
.. _pySerial: http://pypi.python.org/pypi/pyserial
.. _colorama: http://pypi.python.org/pypi/colorama
