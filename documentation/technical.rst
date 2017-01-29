===========
 Technical
===========

REPL connection
===============
``repl_connection.py`` implements a Protocol_ for pySerial_ so that statements
can be executed on a remote Python prompt (REPL). MicroPython_ has a special
"machine mode" where it does not echo input and clearly marks the output and
error response, so that it is easy to parse with a machine.

The class :class:`MicroPythonRepl` provides two functions for remote code
execution:


.. class:: MicroPythonRepl

    .. method:: exec(code)

        :param str code: code to execute
        :returns: all output as text
        :rtype: str
        :raises IOError: execution failed

        Execute the string and returns the output as string. It may contain
        multiple lines.

        The executed code should use ``print()`` to construct the answer, e.g.
        ``print(repr(obj))``. It is also possible to use multiple print statements
        to construct the response, e.g. to create a list with many entries. As
        printed lines are transfered immediately and the PC caches the data, it
        is possible to create very large responses.

        If the target raises an exception, this function will raise an
        exception too. The type depends on the exception. An ``IOError`` is
        rasied by default, unless the Traceback can be parsed. If an
        ``OSError`` is recognized it or one of the sublcasses
        (``FileNotFoundError``, ``PermissionError``,  ``FileExistsError``),
        then that one will be rised instead.


    .. method:: evaluate(code)

        :param str code: code to execute
        :returns: Python object

        Execute the string (just like :meth:`eval`) and return the output
        parsed using ``ast.literal_eval`` so that numbers, strings, lists etc.
        can be handled as Python objects.


    :class:`MicroPythonRepl` has additional helper methods to list, read
    and write files.


    .. method:: statvfs(path)

        :param str path: Absolute path on target.
        :rtype: os.statvfs_result

        Return statvfs information (disk size, free space etc.) about remote
        filesystem.

    .. method:: stat(path, fake_attrs=False)

        :param str path: Absolute path on target.
        :param bool fake_attrs: override uid and gid in stat
        :returns: stat information about path on remote
        :rtype: os.stat_result
        :raises FileNotFoundError:

        Return stat info for given path.

        If ``fake_attrs`` is true, UID, GID and R/W flags are overriden. This
        is used for the mount feature.

    .. method:: remove(path)

        :param str path: Absolute path on target.
        :raises FileNotFoundError:

        Delete one file. See also :meth:`rmdir`.

    .. method:: rename(source, target)

        :param str source: Absolute path on target.
        :param str target: Absolute path on target.
        :raises FileNotFoundError: Source is not found
        :raises FileExistsError: Target already exits

        Rename file or directory. Source and target path need to be on the same
        filesystem.

    .. method:: mkdir(path)

        :param str path: Absolute path on target.
        :raises FileNotFoundError:

        Create new directory.

    .. method:: rmdir( path)

        :param str path: Absolute path on target.
        :raises FileNotFoundError:

        Remove (empty) directory

    .. method:: read_file(path, local_filename)

        :param str path: Absolute path on target.
        :param str local_filename: Path to local file
        :raises FileNotFoundError:

        Copy a file from remote to local filesystem.

    .. method:: read_from_file(path)

        :param str path: Absolute path on target.
        :returns: file contents
        :rtype: bytes

        Return the contents of a remote file as byte string.

    .. method:: write_file(local_filename, path)

        :param str local_filename: Path to local file
        :param str path: Absolute path on target.

        Copy a file from local to remote filesystem.

    .. method:: write_to_file(path, contents)

        :param str path: Absolute path on target.
        :param bytes contents: Data

        Write contents (expected to be bytes) to a file on the target.

    .. method:: listdir(path, fake_attrs=False)

        :param str path: Absolute path on target.
        :param bool fake_attrs: override uid and gid in stat

        Return a list of tuples of filenames and stat info of given remote
        path.

        If ``fake_attrs`` is true, UID, GID and R/W flags are overriden. This
        is used for the mount feature.

    .. method:: walk(topdir, topdown=True)

        :param str topdir: Absolute path on target.
        :param bool topdown: Reverse order.
        :return: iterator over tuples ``(root, dirs, files)`` where ``dirs``
                 and ``files`` are lists of tuples containing
                 ``(name, stat_result)``

        Recursively scan remote path and yield all items that are found.

        If ``topdown`` is true then the top directory is yielded as first item,
        if it is false, then the sub-directories are yielded first.

        If ``topdown`` is true, it is allowed to remove items from the ``dirs``
        list, so that they are not searched.

    .. method:: glob(pattern)

        :param str pattern: Absolute path on target containing wildcards.
        :return: iterator over ``(name, stat_result)`` items that match the pattern

        :mod:`fnmatch` is used to evalute the pattern.


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

    An alternative to ``colorama`` is to get ``ansy.sys`` working.


.. _Protocol: https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.threaded.Protocol
.. _MicroPython: https://micropython.org/
.. _pySerial: http://pypi.python.org/pypi/pyserial
.. _colorama: http://pypi.python.org/pypi/colorama
