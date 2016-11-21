#!/usr/bin/env python3
#
# (C) 2016 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name="mpy-repl-tool",
    #~ description="",
    version='0.1',
    author="Chris Liechti",
    author_email="cliechti@gmx.net",
    url="https://github.com/zsquareplusc/mpy-repl-tool",
    packages=['there'],
    license="BSD",
    #~ long_description="""\
#~ """,
    #~ classifiers=[
    #~ ],
    platforms='any',
    install_requires=[
        'pyserial>=3'
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

