#!/usr/bin/env python

from distutils.core import setup

setup(name='gingham',
      version='1.0',
      description='API test helper',
      author='Tom Brennan',
      author_email='tjb1982@gmail.com',
      url='https://github.com/tjb1982/gingham',
      py_modules=['gingham', 'merge'],
      scripts=["gingham.py"],
     )
