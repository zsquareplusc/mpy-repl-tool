====================
 REPL Transfer Tool
====================

docs: https://mpy-repl-tool.readthedocs.io/en/latest


Transfer files via Python REPL (Read Evaluate Print Loop). This tool was
developed to transfer files from and to MicroPython boards.

This is yet an other tool, there are now several similar tools but not all have
the same features.

Key features of this one:

- ``detect`` serial ports and MicroPython boards.
- ``run`` temporary scripts.
- ``pull`` get files and directories from the target filesystem.
- ``push`` files and directories on the target filesystem.
- ``mount`` target as filesystem (FUSE).
- ``--interactive`` mode (terminal).
- set RTC
- All of the above, and more, via the serial REPL connection to a MicroPython board.


Usage
=====
Here is the output of ``python3 -m there --help``::

  usage: __main__.py [-h] [-p PORT] [-b BAUDRATE] [--set-rtc]
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
    --command-timeout T   timeout in seconds for --command
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

The ``-c`` option executes the given string after running all the actions.
The ``-i`` option enters a miniterm session at the end of all other actions.

The tool automatically selects a USB port for communication, it may take the
wrong one if multiple USB serial devices are connected. In that case, use
``there detect`` to list all devices and then ``-p PORT`` to specify the
port to use on the other calls.

Use ``python3 -m there <action> --help`` to get help on sub-commands.


Requirements
============
This tool requires Python 3.

It depends on pySerial for communication and the mount function requires
fusepy. Those dependencies are automatically installed when using pip,
see installation notes in documentation.
