#!/usr/bin/env python3
#
# (C) 2016-2018 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name="mpy-repl-tool",
    #~ description="",
    version='0.6',
    author="Chris Liechti",
    author_email="cliechti@gmx.net",
    url="https://github.com/zsquareplusc/mpy-repl-tool",
    packages=['there'],
    license="BSD",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: MacOS',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Software Development :: Embedded Systems',
    ],
    platforms='any',
    install_requires=[
        'pyserial>=3',
        'colorama',
    ],
    extras_require={
        'mount': ['fusepy'],
    },
    entry_points={
        'console_scripts': [
            'there = there.__main__:main',
        ],
    },
)

