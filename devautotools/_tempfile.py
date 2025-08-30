"""
Additions for the upstream "tempfile" module.
"""

from atexit import register as atexit_register
from os import remove as os_remove
from tempfile import mkstemp as _mkstemp


def mkstemp(*args, session=False, **kwargs):
	"""
	Adds a "session" parameter that will delete the temporary file when the Python interpreter ends.
	"""
	
	file_desc, file_path = _mkstemp(*args, **kwargs)
	
	if session:
		atexit_register(os_remove, file_path)
	
	return file_desc, file_path