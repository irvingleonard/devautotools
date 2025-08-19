#!python
"""Django stuff
Some helper functionality around Django projects.
"""

from atexit import register as atexit_register
from base64 import b64decode
from json import loads as json_loads
from logging import getLogger
from os import environ, getenv, remove as os_remove
from pathlib import Path
from re import compile as re_compile, search as re_search, IGNORECASE as RE_IGNORECASE
from shutil import rmtree
from subprocess import run
from tempfile import mkstemp
from warnings import warn
from webbrowser import open as webbrowser_open

from ._venv import deploy_local_venv

LOGGER = getLogger(__name__)
POSSIBLE_LOG_LEVELS = ('INFO', 'CRITICAL', 'ERROR', 'WARNING', 'DEBUG')
REQUIRED_SECTION_RE = re_compile(r'(:?.+_required)|(:?required_.+)', RE_IGNORECASE)
SSL_FILE_OPTIONS = ('sslcert', 'sslkey', 'sslrootcert')
TRUTH_LOWERCASE_STRING_VALUES = ('true', 'yes', 'on', '1')

def django_common_settings(settings_globals, parent_callables=None):
	"""Common values for Django
	Generates Django values for your settings.py file. It's usually added as:

	global_state = globals()
	global_state |= django_common_settings(globals())

	:param settings_globals: the caller's "globals"
	:param parent_callables: an optional list of parent "common_settings" callables
	:type parent_callables: [callable]|None
	:return: new content for "globals"
	"""

	django_settings = settings_globals.copy()

	if 'EXPECTED_VALUES_FROM_ENV' not in django_settings:
		django_settings['EXPECTED_VALUES_FROM_ENV'] = {}

	if parent_callables is None:
		if 'ENVIRONMENTAL_SETTINGS' not in django_settings:
			django_settings['ENVIRONMENTAL_SETTINGS'] = {}
		django_settings['ENVIRONMENTAL_SETTINGS'] |= django_settings_env_capture()
		django_settings['ENVIRONMENTAL_SETTINGS_KEYS'] = frozenset(django_settings['ENVIRONMENTAL_SETTINGS'].keys())
	elif parent_callables:
		parent_common_settings = parent_callables.pop(0)
		django_settings = parent_common_settings(django_settings, parent_callables=parent_callables)
	else:
		if 'ENVIRONMENTAL_SETTINGS' not in django_settings:
			django_settings['ENVIRONMENTAL_SETTINGS'] = {}
		django_settings['ENVIRONMENTAL_SETTINGS'] |= django_settings_env_capture(**django_settings['EXPECTED_VALUES_FROM_ENV'])
		django_settings['ENVIRONMENTAL_SETTINGS_KEYS'] = frozenset(django_settings['ENVIRONMENTAL_SETTINGS'].keys())

	django_settings['DEBUG'] = setting_is_true(django_settings['ENVIRONMENTAL_SETTINGS'].get('DJANGO_DEBUG', ''))

	django_log_level = django_settings['ENVIRONMENTAL_SETTINGS'].get('DJANGO_LOG_LEVEL', '').upper()
	if django_log_level not in POSSIBLE_LOG_LEVELS:
		django_log_level = POSSIBLE_LOG_LEVELS[0]
	django_settings['LOGGING'] = {
		'version': 1,
		'disable_existing_loggers': False,
		'handlers': {
			'console': {
				'level': 'DEBUG',
				'class': 'logging.StreamHandler',
			},
		},
		'loggers': {
			'': {
				'handlers': ['console'],
				'level': 'DEBUG' if django_settings['DEBUG'] else django_log_level,
				'propagate': True,
			},
		},
	}

	django_settings['STATIC_URL'] = '/static/'
	django_settings['STATIC_ROOT'] = django_settings['BASE_DIR'] / 'storage' / 'staticfiles'
	django_settings['STORAGES'] = {
		'default': {
			'BACKEND': 'django.core.files.storage.FileSystemStorage',
			'OPTIONS': {
				'location': django_settings['BASE_DIR'] / 'storage' / 'media',
			},
		},
		'staticfiles': {
			'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
			'OPTIONS': {
				'location': django_settings['STATIC_ROOT'],
				'base_url': django_settings['STATIC_URL'],
			},
		},
	}
	Path(django_settings['STORAGES']['default']['OPTIONS']['location']).mkdir(parents=True, exist_ok=True)
	Path(django_settings['STORAGES']['staticfiles']['OPTIONS']['location']).mkdir(parents=True, exist_ok=True)

	database_settings, database_options = {}, {}
	for key in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		if key[:24] == 'DJANGO_DATABASE_OPTIONS_':
			local_key = key[24:]
			database_options[local_key.lower()] = django_settings['ENVIRONMENTAL_SETTINGS'][local_key]
		elif key[:16] == 'DJANGO_DATABASE_':
			local_key = key[16:]
			database_settings[local_key] = django_settings['ENVIRONMENTAL_SETTINGS'][local_key]
	if database_settings:
		if database_options:
			for key in list(database_options.keys()):
				if key.rstrip('_base64').rstrip('_content').rstrip('_path') in SSL_FILE_OPTIONS:
					if key[-5:] == '_path':
						clean_key = key[:-5]
						file_content = None
						file_path = database_options[key]
					elif key[-7:] == '_base64':
						clean_key = key[:-7]
						file_content = b64decode(django_settings['ENVIRONMENTAL_SETTINGS'][key]).decode()
					elif key[-8:] == '_content':
						clean_key = key[:-8]
						file_content = django_settings['ENVIRONMENTAL_SETTINGS'][key]
					else:
						warn(f'Unknown Database SSL file option variation: {key}', RuntimeWarning)
						continue
					if file_content is not None:
						file_desc, file_path = mkstemp(text=True)
						atexit_register(os_remove, file_path)
						with open(file_path, 'wt') as file_obj:
							file_obj.write(file_content)
					database_options[clean_key] = file_path
			database_settings['OPTIONS'] = database_options
		else:
			warn(f'Potentially missing database SSL options; the connection could be insecure: {SSL_FILE_OPTIONS}')
		django_settings['DATABASES'] = {'default' : database_settings}
	else:
		warn('Not enough information to connect to an external database; using the builtin SQLite', RuntimeWarning)

	return django_settings

def deploy_local_django_site(*secret_json_files_paths, dev_from_pypi=False, venv_options={}, pip_install_options={}, django_site_name='test_site', extra_paths_to_link='', create_cache_table=False, superuser_password='', just_build=False):
	"""Deploy a local Django site
	Starts by deploying a new virtual environment via "deploy_local_env()" and then creates a test site with symlinks to the existing project files. It runs the test server until it gets stopped (usually with ctrl + c).
	"""

	return DjangoLinkedSite.deploy_locally(*secret_json_files_paths, django_site_name=django_site_name, extra_paths_to_link=extra_paths_to_link, create_cache_table=create_cache_table, superuser_password=superuser_password, dev_from_pypi=dev_from_pypi, venv_options=venv_options, pip_install_options=pip_install_options, just_build=just_build)


def django_settings_env_capture(**expected_sections):
	"""Capture Django settings
	Parses the current environment and collect variables applicable to the Django site.

	:param expected_sections:
	:type expected_sections:
	:return:
	:rtype:
	"""

	required_expected_sections, optional_expected_sections = set(), set()
	for expected_section in expected_sections:
		if re_search(REQUIRED_SECTION_RE, expected_section) is None:
			optional_expected_sections.add(expected_section)
		else:
			required_expected_sections.add(expected_section)
	environmental_settings, missing_setting_from_env = {}, []

	for required_section in required_expected_sections:
		for required_setting in expected_sections[required_section]:
			required_setting_value = getenv(required_setting, '')
			if len(required_setting_value):
				environmental_settings[required_setting] = required_setting_value
			else:
				missing_setting_from_env.append(required_setting)
	if len(missing_setting_from_env):
		raise RuntimeError(f'Missing required settings from env: {missing_setting_from_env}')

	for optional_section in optional_expected_sections:
		for optional_setting in expected_sections[optional_section]:
			optional_setting_value = getenv(optional_setting, '')
			if len(optional_setting_value):
				environmental_settings[optional_setting] = optional_setting_value
			else:
				missing_setting_from_env.append(optional_setting)
	if len(missing_setting_from_env):
		warn(f'Missing optional settings from env: {missing_setting_from_env}', RuntimeWarning)
	for key, value in environ.items():
		if key[:7] == 'DJANGO_':
			environmental_settings[key] = value

	return environmental_settings

def setting_is_true(value):
	"""Setting is True
	Compares the provided string to the known "truth" values. Uses the list in TRUTH_LOWERCASE_STRING_VALUES.

	:param str value: the value to check
	:returns bool: if the string matches a "true" value
	"""

	return value.strip().lower() in TRUTH_LOWERCASE_STRING_VALUES

class DjangoLinkedSite:
	"""Django linked site
	Create a Django site using symlinks to the project files. Potentially useful to develop Django applications while testing them live.
	"""
	
	DEFAULT_PROJECT_TO_SITE_MAP = {
		'settings.py': 'local_settings.py',
		'urls.py': None,
	}
	
	def __getattr__(self, name):
		"""Magic attribute resolution
		Lazy calculation of certain attributes

		:param str name: the attribute that is not defined (yet)
		:returns Any: the value for the attribute
		"""
		
		if (name == 'venv') or (name == 'pyproject_toml'):
			venv, pyproject_toml = deploy_local_venv(dev_from_pypi=self.dev_from_pypi, env_create_options=self.venv_options, pip_install_options=self.pip_install_options)
			if name == 'venv':
				value = venv
				self.__setattr__('pyproject_toml', pyproject_toml)
			else:
				value = pyproject_toml
				self.__setattr__('venv', venv)
		elif name == 'base_dir':
			value = self.parent_dir / self.site_name
		elif name == 'manage_py':
			value = self.base_dir / 'manage.py'
		elif name == 'site_dir':
			value = self.base_dir / self.site_name
		else:
			raise AttributeError(name)
		
		self.__setattr__(name, value)
		return value
	
	def __init__(self, site_name, project_dir=Path.cwd(), parent_dir=Path.cwd(), virtual_environment_pyproject_toml=(None, None), dev_from_pypi=False, venv_options={}, pip_install_options={}):
		"""
		Magic initiation

		:param str site_name: the site name, the only required value
		:returns None: init shouldn't return
		"""
		
		self.site_name = site_name
		self.project_dir = Path(project_dir).absolute()
		self.parent_dir = Path(parent_dir).absolute()
		virtual_environment, pyproject_toml = virtual_environment_pyproject_toml
		if (virtual_environment is not None) and (pyproject_toml is not None):
			self.venv = virtual_environment
			self.pyproject_toml = pyproject_toml
		self.dev_from_pypi = dev_from_pypi
		self.venv_options = venv_options
		self.pip_install_options = pip_install_options

	@staticmethod
	def _environ_from_json(*secret_json_files_paths):
		"""Environ from JSON files
		Parse content of JSON files and build environment dict.
		"""

		secret_json_files_paths = [Path(json_file_path) for json_file_path in secret_json_files_paths]
		for json_file_path in secret_json_files_paths:
			if not json_file_path.is_file():
				raise RuntimeError('The provided file does not exists or is not accessible by you: {}'.format(json_file_path))

		result = {}
		for json_file_path in secret_json_files_paths:
			result.update({key.upper(): value for key, value in json_loads(json_file_path.read_text()).items()})

		return result

	def _relative_to_project(self, path):
		"""Relative path
		Build a relative path from the one provided pointing to the project's dir. The "name" should be the one in the project dir, though.
		"""
		
		path = Path(path)
		if self.project_dir in path.parents:
			return Path('.').joinpath(*([Path('..')] * path.parents.index(self.project_dir))) / path.name
		else:
			return (self.project_dir / path.name).absolute()
	
	def create(self, overwrite=True, project_paths_to_site=''):
		"""Create the Django site
		Runs the basic "django-admin startproject" and also links the related files
		"""
		
		if overwrite and self.base_dir.exists():
			LOGGER.info('Deleting current site: %s', self.base_dir)
			rmtree(self.base_dir)
		elif self.base_dir.exists():
			raise FileExistsError('The site is already present. Use the "overwrite" parameter to recreate it')
		
		LOGGER.info('Creating new site: %s', self.site_name)
		self.venv('startproject', self.site_name, program='django-admin', cwd=self.parent_dir)
		
		if ('tool' in self.pyproject_toml) and ('setuptools' in self.pyproject_toml['tool']) and ('packages' in self.pyproject_toml['tool']['setuptools']) and ('find' in self.pyproject_toml['tool']['setuptools']['packages']) and ('include' in self.pyproject_toml['tool']['setuptools']['packages']['find']):
			for pattern in self.pyproject_toml['tool']['setuptools']['packages']['find']['include']:
				for resulting_path in self.project_dir.glob(pattern):
					base_content = self.base_dir / resulting_path.name
					content_from_base = self._relative_to_project(base_content)
					LOGGER.info('Linking module content: %s -> %s', base_content, content_from_base)
					base_content.symlink_to(content_from_base)

		project_paths_to_site = project_paths_to_site.split(',') if project_paths_to_site else []
		project_to_site_map = self.DEFAULT_PROJECT_TO_SITE_MAP | dict(zip(project_paths_to_site, [None] *len(project_paths_to_site)))
		for project_path_name, site_path_name in project_to_site_map.items():
			if (self.project_dir / project_path_name).exists():
				site_path = self.site_dir / (project_path_name if site_path_name is None else site_path_name)
				if site_path.exists():
					LOGGER.info('Cleaning site path: %s', site_path)
					site_path.unlink()
				content_from_site = self._relative_to_project(self.site_dir / project_path_name)
				LOGGER.info('Linking path: %s -> %s', site_path, content_from_site)
				site_path.symlink_to(content_from_site)
			else:
				LOGGER.warning("Couldn't find file in project directory: %s", project_path_name)

	@classmethod
	def deploy_locally(cls, *secret_json_files_paths, django_site_name='test_site', extra_paths_to_link='', create_cache_table=False, superuser_password='', dev_from_pypi=False, venv_options={}, pip_install_options={}, just_build=False):
		"""Deploy a local Django site
		Starts by deploying a new virtual environment via "deploy_local_env()" and then creates a test site with symlinks to the existing project files. It runs the test server until it gets stopped (usually with ctrl + c).
		"""

		environment_content = cls._environ_from_json(*secret_json_files_paths)

		site = cls(django_site_name, dev_from_pypi=dev_from_pypi, venv_options=venv_options, pip_install_options=pip_install_options)
		if (pip_install_options is None) or not pip_install_options:
			pip_install_options = {}
		if dev_from_pypi:
			pip_install_options |= {
				'pre': True,
				'extra-index-url': 'https://test.pypi.org/simple',
			}
		site.venv.install('devautotools', **pip_install_options)
		site.create(project_paths_to_site=extra_paths_to_link)
		superuser = site.initialize(environment_content=environment_content, create_cache_table=create_cache_table, superuser_password=superuser_password)

		if secret_json_files_paths:
			inline_vars = ['`./venv/bin/python -m devautotools env_vars_from_json --uppercase_vars {secret_files}`'.format(secret_files=' '.join([str(s) for s in secret_json_files_paths]))]
		else:
			inline_vars = []

		result = [
			'######################################################################',
			'',
			'You can run this again with:',
			'',
			' '.join(['env DJANGO_DEBUG=true'] + inline_vars + ['./venv/bin/python ./test_site/manage.py runserver --settings=test_site.local_settings']),
			'',
		]

		if superuser is not None:
			result += [
				'Then go to http://localhost:8000/admin and use credentials {user}:{password}'.format(user=superuser[0], password=superuser[1]),
				'',
			]

		LOGGER.info('\n'.join(result + ['######################################################################']))

		if not just_build:
			site.start(*secret_json_files_paths)

		return result

	def initialize(self, environment_content={}, create_cache_table=False, superuser_password=''):
		"""Initialize the Django site
		Create the cache table if requested, apply the migrations and create a superuser using the currently logged in username ad the password provided.
		"""

		if create_cache_table:
			LOGGER.info('Creating the cache table')
			self.venv(str(self.manage_py), 'createcachetable', '--settings={}.local_settings'.format(self.site_name), env=environ|environment_content)

		LOGGER.info('Applying migrations')
		self.venv(str(self.manage_py), 'migrate', '--settings={}.local_settings'.format(self.site_name), env=environ|environment_content)

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
			self.venv(str(self.manage_py), 'createsuperuser', '--noinput', '--settings={}.local_settings'.format(self.site_name), env=environ|environment_content|super_user_details)
			return current_user, superuser_password

	def start(self, *secret_json_files_paths):
		"""Start the Django site
		Start the site using the "runserver" Django command and open it on the default browser.
		"""

		environment_content = self._environ_from_json(*secret_json_files_paths)

		webbrowser_open('http://localhost:8000/admin')
		return self.venv(str(self.manage_py), 'runserver', '--settings={}.local_settings'.format(self.site_name), env=environ|environment_content|{'DJANGO_DEBUG': 'true'})
