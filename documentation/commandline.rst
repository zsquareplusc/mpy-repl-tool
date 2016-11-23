=============
 Commandline
=============

$ python3 -m there -h

usage: __main__.py [-h] [-p PORT] [-b BAUDRATE] [-c COMMAND] [-i] [-v]
                   [--develop]
                   {detect,run,ls,cat,put,rm,mount} ...

Do stuff via the MicroPython REPL

positional arguments:
  {detect,run,ls,cat,put,rm,mount}
                        sub-command help
    detect              help locating a board
    run                 execute file contents on target
    ls                  list files
    cat                 print contents of one file
    put                 file(s) to copy onto target
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
  -v, --verbose         show diagnostic messages
  --develop             show tracebacks on errors (development of this tool)


One ``--verbose`` prints progress information on sys.stderr for some actions,
e.g. ``put`` A seconds ``--verbose`` (e.g. ``-vv``) also prints the data
exchanged between PC and target.

Global options must be mentioned before the action, options for the action
itself after that.
