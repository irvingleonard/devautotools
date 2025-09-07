#!python
"""Django stuff
Some helper functionality around Django projects.
"""

from base64 import b64decode
from email.utils import getaddresses as parse_email_addresses
from importlib import import_module
from json import loads as json_loads
from logging import getLogger
from os import environ, getenv, name as os_name
from pathlib import Path
from re import compile as re_compile, search as re_search, IGNORECASE as RE_IGNORECASE
from shutil import rmtree
from subprocess import run
from warnings import warn
from webbrowser import open as webbrowser_open

from ._tempfile import mkstemp
from ._venv import deploy_local_venv

LOGGER = getLogger(__name__)
POSSIBLE_LOG_LEVELS = ('INFO', 'CRITICAL', 'ERROR', 'WARNING', 'DEBUG')
REQUIRED_SECTION_RE = re_compile(r'(:?.+_required)|(:?required_.+)', RE_IGNORECASE)
TRUTH_LOWERCASE_STRING_VALUES = ('true', 'yes', 'on', '1')


def _decode_setting(django_settings, base_var_name, lowercase=False):
	"""Decode a setting
	Given an environment variable name, find the correct value for the corresponding setting. The setting name would be the base name. The logic is:
	1. if the base_var_name is found, it's returned as is and the "decoded" flag is False
	2. if base_var_name + "_CONTENT" is found (ex: FOO_CONTENT) then the content is returned as is.
	3. if base_var_name + "_BASE64" is found (ex: FOO_BASE64) then the content of the variable is base64 decoded before returning it.
	In every case but #1 the "decoded" flag will be True, meaning that you can use it to identify if this function found the "base_var_name" or a variation of it.
	If you're not interested on the decoding flag and want the decoded value unconditionally, use the "decode_setting" instead.

	:param django_settings: the global variables from the original settings.py file
	:type django_settings: dict
	:param base_var_name: the name of the environment variable to look for
	:type base_var_name: str
	:param lowercase: if the variations suffixes should be lowercase
	:type lowercase: bool
	:return: A tuple of length 2, with the "decoded" flag first and the decoded content of the variable on the 2nd.
	:rtype: tuple
	"""
	
	env_var_variations = {
		'CONTENT': base_var_name + ('_content' if lowercase else '_CONTENT'),
		'BASE64': base_var_name + ('_base64' if lowercase else '_BASE64'),
	}
	
	decoded, content = True, None
	if base_var_name in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		decoded, content = False, django_settings['ENVIRONMENTAL_SETTINGS'][base_var_name]
	elif env_var_variations['CONTENT'] in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		content = django_settings['ENVIRONMENTAL_SETTINGS'][env_var_variations['CONTENT']]
	elif env_var_variations['BASE64'] in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		content = b64decode(django_settings['ENVIRONMENTAL_SETTINGS'][env_var_variations['BASE64']])
	else:
		decoded = False
	
	return decoded, content

decode_setting = lambda django_settings, base_var_name, lowercase=False: _decode_setting(django_settings=django_settings, base_var_name=base_var_name, lowercase=lowercase)[1]


def deploy_local_django_site(*secret_json_files_paths, dev_from_pypi=False, venv_options={}, pip_install_options={}, django_site_name='test_site', extra_paths_to_link='', create_cache_table=False, superuser_password='', just_build=False):
	"""Deploy a local Django site
	Starts by deploying a new virtual environment via "deploy_local_env()" and then creates a test site with symlinks to the existing project files. It runs the test server until it gets stopped (usually with ctrl + c).
	"""

	return DjangoLinkedSite.deploy_locally(*secret_json_files_paths, django_site_name=django_site_name, extra_paths_to_link=extra_paths_to_link, create_cache_table=create_cache_table, superuser_password=superuser_password, dev_from_pypi=dev_from_pypi, venv_options=venv_options, pip_install_options=pip_install_options, just_build=just_build)


def django_normalized_settings(*settings_module_names, django_settings, loose_list=False):
	"""Normalized Django settings system workhorse
	The interface to use the normalized Django settings system. It's usually added as:

	settings_module_names = (
		'devautotools',
		'foo.settings',
		'bar.settings',
	)
	global_state = globals()
	global_state |= django_normalized_settings(*settings_module_names, django_settings=globals())

	The modules will be processed in the provided order, so value overrides if present will apply in the same order.

	:param settings_module_names: module names to load; each of them could include "EXPECTED_VALUES_FROM_ENV" and "IMPLICIT_ENVIRONMENTAL_SETTINGS" constants and a "common_settings" callable.
	:type settings_module_names: str
	:param django_settings: usually the "globals()" from the calling settings.py
	:type django_settings: Any
	:param loose_list: will not stop execution when it fails to load a "settings_module" if False
	:type loose_list: bool
	"""

	settings_modules = []
	for module_name in settings_module_names:
		try:
			if isinstance(module_name, str):
				settings_modules.append(import_module(module_name))
			else:
				settings_modules.append(import_module(*module_name))
		except ImportError:
			if loose_list:
				LOGGER.exception("Couldn't load settings module: %s", module_name)
			else:
				raise

	django_settings = django_settings.copy()
	if 'EXPECTED_VALUES_FROM_ENV' not in django_settings:
		django_settings['EXPECTED_VALUES_FROM_ENV'] = {}
	if 'IMPLICIT_ENVIRONMENTAL_SETTINGS' not in django_settings:
		django_settings['IMPLICIT_ENVIRONMENTAL_SETTINGS'] = {}
	for settings_module in settings_modules:
		django_settings['EXPECTED_VALUES_FROM_ENV'] |= getattr(settings_module, 'EXPECTED_VALUES_FROM_ENV', {})
		django_settings['IMPLICIT_ENVIRONMENTAL_SETTINGS'] |= getattr(settings_module, 'IMPLICIT_ENVIRONMENTAL_SETTINGS', {})

	if 'ENVIRONMENTAL_SETTINGS' not in django_settings:
		django_settings['ENVIRONMENTAL_SETTINGS'] = {}
	django_settings['ENVIRONMENTAL_SETTINGS'] |= django_settings['IMPLICIT_ENVIRONMENTAL_SETTINGS'].copy() | django_settings_env_capture(**django_settings['EXPECTED_VALUES_FROM_ENV'])
	django_settings['ENVIRONMENTAL_SETTINGS_KEYS'] = frozenset(django_settings['ENVIRONMENTAL_SETTINGS'].keys())

	for settings_module in settings_modules:
		if hasattr(settings_module, 'normalized_settings'):
			django_settings = getattr(settings_module, 'normalized_settings')(**django_settings)

	return django_settings


def django_settings_env_capture(**expected_sections):
	"""Capture Django settings
	Parses the current environment and collect variables applicable to the Django site.

	:param expected_sections:
	:type expected_sections:
	:return:
	:rtype:
	"""
	
	known_variations = (
		'_CONTENT',
		'_content',
		'_BASE64',
		'_base64',
	)
	
	required_expected_sections, optional_expected_sections = set(), set()
	for expected_section in expected_sections:
		if re_search(REQUIRED_SECTION_RE, expected_section) is None:
			optional_expected_sections.add(expected_section)
		else:
			required_expected_sections.add(expected_section)
	environmental_settings, missing_setting_from_env = {}, []

	for required_section in required_expected_sections:
		for required_setting in expected_sections[required_section]:
			required_setting_found = False
			for known_variation in known_variations:
				required_setting_variation = required_setting + known_variation
				required_setting_value = getenv(required_setting_variation, '')
				if len(required_setting_value):
					environmental_settings[required_setting_variation] = required_setting_value
					required_setting_found = True
			else:
				required_setting_value = getenv(required_setting, '')
				if len(required_setting_value):
					environmental_settings[required_setting] = required_setting_value
					required_setting_found = True
			if not required_setting_found:
				missing_setting_from_env.append(required_setting)
	if len(missing_setting_from_env):
		raise RuntimeError(f'Missing required settings from env: {missing_setting_from_env}')

	for optional_section in optional_expected_sections:
		for optional_setting in expected_sections[optional_section]:
			optional_setting_found = False
			for known_variation in known_variations:
				optional_setting_variation = optional_setting + known_variation
				optional_setting_value = getenv(optional_setting_variation, '')
				if len(optional_setting_value):
					environmental_settings[optional_setting_variation] = optional_setting_value
					optional_setting_found = True
			else:
				optional_setting_value = getenv(optional_setting, '')
				if len(optional_setting_value):
					environmental_settings[optional_setting] = optional_setting_value
					optional_setting_found = True
			if not optional_setting_found:
				missing_setting_from_env.append(optional_setting)
	if len(missing_setting_from_env):
		warn(f'Missing optional settings from env: {missing_setting_from_env}', RuntimeWarning)
	for key, value in environ.items():
		if key[:7] == 'DJANGO_':
			environmental_settings[key] = value

	return environmental_settings


def normalize_variable_name(variable_name):
	"""Normalize a variable name
	Given a environmental variable name, return the base name (without "_CONTENT" or "_BASE64" suffixes).

	:param variable_name: the name of the variable
	:type variable_name: str
	:return: the normalized name
	:rtype: str
	"""

	variable_name_upper = variable_name.upper()
	if variable_name_upper.endswith('_BASE64'):
		return variable_name[:-7]
	elif variable_name_upper.endswith('_CONTENT'):
		return variable_name[:-8]
	else:
		return variable_name


def normalized_settings(**django_settings):
	"""Common values for Django
	Generates basic values for your Django settings.py file.

	:param django_settings: the current Django settings collection (ultimately the content of globals())
	:type django_settings: Any
	:return: new content for Django settings
	"""

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
			base_key = normalize_variable_name(key)
			database_options[base_key[24:]] = path_for_setting(django_settings=django_settings, base_var_name=base_key, lowercase=True)
		elif key[:16] == 'DJANGO_DATABASE_':
			database_settings[key[16:]] = django_settings['ENVIRONMENTAL_SETTINGS'][key]
	if database_settings:
		if database_options:
			database_settings['OPTIONS'] = database_options
		else:
			warn('Potentially missing database SSL options; the connection could be insecure.', RuntimeWarning)
		django_settings['DATABASES'] = {'default' : database_settings}
	else:
		warn('Not enough information to connect to an external database; using the builtin SQLite', RuntimeWarning)

	if 'DJANGO_EMAIL_BACKEND' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_BACKEND'] = django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_BACKEND']
	if 'DJANGO_EMAIL_HOST' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_HOST'] = django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_HOST']
	if 'DJANGO_EMAIL_PORT' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_PORT'] = int(django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_PORT'])
	if 'DJANGO_EMAIL_TIMEOUT' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_TIMEOUT'] = int(django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_TIMEOUT'])
	if 'DJANGO_EMAIL_USE_SSL' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_USE_SSL'] = setting_is_true(django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_USE_SSL'])
	if (('EMAIL_USE_SSL' not in django_settings) or not django_settings['EMAIL_USE_SSL']) and ('DJANGO_EMAIL_USE_TLS' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']):
		django_settings['EMAIL_USE_TLS'] = setting_is_true(django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_USE_TLS'])
	if 'DJANGO_EMAIL_FILE_PATH' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_FILE_PATH'] = django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_FILE_PATH']

	if 'DJANGO_EMAIL_HOST_USER' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_HOST_USER'] = django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_HOST_USER']
	if 'DJANGO_EMAIL_HOST_PASSWORD' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_HOST_PASSWORD'] = django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_HOST_PASSWORD']
	django_email_ssl_certfile = path_for_setting(django_settings=django_settings, base_var_name='DJANGO_EMAIL_SSL_CERTFILE')
	if django_email_ssl_certfile is not None:
		django_settings['EMAIL_SSL_CERTFILE'] = django_email_ssl_certfile
	django_email_ssl_keyfile = path_for_setting(django_settings=django_settings, base_var_name='DJANGO_EMAIL_SSL_KEYFILE')
	if django_email_ssl_keyfile is not None:
		django_settings['EMAIL_SSL_KEYFILE'] = django_email_ssl_keyfile

	server_email = django_settings['ENVIRONMENTAL_SETTINGS'].get('DJANGO_SERVER_EMAIL', '')
	default_from_email = django_settings['ENVIRONMENTAL_SETTINGS'].get('DJANGO_DEFAULT_FROM_EMAIL', '')
	if server_email and default_from_email:
		django_settings['SERVER_EMAIL'] = server_email
		django_settings['DEFAULT_FROM_EMAIL'] = default_from_email
	elif server_email:
		django_settings['SERVER_EMAIL'] = django_settings['DEFAULT_FROM_EMAIL'] = server_email
	elif default_from_email:
		django_settings['SERVER_EMAIL'] = django_settings['DEFAULT_FROM_EMAIL'] = default_from_email
	admin_addresses = parse_email_addresses(django_settings['ENVIRONMENTAL_SETTINGS'].get('DJANGO_ADMINS', ''))
	manager_addresses = parse_email_addresses(django_settings['ENVIRONMENTAL_SETTINGS'].get('DJANGO_MANAGERS', ''))
	if admin_addresses and manager_addresses:
		django_settings['ADMINS'] = admin_addresses
		django_settings['MANAGERS'] = manager_addresses
	elif admin_addresses:
		django_settings['ADMINS'] = django_settings['MANAGERS'] = admin_addresses
	elif manager_addresses:
		django_settings['ADMINS'] = django_settings['MANAGERS'] = manager_addresses

	if 'DJANGO_EMAIL_SUBJECT_PREFIX' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_SUBJECT_PREFIX'] = setting_is_true(django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_SUBJECT_PREFIX'])
	if 'DJANGO_EMAIL_USE_LOCALTIME' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['EMAIL_USE_LOCALTIME'] = setting_is_true(django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_EMAIL_USE_LOCALTIME'])

	if 'DJANGO_ALLOWED_HOSTS' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['ALLOWED_HOSTS'] = django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_ALLOWED_HOSTS'].split(',')
	if 'DJANGO_CSRF_TRUSTED_ORIGINS' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
		django_settings['CSRF_TRUSTED_ORIGINS'] = django_settings['ENVIRONMENTAL_SETTINGS']['DJANGO_CSRF_TRUSTED_ORIGINS'].split(',')

	return django_settings


def path_for_setting(django_settings, base_var_name, lowercase=False):
	"""Path for a setting
	Given an environment variable name, decode the content if applicable, write it into a temporary file and return the path to such file. The "decoding" logic is implemented on the "_decode_setting" function. The file is created using "mkstemp" and any related limitations and security considerations apply. The file is automatically removed when the Python interpreter ends (atexit + os.remove).

	:param django_settings: the global variables from the original settings.py file
	:type django_settings: dict
	:param base_var_name: the name of the environment variable to look for
	:type base_var_name: str
	:param lowercase: if the variations suffixes should be lowercase
	:type lowercase: bool
	:return: The path for the setting
	:rtype: any
	"""
	
	decoded, content = _decode_setting(django_settings=django_settings, base_var_name=base_var_name, lowercase=lowercase)
	if not decoded:
		return content
	
	extra_mode = 't' if isinstance(content, str) else 'b'
	
	file_desc, file_path = mkstemp(text=True, session=True)
	with open(file_path, f'w{extra_mode}') as file_obj:
		file_obj.write(content)

	return file_path


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
	DEFAULT_START_URL = 'http://localhost:8000'
	
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
			result |= json_loads(json_file_path.read_text())

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
		
		env_django_debug = ['$env:DJANGO_DEBUG=true;'] if os_name == 'nt' else ['env DJANGO_DEBUG=true']
		
		if secret_json_files_paths:
			env_python_path = '.\\venv\\Scripts\\python.exe' if os_name == 'nt' else './venv/bin/python'
			inline_vars = ['`{env_python_path} -m devautotools env_with_vars_from_json {secret_files}`'.format(env_python_path=env_python_path, secret_files=' '.join([str(s) for s in secret_json_files_paths]))]
		else:
			inline_vars = []

		result = [
			'######################################################################',
			'',
			'You can run this again with:',
			'',
			' '.join(env_django_debug + inline_vars + ['./venv/bin/python ./test_site/manage.py runserver --settings=test_site.local_settings']),
			'',
		]

		if superuser is not None:
			result += [
				f'Then go to {cls.DEFAULT_START_URL} and use credentials {superuser[0]}:{superuser[1]}',
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
			current_user = current_user.split('\\')[-1]
			username_parameter_name = environ.get('DJANGO_CREATESUPERUSER_USERNAME', 'username')
			email_parameter_name = environ.get('DJANGO_CREATESUPERUSER_EMAIL', 'email')

			super_user_details = {
				f'DJANGO_SUPERUSER_{username_parameter_name.upper()}': current_user,
				'DJANGO_SUPERUSER_FIRSTNAME': current_user,
				'DJANGO_SUPERUSER_LASTNAME': current_user,
				f'DJANGO_SUPERUSER_{email_parameter_name.upper()}': f'{current_user}@example.local',
				'DJANGO_SUPERUSER_PASSWORD': superuser_password,
			}
			LOGGER.info('Creating the super user: %s', current_user)
			self.venv(str(self.manage_py), 'createsuperuser', '--noinput', f'--settings={self.site_name}.local_settings', env=environ|environment_content|super_user_details)
			return current_user, superuser_password

	def start(self, *secret_json_files_paths, start_url=None):
		"""Start the Django site
		Start the site using the "runserver" Django command and open it on the default browser.
		"""

		environment_content = self._environ_from_json(*secret_json_files_paths)
		if start_url is None:
			start_url = self.DEFAULT_START_URL

		webbrowser_open(start_url)
		return self.venv(str(self.manage_py), 'runserver', '--settings={}.local_settings'.format(self.site_name), env=environ|environment_content|{'DJANGO_DEBUG': 'true'})
