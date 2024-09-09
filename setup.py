#!python
"""A setuptools based setup module.

ToDo:
- Everything
"""

from setuptools import setup
from simplifiedapp import object_metadata

import devautotools

setup(**object_metadata(devautotools))

