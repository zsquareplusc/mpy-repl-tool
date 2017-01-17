====================
 REPL Transfer Tool
====================

docs: https://mpy-repl-tool.readthedocs.io/en/latest


Transfer files via Python REPL (Read Eval Print Loop). This tool was developed
to transfer files from and to MicroPython boards.

This is yet an other tool, there are now several similar tools but not all have
the same features.

Key features of this one:

- ``detect`` serial ports and micropython boards.
- ``run`` temporary scripts.
- ``pull`` get files and directories from the target filesystem.
- ``push`` files and directories on the target filesystem.
- ``mount`` target as filesytem (FUSE).
- ``--interactive`` mode (terminal).
- All of the above, and more, via the serial REPL connection to a micropython board.


Usage
=====

Here is the output of ``python3 -m there --help``::

    usage: __main__.py [-h] [-p PORT] [-b BAUDRATE] [-c COMMAND] [-i] [-v]
                       detect,run,ls,cat,pull,push,rm,mount} ...

    Do stuff via the MicroPython REPL

    positional arguments:
      {detect,run,ls,cat,put,rm,mount}
                            sub-command help
        detect              help locating a board
        run                 execute file contents on target
        ls                  list files
        cat                 print content of one file
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

The ``-c`` option executes the given string after running all the actions.
The ``-i`` option enters a miniterm session at the end of all other actions.

The tool automatically selects a USB port for communication, it may take the
wrong one if multiple USB serial devices are connected. In that case, use
``there detect`` to list all devices and then ``-p PORT`` to specify the
port to use on the other calls.

Use ``python3 -m there <action> --help`` to get help on sub-commands.
