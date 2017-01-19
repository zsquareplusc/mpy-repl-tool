=================
 Getting Started
=================

Installation
============
::

    python3 -m pip install mpy-repl-tool
    python3 -m pip install "mpy-repl-tool[mount]"

Use the second line to support the ``mount`` command. On windows, use ``py -3``
instead of ``python3``.

The source code is available at github_.

.. _github: https://github.com/zsquareplusc/mpy-repl-tool


Find a MicroPython board
========================
::

    # list serial ports
    python3 -m there detect

    # and optionally also test them for a running MicroPython
    # (interrupts a running program on target)
    python3 -m there detect --test

The following examples automatically pick the first USB-Serial adapter to
communicate, add a ``-p COMxy`` option or set the ``MPY_PORT`` environment
variable to choose a different one.

Usage examples
==============
::

    # run a file without copying it to the target's file system:
    python3 -m there run test.py

    # get a file list
    python3 -m there ls

    # file listing with more details
    python3 -m there ls -l

    # read the contents of a file from the target
    python3 -m there cat /somepath/somefile

    # copy multiple files from computer to target
    python3 -m there push *.py /flash

    # backup all the files on the pc
    python3 -m there pull -r \* backup

Adding a ``-i`` starts a serial terminal::

    python3 -m there -i

    # or after running an other action
    python3 -m there -i run test.py

An few statements can be executed using ``-c`` and it can be combined with other options::

    python3 -m there push xy.py / -c "import xy; xy.test()" -i

When FUSE is available on the system and ``fusepy`` was installed, it is also
possible to browse the files in a file navigator/explorer::

    mkdir mpy-board
    python3 -m there mount mpy-board

See also :ref:`mount_windows`, it currently requires a hack to get it working there.

Connection to telnet REPLs such as the one provided by the WiPy is also possible::

    python3 -m there -p socket://192.168.1.1:23 -u micro -w python -i
