#!/usr/bin/env python
#
# Copyright 2013-current Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import ast
import os
import re
from setuptools import setup, find_packages
import sys

assert sys.version_info >= (3, 6, 0), 'pyaib requires Python >=3.6'

thisdir = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(thisdir, 'README.rst'), 'r') as f:
    long_description = f.read()

_version_re = re.compile(r'__version__\s+=\s+(?P<version>.*)')

with open(os.path.join(thisdir, 'pyaib', '__init__.py'), 'r') as f:
        version = _version_re.search(f.read()).group('version')
        version = str(ast.literal_eval(version))

setup(
    name='pyaib',
    version=version,
    url='http://github.com/facebook/pyaib',
    license='Apache 2.0',
    author='Jason Fried, Facebook',
    author_email='fried@fb.com',
    description='Python Framework for writing IRC Bots using gevent',
    long_description=long_description,
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Communications :: Chat :: Internet Relay Chat',
        'Programming Language :: Python :: 3.6',
        'Intended Audience :: Developers',
        'Development Status :: 5 - Production/Stable',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
    ],
    packages=find_packages(
        exclude=['*.test', '*.test.*'],
        include=['pyaib.*', 'pyaib'],
    ),
    test_suite="pyaib.test",
    install_requires=[
        'toml >= 0.9.4',
    ],
)
