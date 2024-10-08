#!python
"""Developers automated tools
Several tools to automate development related tasks.
"""

from atexit import register as atexit_register
from json import loads as json_loads
from logging import getLogger
from os import environ, name as os_name
from pathlib import Path
from re import match as re_match
from shutil import rmtree
from subprocess import PIPE, STDOUT, run
from sys import executable, stderr
from tempfile import mkdtemp
from webbrowser import open as webbrowser_open

from pip._vendor.packaging.tags import sys_tags
from tomli import load as tomli_load

__version__ = '0.1.2.dev4'

LOGGER = getLogger(__name__)

DEFAULT_EXTRA_ENV_VARIABLES = {
	'DJANGO_DEBUG': 'true',
	'DJANGO_LOG_LEVEL': 'debug',
	'PORT': '8080',
}


class VirtualEnvironmentManager:
	"""Manage a virtual environment
	A hopefully useful class to manage your local python virtual environment using subprocess.
	"""
	
	WHEEL_NAMING_CONVENTION = r'(?P<distribution>.+)-(?P<version>[^-]+)(?:-(?P<build_tag>[^-]+))?-(?P<python_tag>[^-]+)-(?P<abi_tag>[^-]+)-(?P<platform_tag>[^-]+)\.whl'
	
	def __call__(self, *arguments, program='python', cwd=None, env=None, capture_output=None):
		"""Run something
		Run the virtual environment's python with the provided arguments
		
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
		
	def __init__(self, path='venv', overwrite=False, system_site_packages=False):
		"""Magic initialization
		Initial environment creation, re-creation, or just assume it's there.
		
		:param str|Path? path: the root path for the virtual environment
		:param bool? overwrite: always creates new virtual environments (it deletes the existing one first)
		:param bool? system_site_packages: add the "--system-site-packages" switch to the venv creation
		"""
		
		if path is None:
			self.path = (Path(mkdtemp()) / 'venv').absolute()
			self._is_temp = True
		else:
			self.path = Path(path).absolute()
			self._is_temp = False
		
		#Storing for __repr__
		if overwrite:
			self._overwrite = overwrite
		if system_site_packages:
			self._system_site_packages = system_site_packages
		
		if overwrite and self.path.exists():
			if self.path in Path(executable).parents:
				raise RuntimeError("You can't run this command from your virtual environment")
			rmtree(self.path)
		
		venv_extra_params = []
		if system_site_packages:
			venv_extra_params.append('--system-site-packages')
		
		if not self.path.exists():
			if self._is_temp:
				atexit_register(rmtree, self.path.parent, ignore_errors=True)
			run((executable, '-m', 'venv', str(self.path), *venv_extra_params), capture_output=True, check=True, text=True)
			self('-m', 'pip', 'install', '--upgrade', 'pip')
	
	def __repr__(self):
		"""Magic representation
		An evaluable python expression describing the current virtual environment
		
		:returns str: a valid python string to recreate this object
		"""
		
		if self._is_temp:
			parameters = ['path=None']
		else:
			parameters = ['path=' + repr(str(self.path))]
		if hasattr(self, '_overwrite'):
			parameters.append('overwrite=' + repr(self._overwrite))
		if hasattr(self, '_system_site_packages'):
			parameters.append('system_site_packages=' + repr(self._system_site_packages))
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
	
	def download(self, *packages, dest='.', no_deps=True):
		"""Downloads a package
		The package can be whatever "pip install" expects.
		
		:param str packages: a list of packages to download. Could be anything that "pip download" expects
		:param str|Path? dest: place to put the downloaded wheels
		:param bool? no_deps: if provided adds the "--no-deps" switch to the command
		:returns str: the result of the command, "pip download ..."
		"""
		
		command = ['download', '--dest', dest]
		if no_deps:
			command.append('--no-deps')
		command += list(packages)
		
		return self(*command, program='pip')
	
	def freeze(self, list_format=None):
		"""Pip freeze
		Gets the list of packages installed on the virtual environment
		
		:param str? list_format: if None (default) a "pip freeze" run is performed, otherwise is passed as a format to "pip list --format {format}"
		:returns str: the result of the command, "pip freeze" or "pip list --format {format}"
		"""
		
		if list_format is None:
			return self('freeze', program='pip', capture_output=True).stdout
		else:
			return self('list', '--format', list_format, program='pip', capture_output=True).stdout
	
	def install(self, *packages, upgrade=False, no_index=False, no_deps=False):
		"""Installs a package
		The package can be whatever "pip install" expects.
		
		:param str packages: a list of packages to install. Could be anything that "pip install" expects
		:param bool? upgrade: if provided adds the "--upgrade" switch to the command
		:param bool? no_index: if provided adds the "--no-index" switch to the command
		:param bool? no_deps: if provided adds the "--no-deps" switch to the command
		:returns str: the result of the command "pip install ..."
		"""
		
		command = ['install']
		if upgrade:
			command.append('--upgrade')
		if no_index:
			command.append('--no-index')
		if no_deps:
			command.append('--no-deps')
		command += list(packages)
		
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


def deploy_local_venv(system_site_packages=False):
	"""Deploy a local virtual environment
	Based on the current working directory, creates a python3 virtual environment (of the default python 3 on the system) on "./venv/" and populates it with the dependencies described on the "./pyproject.toml" file.
	"""
	
	virtual_env = VirtualEnvironmentManager(overwrite=True, system_site_packages=system_site_packages)
	
	pyproject_toml_path = Path.cwd() / 'pyproject.toml'
	
	if not pyproject_toml_path.exists():
		raise RuntimeError('Missing "{}" file'.format(pyproject_toml_path))
	
	with pyproject_toml_path.open('rb') as pyproject_toml_f:
		pyproject_toml = tomli_load(pyproject_toml_f)
	
	if ('build-system' in pyproject_toml) and ('requires' in pyproject_toml['build-system']):
		LOGGER.info('Installing build related modules')
		virtual_env.install(*pyproject_toml['build-system']['requires'])
	
	if ('project' in pyproject_toml) and ('dependencies' in pyproject_toml['project']):
		LOGGER.info('Installing dependencies')
		virtual_env.install(*pyproject_toml['project']['dependencies'])
	
	if ('project' in pyproject_toml) and ('optional-dependencies' in pyproject_toml['project']):
		for section, modules in pyproject_toml['project']['optional-dependencies'].items():
			LOGGER.info('Installing optional dependencies: %s', section)
			virtual_env.install(*modules)
	
	return virtual_env, pyproject_toml


def deploy_local_django_site(*secret_json_files_paths, system_site_packages=False, django_site_name='test_site', superuser_password='', just_build=False):
	"""Deploy a local Django site
	Starts by deploying a new virtual environment via "deploy_local_env()" and then creates a test site with symlinks to the existing project files. It runs the test server until it gets stopped (usually with ctrl + c).
	"""
	
	secret_json_files_paths = [Path(json_file_path) for json_file_path in secret_json_files_paths]
	for json_file_path in secret_json_files_paths:
		if not json_file_path.is_file():
			raise RuntimeError('The provided file does not exists or is not accessible by you: {}'.format(json_file_path))
	
	environment_content = {}
	for json_file_path in secret_json_files_paths:
		environment_content.update({key.upper(): value for key, value in json_loads(json_file_path.read_text()).items()})
	
	virtual_env, pyproject_toml = deploy_local_venv(system_site_packages=system_site_packages)
	current_directory = Path.cwd()
	base_dir = current_directory / django_site_name
	site_dir = base_dir / django_site_name
	root_from_site = Path('..') / '..'
	
	LOGGER.info('Removing test site directory: %s', base_dir)
	run(('rm', '-rfv', str(base_dir)), stdout=stderr)
	
	LOGGER.info('Creating a new test site')
	virtual_env('startproject', django_site_name, program='django-admin')
	
	if ('tool' in pyproject_toml) and ('setuptools' in pyproject_toml['tool']) and ('packages' in pyproject_toml['tool']['setuptools']) and ('find' in pyproject_toml['tool']['setuptools']['packages']) and ('include' in pyproject_toml['tool']['setuptools']['packages']['find']):
		for pattern in pyproject_toml['tool']['setuptools']['packages']['find']['include']:
			for resulting_path in current_directory.glob(pattern):
				base_content = base_dir / resulting_path.name
				content_from_base = Path('..') / resulting_path.name
				LOGGER.info('Linking module content: %s -> %s', base_content, content_from_base)
				base_content.symlink_to(content_from_base)
	
	if (current_directory / 'urls.py').exists():
		site_urls_py = site_dir / 'urls.py'
		LOGGER.info('Cleaning vanilla router file: %s', site_urls_py)
		site_urls_py.unlink(missing_ok=True)
		urls_from_site = root_from_site / 'urls.py'
		LOGGER.info('Linking router file: %s -> %s', site_urls_py, urls_from_site)
		site_urls_py.symlink_to(urls_from_site)
	
	if (current_directory / 'jinja2.py').exists():
		site_jinja2_py = site_dir / 'jinja2.py'
		jinja2_from_site = root_from_site / 'jinja2.py'
		LOGGER.info('Linking Jinja2 configuration: %s -> %s', site_jinja2_py, jinja2_from_site)
		site_jinja2_py.symlink_to(jinja2_from_site)
	
	if (current_directory / 'settings.py').exists():
		site_settings_py = site_dir / 'local_settings.py'
		settings_from_site = root_from_site / 'settings.py'
		LOGGER.info('Linking settings file: %s -> %s', site_settings_py, settings_from_site)
		site_settings_py.symlink_to(settings_from_site)
	
	static_files_dir = base_dir / 'storage' / 'staticfiles'
	LOGGER.info('Creating the static file directory: %s', static_files_dir)
	static_files_dir.mkdir(parents=True)
	
	manage_py = base_dir / 'manage.py'
	LOGGER.info('Creating the cache table')
	virtual_env(str(manage_py), 'createcachetable', '--settings=test_site.local_settings', program='python', env=environ | environment_content)
	LOGGER.info('Applying migrations')
	virtual_env(str(manage_py), 'migrate', '--settings=test_site.local_settings', program='python', env=environ | environment_content)
	
	result = [
		'######################################################################',
		'',
		'You can run this again with:',
		'',
		'env DJANGO_DEBUG=true `./venv/bin/python -m env_pipes vars_from_file --uppercase_vars {secret_files}` ./venv/bin/python ./test_site/manage.py runserver --settings=test_site.local_settings'.format(secret_files=' '.join([str(s) for s in secret_json_files_paths])),
		'',
	]
	
	if len(superuser_password):
		current_user = run(('whoami',), capture_output=True, text=True).stdout.strip('\n')
		super_user_details = {
			'DJANGO_SUPERUSER_LOGIN': current_user,
			'DJANGO_SUPERUSER_FIRSTNAME': current_user,
			'DJANGO_SUPERUSER_LASTNAME': current_user,
			'DJANGO_SUPERUSER_EMAIL': '{}@example.local'.format(current_user),
			'DJANGO_SUPERUSER_PASSWORD': superuser_password,
		}
		LOGGER.info('Creating the super user: %s', current_user)
		virtual_env(str(manage_py), 'createsuperuser', '--noinput', '--settings=test_site.local_settings', program='python', env=environ | environment_content | super_user_details)
		
		result += [
			'Then go to http://localhost:8000/admin and use credentials {user}:{password}'.format(user=current_user, password=superuser_password),
			'',
		]
	
	LOGGER.info('\n'.join(result + ['######################################################################']))
	
	if not just_build:
		webbrowser_open('http://localhost:8000/admin')
		return virtual_env(str(manage_py), 'runserver', '--settings=test_site.local_settings', program='python', env=environ | environment_content | {'DJANGO_DEBUG': 'true'})


def start_local_docker_container(*secret_json_files_paths, extra_env_variables=None, platform=None, build_only=False):
	"""Start local Docker container
	Build and run a container based on the Dockerfile on the current working directory.
	"""
	
	secret_json_files_paths = [Path(json_file_path) for json_file_path in secret_json_files_paths]
	for json_file_path in secret_json_files_paths:
		if not json_file_path.is_file():
			raise RuntimeError(
				'The provided file does not exists or is not accessible by you: {}'.format(json_file_path))
	
	environment_content = DEFAULT_EXTRA_ENV_VARIABLES.copy() if extra_env_variables is None else dict(extra_env_variables)
	
	for json_file_path in secret_json_files_paths:
		environment_content.update({key.upper(): value for key, value in json_loads(json_file_path.read_text()).items()})
	
	build_command = ['docker', 'build']
	if platform is not None:
		build_command += ['--platform', platform]
	for var_name in environment_content:
		build_command += ['--build-arg', var_name]
	
	current_directory = Path.cwd()
	
	LOGGER.debug('Environment populated: %s', environment_content)
	build_command += ['--tag', '{}:latest'.format(current_directory.name), str(current_directory)]
	LOGGER.debug('Running build command: %s', build_command)
	build_run = run(build_command, env=environ | environment_content)
	build_run.check_returncode()
	
	if not build_only:
		
		run_command = ['docker', 'run', '-d', '--rm', '--name', '{}_test'.format(current_directory.name)]
		for var_name in environment_content:
			run_command += ['-e', var_name]
		run_command += ['-p', '127.0.0.1:{PORT}:{PORT}'.format(PORT=environment_content['PORT']), '{}:latest'.format(current_directory.name)]
		
		run_run = run(run_command, env=environ | environment_content)
		run_run.check_returncode()
		
		return run(('docker', 'logs', '-f', '{}_test'.format(current_directory.name)))


def stop_local_docker_container():
	"""Stop local Docker container
	Stop a container started with "start_local_docker_container" on the current local directory.
	"""
	
	return run(('docker', 'stop', '{}_test'.format(Path.cwd().name)))
