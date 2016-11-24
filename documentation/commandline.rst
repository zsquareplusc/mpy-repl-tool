=============
 Commandline
=============

Overview
========
usage: there [-h] [-p PORT] [-b BAUDRATE] [-c COMMAND] [-i] [-v]
             [--develop]
             {detect,run,ls,cat,put,rm,mount} ...

Do stuff via the MicroPython REPL

positional arguments:
  {detect,run,ls,cat,put,rm,mount}

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  set the serial port
  -b BAUDRATE, --baudrate BAUDRATE
                        set the baud rate
  -c COMMAND, --command COMMAND
                        execute given code on target
  -i, --interactive     drop to interactive shell at the end
  -v, --verbose         show diagnostic messages
  --develop             show tracebacks on errors (development of this tool)


One ``--verbose`` prints progress information on stderr for some actions, e.g.
``put``. A second and or third ``--verbose`` (e.g. ``-vv``) also prints the
data exchanged between PC and target.

The order of operation is as follows:

1) execute action
2) run statements that are given with ``--command``
3) start miniterm if ``--interactive`` is given

The environment variables ``MPY_PORT``, ``MPY_BAUDRATE``, ``MPY_USER`` and
``MPY_PASSWORD`` are used as defaults if the corresponding command line options
are not given. And if those are not given, the default is ``hwgrep://USB`` and
115200 baud, and None for user and password.

``hwgrep://USB`` picks a random USB-Serial adapter, works best if there
is only one micropython board connected. Otherwise the detect action should
be used to find the comport and use ``--port`` option or environment
variable.


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

The file contents is sent to the REPL.

usage: there run [-h] [FILE]

positional arguments:
  FILE        load this file contents

optional arguments:
  -h, --help  show this help message and exit


``ls``
------
List files on the targets file system. With ``--long`` more details are shown
such as the file size.

usage: there ls [-h] [-l] [PATH [PATH ...]]

positional arguments:
  PATH        paths to list

optional arguments:
  -h, --help  show this help message and exit
  -l, --long  show more info


The file date is often not very useful as most micropython boards do not have a
battery backed RTC running.


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
Remove files on target.
usage: there rm [-h] PATH [PATH ...]

positional arguments:
  PATH        filename on target

optional arguments:
  -h, --help  show this help message and exit


``put``
-------
Copies files and directories from the PC to the micropython board.

usage: there put [-h] [-r] [--dry-run] SRC [SRC ...] DST

positional arguments:
  SRC              one or more source files/directories
  DST              destination directory

optional arguments:
  -h, --help       show this help message and exit
  -r, --recursive  copy recursively
  --dry-run        do not actually create anything on target


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
mirrors the contents of the micropython board. Operations such as creating,
renaming, deleting are supported.

To improve performance, the mount command is caching data such as directory
listings and stat file infos. The cache is set to be valid for 10 seconds.
