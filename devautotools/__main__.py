#!python
"""Developers automated tools
Several tools to automate development related tasks.

This is the executable script
"""

from simplifiedapp import main

try:
	import devautotools
except ModuleNotFoundError:
	import __init__ as devautotools

main(devautotools)
