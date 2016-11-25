===========
 Technical
===========

REPL connection
===============
``repl_connection.py`` implements a Protocol for pySerial so that statements
can be executed on a remote Python prompt (REPL). Micropython has a special
"machine mode" where it does not echo input and clearly marks the output and
error response, so that it is easy to parse with a machine.

The class :class:`MicroPythonRepl` provides two functions for remote code
execution:

- :meth:`exec` executes the string and returns the output as string
- :meth:`evaluate` executes the string and returns the output parsed using
  ``ast.literal_eval`` so that numbers, strings, lists etc can be handled
  as Python objects.

The executed code typicaly uses ``print()`` to construct the answer, e.g.
``print(repr(obj))``.

:class:`MicroPythonRepl` has additional helper methods to list, read
and write files.


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

.. _pySerial: http://pypi.python.org/pypi/pyserial
.. _colorama: http://pypi.python.org/pypi/colorama

.. note::

    ``colorama`` does currently not support (or recognize, when split accross
    multiple writes) all escape sequences sent by micropython, so some quirks
    may be visible under Windows.

.. note::

    An alternative to ``colorama`` is to get ``ansy.sys`` working.
