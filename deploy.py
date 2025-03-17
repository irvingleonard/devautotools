#!python
"""Developers automated tools
This module includes the basic tools to deploy virtual environment for your projects. Trying to use it to deploy this module's virtual environment generates a circular dependency: enters this script. This installs the bare requirements to get the virtual environment going, then parses the pyproject.toml file and installs all the listed dependencies
"""

from atexit import register as atexit_register
from logging import getLogger
from os import name as os_name
from pathlib import Path
from shutil import rmtree
from subprocess import run
from sys import executable
from tempfile import mkdtemp

LOGGER = getLogger(__name__)
DEPENDENCIES = ('simplifiedapp', 'tomli')


class TempMiniVirtualEnvironmentManager:
	"""Manage a virtual environment
	A hopefully useful class to manage your local python virtual environment using subprocess.
	"""

	def __call__(self, *arguments, program='python'):
		"""Run something
		Use subprocess.run with a virtual environment's "program" and the provided arguments

		:param str arguments: a list of arguments to provide to the program
		:param str? program: the program to run. It should be the name of one of the ones present in "bin/" (or "Scripts\" in Windows)
		:returns CompletedProcess: the result of the run
		"""

		program_path = self.bin_scripts / program
		if os_name == 'nt':
			program_path = program_path.with_suffix('.exe')
		if not program_path.exists():
			raise ValueError('Unsupported program: {}'.format(program_path))

		return run((str(program_path),) + tuple(arguments), check=True)

	def __getattr__(self, name):
		"""Magic attribute resolution
		Lazy calculation of certain attributes

		:param str name: the attribute that is not defined (yet)
		:returns Any: the value for the attribute
		"""

		if name == 'bin_scripts':
			value = self.path / ('Scripts' if os_name == 'nt' else 'bin')
		else:
			raise AttributeError(name)

		self.__setattr__(name, value)
		return value

	def __init__(self):
		"""Magic initialization
		Initial environment creation.
		"""

		self.path = (Path(mkdtemp()) / 'venv').absolute()

		atexit_register(rmtree, self.path.parent, ignore_errors=True)

		run((executable, '-m', 'venv', str(self.path)), capture_output=True, check=True, text=True)
		self('-m', 'pip', 'install', '--upgrade', 'pip')

	def __repr__(self):
		"""Magic representation
		An evaluable python expression describing the current virtual environment

		:returns str: a valid python string to recreate this object
		"""

		return '{}()'.format(type(self).__name__)

	def __str__(self):
		"""Magic cast to string
		Returns the path to the virtual environment

		:returns str: the path to the virtual environment
		"""

		return str(self.path)

	def install(self, *packages):
		"""Installs a package
		The package can be whatever "pip install" expects.

		:param str packages: a list of packages to install. Could be anything that "pip install" expects
		:returns str: the result of the command "pip install ..."
		"""

		command = ['install', '--upgrade'] + list(packages)
		return self(*command, program='pip')

venv = TempMiniVirtualEnvironmentManager()
venv.install(*DEPENDENCIES)
venv('-m', 'devautotools', 'deploy_local_venv')
