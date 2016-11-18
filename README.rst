====================
 REPL Transfer Tool
====================

Transfer files via Python REPL (Read Eval Print Loop). This tool was developed
to transfer files from and to MicroPython boards.

This is yet an other tool, there are now several similar tools but not all have
the same features.

Usage
=====

Here is the output of `python3 -m there --help`:

    usage: there.py [-h] [-c COMMAND] [-i] [-v] {run,ls,cat,put} ...

    Do stuff via the MicroPython REPL

    positional arguments:
      {run,ls,cat,put}      sub-command help
        run                 execute file contents on target
        ls                  list files
        cat                 print content of one file
        put                 file(s) to copy onto target

    optional arguments:
      -h, --help            show this help message and exit
      -c COMMAND, --command COMMAND
                            execute given code on target
      -i, --interactive     drop to interactive shell at the end
      -v, --verbose         show diagnostic messages


The ``-c`` option executes the given string after running all the actions.
The ``-i`` option enters a miniterm sesstion at the end of all other actions.

.. note::

    Currently the escape handling in miniterm is disabled which makes editing
    on the MicroPython REPL a bit inconvenient.

Use `python3 -m there <action> --help` to get help on sub-commands.
