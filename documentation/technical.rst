===========
 Technical
===========

REPL connection
===============
``repl_connection.py`` implements a Protocol for pySerial so that statements
can be executed on a remote Python prompt (REPL). Micropython has a special
"machine mode" where it does not echo input and clearly marks the output and
error response, so that it is easy to parse with a machine.

The class :class:`MicroPythonRepl` provides two function for remote code
execution:

- :meth:`exec` executes the string and returns the output as string
- :meth:`evaluate` executes the string and returns the output parsed using
  ``ast.literal_eval`` so that numbers, strings, lists etc can be handled
  as Python objects.

:class:`MicroPythonRepl` also has additional helper methods to list, read
and write files.


Mount Action
============
FUSE is a feature of the GNU/Linux kernel that allows to implement file system
in user space programs. There are compatible libraries for MacOS and even for
Windows.

``fuse_drive.py`` implements an class for ``fusepy``. It get a connection which
it's using to execute commands on the target.


Miniterm-MPY
============
This project contains a modified version of pySerial's miniterm. This version
handles the special keys on Windows and translates them to escape sequences. It
also uses the Python module ``colorama`` to get support for receiving some
escape sequences.

.. note::

    ``colorama`` does currently not support all escape sequences sent by
    micropython, so some quirks may be visible under Windows.

