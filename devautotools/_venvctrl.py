#!python
"""Overriding venvctrl
Missing functionality from venvctrl (https://github.com/kevinconway/venvctrl).
"""

from atexit import register as atexit_register
from json import loads as json_loads
from logging import getLogger
from os import name as os_name
from pathlib import Path
from re import match as re_match
from shutil import rmtree
from subprocess import PIPE, STDOUT, run
from sys import executable
from tempfile import mkdtemp

from pip._vendor.packaging.tags import sys_tags

from ._utils import options_for_cli

LOGGER = getLogger(__name__)


class VirtualEnvironmentManager:
	"""Manage a virtual environment
	A hopefully useful class to manage your local python virtual environment using subprocess.
	"""
	
	WHEEL_NAMING_CONVENTION = r'(?P<distribution>.+)-(?P<version>[^-]+)(?:-(?P<build_tag>[^-]+))?-(?P<python_tag>[^-]+)-(?P<abi_tag>[^-]+)-(?P<platform_tag>[^-]+)\.whl'
	
	def __call__(self, *arguments, program='python', cwd=None, env=None, capture_output=None):
		"""Run something
		Use subprocess.run with a virtual environment's "program" and the provided arguments

		:param str arguments: a list of arguments to provide to the program
		:param str? program: the program to run. It should be the name of one of the ones present in "bin/" (or "Scripts\" in Windows)
		:param str|Path? cwd: current working directory for the run
		:param dict? env: environment values to use for the run
		:param bool? capture_output: the "file" to forward the output to
		:returns CompletedProcess: the result of the run
		"""
		
		program_path = self.bin_scripts / program
		if os_name == 'nt':
			program_path = program_path.with_suffix('.exe')
		if not program_path.exists():
			raise ValueError('Unsupported program: {}'.format(program_path))
		run_args = {
			'cwd': cwd,
			'check': True,
			'env': env,
		}
		if capture_output is not None:
			run_args.update({
				'stderr': STDOUT,
				'text': True,
			})
			if isinstance(capture_output, bool) and capture_output:
				run_args['stdout'] = PIPE
			else:
				run_args['stdout'] = capture_output
		
		return run((str(program_path),) + tuple(arguments), **run_args)
	
	def __enter__(self):
		"""Context manager initialization
		Magic method used to initialize the context manager

		:returns VirtualEnvironmentManager: this object is itself a context manager
		"""
		
		return self
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager termination
		Magic method used to terminate the context manager

		:param Type[BaseException]? exc_type: the type of exception that occurred
		:param BaseException? exc_val: the exception that occurred as an object
		:param TracebackType? exc_tb: the traceback of the occurred exception
		"""
		
		LOGGER.debug('Ignoring exception in context: %s(%s) | %s', exc_type, exc_val, exc_tb)
	
	def __getattr__(self, name):
		"""Magic attribute resolution
		Lazy calculation of certain attributes

		:param str name: the attribute that is not defined (yet)
		:returns Any: the value for the attribute
		"""
		
		if name == 'bin_scripts':
			value = self.path / ('Scripts' if os_name == 'nt' else 'bin')
		elif name == 'compatible_tags':
			value = {str(tag) for tag in sys_tags()}
		else:
			raise AttributeError(name)
		
		self.__setattr__(name, value)
		return value
	
	def __init__(self, _path='venv', _overwrite=False, /, **create_options):
		"""Magic initialization
		Initial environment creation, re-creation, or just assume it's there.

		:param str|Path? _path: the root path for the virtual environment
		:param bool? _overwrite: always creates new virtual environments (it deletes the existing one first)
		:param Any? create_options: map of options to pass to the "create" command.
		"""
		
		if _path is None:
			self.path = (Path(mkdtemp()) / 'venv').absolute()
			self._is_temp = True
		else:
			self.path = Path(_path).absolute()
			self._is_temp = False
		
		# Storing for __repr__
		if _overwrite:
			self._overwrite = _overwrite
		self._create_options = create_options
		
		if _overwrite and self.path.exists():
			if self.path in Path(executable).parents:
				raise RuntimeError("You can't run this command from your virtual environment")
			LOGGER.info('Deleting existing content')
			rmtree(self.path)
		
		if not self.path.exists():
			if self._is_temp:
				atexit_register(rmtree, self.path.parent, ignore_errors=True)
			LOGGER.info('Creating virtual environment')
			run((executable, '-m', 'venv', str(self.path), *options_for_cli(create_options)), capture_output=True, check=True, text=True)
			LOGGER.info('Upgrading pip')
			self('-m', 'pip', 'install', '--upgrade', 'pip')
	
	def __repr__(self):
		"""Magic representation
		An evaluable python expression describing the current virtual environment

		:returns str: a valid python string to recreate this object
		"""
		
		if self._is_temp:
			parameters = ['None']
		else:
			parameters = [repr(str(self.path))]
		if hasattr(self, '_overwrite'):
			parameters.append(repr(self._overwrite))
		parameters += [f'{option}={repr(value)}' for option, value in self._create_options.items()]
		return '{}({})'.format(type(self).__name__, ', '.join(parameters))
	
	def __str__(self):
		"""Magic cast to string
		Returns the path to the virtual environment

		:returns str: the path to the virtual environment
		"""
		
		return str(self.path)
	
	def compatible_wheel(self, wheel_name):
		"""Check wheel compatibility
		Uses the platform tag from the wheel name to check if it's compatible with the current platform.

		Using the list from https://stackoverflow.com/questions/446209/possible-values-from-sys-platform

		:param str wheel_name: the wheel name to be analyzed
		:returns bool: if it's compatible or not
		"""
		
		details = self.parse_wheel_name(wheel_name)
		possible_tags = set()
		for python_tag in details['python_tag']:
			for abi_tag in details['abi_tag']:
				for platform_tag in details['platform_tag']:
					possible_tags.add('-'.join((python_tag, abi_tag, platform_tag)))
		
		return bool(possible_tags & self.compatible_tags)
	
	def download(self, *packages, dest='.', **options):
		"""Downloads a package
		The "packages" can be whatever "pip download" expects.

		:param str packages: a list of packages to download. Could be anything that "pip download" expects
		:param str|Path? dest: place to put the downloaded wheels
		:param options: map of options to pass to the "download" command.
		:returns str: the result of the command, "pip download ..."
		"""

		options['dest'] = dest
		command = ['download'] + options_for_cli(options) + list(packages)
		return self(*command, program='pip')
	
	def freeze(self, list_format=None):
		"""Pip freeze
		Gets the list of packages installed on the virtual environment. It can also do "pip list", depends on the "list_format".

		:param str? list_format: if None (default) a "pip freeze" run is performed, otherwise is passed as a format to "pip list --format {format}"
		:returns str: the result of the command, "pip freeze" or "pip list --format {format}"
		"""
		
		if list_format is None:
			return self('freeze', program='pip', capture_output=True).stdout
		else:
			return self('list', '--format', list_format, program='pip', capture_output=True).stdout
	
	def install(self, *packages, **options):
		"""Installs a package
		The package can be whatever "pip install" expects and the behavior can be controlled with switches.

		:param str packages: a list of packages to install. Could be anything that "pip install" expects
		:param options: map of the options to pass to the "install" command.
		:returns str: the result of the command "pip install ..."
		"""

		command = ['install'] + options_for_cli(options) + list(packages)
		return self(*command, program='pip')
	
	@property
	def modules(self):
		"""List of modules
		Simple "pip list" as a python dictionary (name : version)

		:returns dict: a mapping of the installed packages and their current versions
		"""
		
		return {module['name']: module['version'] for module in json_loads(self.freeze(list_format='json'))}
	
	@classmethod
	def parse_wheel_name(cls, wheel_name):
		"""Parse wheel name
		Parse the provided name according to PEP-491

		:param str wheel_name: the wheel name to be parsed
		:returns dict: the different components of the name or None if not a valid name
		"""
		
		result = re_match(cls.WHEEL_NAMING_CONVENTION, wheel_name)
		if result is not None:
			result = result.groupdict()
			# Because PEP-425 is a thing
			if result['python_tag']:
				result['python_tag'] = result['python_tag'].split('.')
			if result['abi_tag']:
				result['abi_tag'] = result['abi_tag'].split('.')
			if result['platform_tag']:
				result['platform_tag'] = result['platform_tag'].split('.')
		
		return result
