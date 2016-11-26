==========
 Appendix
==========

.. _mount_windows:

Getting ``mount`` to run on Windows
===================================

Install https://github.com/dokan-dev/dokany/releases/tag/v1.0.1
(Tested with V1.0.1)

Patch fuse.py:

at the top, add an new ``elif``::

    if _system == 'Darwin':
        ...
    elif _system == 'Windows':
        import os
        os.environ['PATH'] += r';C:\Program Files\Dokan\Dokan Library-1.0.1'
        _libfuse_path = find_library('dokanfuse1.dll')
    else:
        ...

and line around 980::

    elif _system == 'Linux':

to::

    elif _system == 'Linux' or _system == 'Windows':


Now it is possible to use ``py -3 -m there mount xxx`` where xxx is an existing
directory and the data is then visible in that directory.

License
=======

.. include:: ../LICENSE.txt
