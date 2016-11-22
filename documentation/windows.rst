

Getting ``mount`` to run on Windows
===================================

Install https://github.com/dokan-dev/dokany/releases/tag/v1.0.1
(Tested with V1.0.1)

XXX prepeare patch

Patch fuse.py:

at the top, replace the code in ``else``::

    if _system == 'Darwin':
        ...
    else:
        import os
        os.environ['PATH'] += r';C:\Program Files\Dokan\Dokan Library-1.0.1'
        _libfuse_path = find_library('dokanfuse1.dll')

and line around 980::

    elif _system == 'Linux' or _system == 'Windows':

to::

    elif _system == 'Linux' or _system == 'Windows':


now it is possible to use ``py -3 -m there mount xxx`` where xxx is an existing
directory and the data is then visible in that directory.