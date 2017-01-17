=============
 Commandline
=============

Overview
========
usage: there [-h] [-p PORT] [-b BAUDRATE] [-c COMMAND] [-i] [-u USER]
             [-w PASSWORD] [-v] [--develop]
             {detect,run,ls,cat,pull,push,rm,mount} ...

Do stuff via the MicroPython REPL

positional arguments:
  {detect,run,ls,cat,pull,push,rm,mount}
                        sub-command help
    detect              help locating a board
    run                 execute file contents on target
    ls                  list files
    cat                 print contents of one file
    pull                file(s) to copy from target
    push                file(s) to copy onto target
    rm                  remove files on target
    mount               Make target files accessible via FUSE

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  set the serial port
  -b BAUDRATE, --baudrate BAUDRATE
                        set the baud rate
  -c COMMAND, --command COMMAND
                        execute given code on target
  -i, --interactive     drop to interactive shell at the end
  -u USER, --user USER  response to login prompt
  -w PASSWORD, --password PASSWORD
                        response to password prompt
  -v, --verbose         show diagnostic messages, repeat for more
  --develop             show tracebacks on errors (development of this tool)


One ``--verbose`` prints progress information on stderr for some actions, e.g.
``push``. A second ``--verbose`` (e.g. ``-vv``) also prints the data exchanged
between PC and target.

The order of operation is as follows:

1) execute action
2) run statements that are given with ``--command``
3) start miniterm if ``--interactive`` is given

All of these steps can be combined or used on their own.

The environment variables ``MPY_PORT``, ``MPY_BAUDRATE``, ``MPY_USER`` and
``MPY_PASSWORD`` are used as defaults if the corresponding command line options
are not given. And if those are not given, the default is ``hwgrep://USB`` and
115200 baud, and None for user and password.

``hwgrep://USB`` picks a random USB-Serial adapter, works best if there
is only one MicroPython board connected. Otherwise the detect action should
be used to find the comport and use ``--port`` option or environment
variable.

If ``--user`` and ``--password`` are given, it waits for a login and password
prompt after connecting. This is useful when connecting to a WiPy via telnet.


Actions
=======

``detect``
----------
Help finding MicroPython boards.

By default it simply lists all serial ports. If ``--test`` is used, each of
the ports is opened (with the given ``--baudrate``) and tested for a Python
prompt. If there is no response it runs in a timeout, so this option is
quite a bit slower that just listing the ports.

usage: there detect [-h] [-t]

optional arguments:
  -h, --help  show this help message and exit
  -t, --test  open and test each port


``run``
-------
Execute the contents of a (small) file on the target, without saving it to
the targets file system.

The file contents is sent to the REPL. The execution time is limited (see
``--timeout`` option to change) unless ``--interactive`` is given, then
miniterm is started immediately.

usage: there run [-h] [FILE]

positional arguments:
  FILE        load this file contents

optional arguments:
  -h, --help                        show this help message and exit
  -t TIMEOUT, --timeout TIMEOUT     wait x seconds for completion

Note, larger files can be executed using ``push`` and ``--command`` combined.


``ls``
------
List files on the targets file system. With ``--long`` more details are shown
such as the file size.

usage: there ls [-h] [-l] [-r] [PATH [PATH ...]]

positional arguments:
  PATH                  paths to list

optional arguments:
  -h, --help            show this help message and exit
  -l, --long            show more info
  -r, --recursive       list contents of directories


The file date (shown in ``--long`` format) is often not very useful as most
MicroPython boards do not have a battery backed RTC running.


``cat``
-------
Loads a file from the target and prints it contents to stdout (in binary mode).

usage: there cat [-h] PATH

positional arguments:
  PATH        filename on target

optional arguments:
  -h, --help  show this help message and exit


``rm``
------
Remove files and/or directories on the target.

usage: there rm [-h] [-r] [-f] PATH [PATH ...]

positional arguments:
  PATH                  filename on target

optional arguments:
  -h, --help            show this help message and exit
  -f, --force           delete anyway / no error if not existing
  -r, --recursive       remove directories recursively
  --dry-run             do not actually create anything on target


``pull``
--------
Copies files and directories from the MicroPython board to the PC.

The remote path should be absolute (starting with ``/``) and supports
wildcards, e.g. ``/*.py``. On POSIX systems it may be needed to escape
wildcards to avoid local expansion (e.g.  ``/\*.py`` or with quotes
``"/*.py"``.

usage: there pull [-h] [-r] [--dry-run] REMOTE [REMOTE ...] LOCAL

positional arguments:
  REMOTE           one or more source files/directories
  LOCAL            destination directory

optional arguments:
  -h, --help       show this help message and exit
  -r, --recursive  copy recursively
  --dry-run        do not actually copy files, just print names


``push``
--------
Copies files and directories from the PC to the MicroPython board.

The remote path should be absolute (starting with ``/``). When copying a single
file, the remote path may be a directory or a path including filename. When
copying multiple files it must be a directory. The local path supports
wildcards, e.g. ``*.py``.

usage: there push [-h] [-r] [--dry-run] LOCAL [LOCAL ...] REMOTE

positional arguments:
  LOCAL            one or more source files/directories
  REMOTE           destination directory

optional arguments:
  -h, --help       show this help message and exit
  -r, --recursive  copy recursively
  --dry-run        do not actually create anything on target

Directories named ``__pycache__`` are excluded.

The action can also be combined with ``--command`` and
``--interactive`` to start the downloaded code and see its
output.


``mount``
---------
Mount the target as file system via FUSE.

usage: there mount [-h] [-e] MOUNTPOINT

positional arguments:
  MOUNTPOINT     local mount point, directory must exist

optional arguments:
  -h, --help     show this help message and exit
  -e, --explore  auto open file explorer at mount point

A virtual file system is created and attached to the given directory. It
mirrors the contents of the MicroPython board. Operations such as creating,
renaming, deleting are supported.

To improve performance, the mount command is caching data such as directory
listings and stat file infos. The cache is set to be valid for 10 seconds.
