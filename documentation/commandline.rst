=============
 Commandline
=============

Overview
========
::

    usage: there [-h] [-p PORT] [-b BAUDRATE] [--set-rtc]
                [--reset-on-connect] [-c COMMAND] [-i] [--reset] [-u USER]
                [-w PASSWORD] [-v] [--develop] [--timeit]
                ACTION ...

    Do stuff via the MicroPython REPL

    optional arguments:
      -h, --help            show this help message and exit

    port settings:
      -p PORT, --port PORT  set the serial port
      -b BAUDRATE, --baudrate BAUDRATE
                            set the baud rate

    operations before running action:
      --set-rtc             set the RTC to "now" before command is executed
      --reset-on-connect    do a soft reset as first operation (main.py will not
                            be executed)

    operations after running action:
      -c COMMAND, --command COMMAND
                            execute given code on target
      -i, --interactive     drop to interactive shell at the end
      --reset               do a soft reset on the end

    login:
      -u USER, --user USER  response to login prompt
      -w PASSWORD, --password PASSWORD
                            response to password prompt

    diagnostics:
      -v, --verbose         show diagnostic messages, repeat for more
      --develop             show tracebacks on errors (development of this tool)
      --timeit              measure command run time

    subcommands:
      use "__main__.py ACTION --help" for more on each sub-command

      ACTION                sub-command help
        detect              help locating a board
        run                 execute file contents on target
        ls                  list files
        hash                hash files
        cat                 print contents of one file
        pull                file(s) to copy from target
        push                file(s) to copy onto target
        rm                  remove files from target
        df                  Show filesystem information
        mount               Make target files accessible via FUSE
        rtc                 Read the real time clock (RTC)

One or two ``--verbose`` flag print progress information on stderr for some
actions, e.g. ``push`` and ``pull`` list deltas with one ``-v`` and all files
with two. A third ``--verbose`` (or ``-vvv``) also prints the data exchanged
between PC and target.

The order of operation is as follows:

1) execute ``--reset-on-connect``
2) execute action (``run``, ``push`` etc.)
3) run statements that are given with ``--command``
4) execute --reset
5) start miniterm if ``--interactive`` is given

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
prompt after connecting. This is useful when connecting to e.g. a WiPy via
telnet.


Actions
=======

``detect``
----------
Help finding MicroPython boards.

By default it simply lists all serial ports. If ``--test`` is used, each of
the ports is opened (with the given ``--baudrate``) and tested for a Python
prompt. If there is no response it runs in a timeout, so this option is
quite a bit slower that just listing the ports.

::

    usage: there detect [-h] [-t]

    optional arguments:
      -h, --help            show this help message and exit
      -t, --test            open and test each port


``run``
-------
Execute the contents of a (small) file on the target, without saving it to
the targets file system.

The file contents is sent to the REPL. The execution time is limited (see
``--timeout`` option to change) unless ``--interactive`` is given, then
miniterm is started immediately.

::

    usage: there run [-h] [-t TIMEOUT] [FILE]

    positional arguments:
      FILE                  load this file contents

    optional arguments:
      -h, --help            show this help message and exit
      -t TIMEOUT, --timeout TIMEOUT
                            wait x seconds for completion

Note, larger files can be executed using ``push`` and ``--command`` combined.


``ls``
------
List files on the targets file system. With ``--long`` more details are shown
such as the file size.

::

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

::

    usage: there cat [-h] PATH

    positional arguments:
      PATH                  filename on target

    optional arguments:
      -h, --help            show this help message and exit


``rm``
------
Remove files and/or directories on the target.

::

    usage: there rm [-h] [-f] [-r] [--dry-run] PATH [PATH ...]

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

::

    usage: there pull [-h] [-r] [--dry-run] REMOTE [REMOTE ...] LOCAL

    positional arguments:
      REMOTE                one or more source files/directories
      LOCAL                 destination directory

    optional arguments:
      -h, --help            show this help message and exit
      -r, --recursive       copy recursively
      --dry-run             do not actually create anything on target


``push``
--------
Copies files and directories from the PC to the MicroPython board.

The remote path should be absolute (starting with ``/``). When copying a single
file, the remote path may be a directory or a path including filename. When
copying multiple files it must be a directory. The local path supports
wildcards, e.g. ``*.py``.

::

    usage: __main__.py push [-h] [-r] [--dry-run] [--force]
                            LOCAL [LOCAL ...] REMOTE

    positional arguments:
      LOCAL            one or more source files/directories
      REMOTE           destination directory

    optional arguments:
      -h, --help       show this help message and exit
      -r, --recursive  copy recursively
      --dry-run        do not actually create anything on target
      --force          write always, skip up-to-date check

Directories named ``.git`` or ``__pycache__`` are excluded.

By default files are first checked (SHA256) if they are already up to date
and copying is not needed. This speeds up transfer substantially. With
``--force``, this check will be skipped and the files are always transferred.

The action can also be combined with ``--command`` and
``--interactive`` to start the downloaded code and see its
output.


``mkdir``
---------
Create new directory.

::

  usage: there mkdir [-h] [--parents] PATH [PATH ...]

  positional arguments:
    PATH        filename on target

  optional arguments:
    -h, --help  show this help message and exit
    --parents   create parents


``hash``
--------
Generate and print a SHA256 hash for each file given.

::

    usage: there hash [-h] [-r] [PATH [PATH ...]]

    positional arguments:
      PATH             paths to list

    optional arguments:
      -h, --help       show this help message and exit
      -r, --recursive  list contents of directories


``df``
------
Show file system info.

::

  usage: theredf [-h] [PATH [PATH ...]]

  positional arguments:
    PATH        remote path

  optional arguments:
    -h, --help  show this help message and exit


``mount``
---------
Mount the target as file system via FUSE.

::

    usage: there mount [-h] [-e] MOUNTPOINT

    positional arguments:
      MOUNTPOINT            local mount point, directory must exist

    optional arguments:
      -h, --help            show this help message and exit
      -e, --explore         auto open file explorer at mount point

A virtual file system is created and attached to the given directory. It
mirrors the contents of the MicroPython board. Operations such as creating,
renaming, deleting are supported.

To improve performance, the mount command is caching data such as directory
listings and stat file infos. The cache is set to be valid for 10 seconds.


``rtc``
-------
Read and print the real time clock on baords that support ``pyb.RTC()``::

    usage: __main__.py rtc [-h] [--test]

    optional arguments:
      -h, --help  show this help message and exit
      --test      test if the clock runs

The ``--test`` function reads the clock twice and check that it is running.
