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

.. class:: MicroPythonRepl

    .. method:: exec(code)

        :param str code: code to execute
        :returns: all output as text
        :rtype: str

        Execute the string and returns the output as string. It may contain
        multiple lines.

    .. method:: evaluate(code)

        :param str code: code to execute
        :returns: Python object

        Execute the string and returns the output parsed using
        ``ast.literal_eval`` so that numbers, strings, lists etc. can be handled
        as Python objects.

        The executed code should use ``print()`` to construct the answer, e.g.
        ``print(repr(obj))``. It is also possible to use multiple print statements
        to construct the response, e.g. to create a list with many entries. As
        printed lines are transfered immediately and the PC caches the data, it
        is possible to create very large responses.

    :class:`MicroPythonRepl` has additional helper methods to list, read
    and write files.


    .. method:: statvfs(path)

        :param str path: Absolute path on target.
        :rtype: os.statvfs_result

        return stat information about remote filesystem

    .. method:: stat(path, fake_attrs=False)

        :param str path: Absolute path on target.
        :returns: stat information about path on remote
        :rtype: os.stat_result
        :raises FileNotFoundError:

    .. method:: remove(path)

        :param str path: Absolute path on target.
        :raises FileNotFoundError:

        Delete file.

    .. method:: rename(path, path_to)

        :param str path: Absolute path on target.
        :param str path_to: Absolute path on target.
        :raises FileNotFoundError: Source is not found
        :raises FileExistsError: Target already exits

        Rename file or directory.

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

        Return the contents of a remote file as byte string

    .. method:: write_file(local_filename, path)

        :param str local_filename: Path to local file
        :param str path: Absolute path on target.

        Copy a file from local to remote filesystem.

    .. method:: write_to_file(path, contents)

        :param str path: Absolute path on target.
        :param bytes contents: Data

        Write contents (expected to be bytes) to a file on the target.

    .. method:: ls(path, fake_attrs=False)

        :param str path: Absolute path on target.
        :param bool fake_attrs: override uid and gid in stat

        Return a list of tuples of filenames and stat info of given remote
        path.

    .. method:: walk(dirpath, topdown=True)

        :param str dirpath: Absolute path on target.

        Recursively scan remote path and yield tuples of (dirpath, dir_st, file_st).
        Where dir_st and file_st are lists of tuples of name and stat info.

    .. method:: glob(pattern)

        :param str pattern: Absolute path on target containing wildcards.

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

.. _pySerial: http://pypi.python.org/pypi/pyserial
.. _colorama: http://pypi.python.org/pypi/colorama

.. note::

    ``colorama`` does currently not support (or recognize, when split accross
    multiple writes) all escape sequences sent by micropython, so some quirks
    may be visible under Windows.

.. note::

    An alternative to ``colorama`` is to get ``ansy.sys`` working.
