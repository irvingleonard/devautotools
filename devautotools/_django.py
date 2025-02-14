#!python
"""Django stuff
Some helper functionality around Django projects.
"""

from json import loads as json_loads
from logging import getLogger
from os import environ
from pathlib import Path
from shutil import rmtree
from subprocess import run
from sys import stderr
from webbrowser import open as webbrowser_open

from ._venv import deploy_local_venv

LOGGER = getLogger(__name__)


DEFAULT_EXTRA_ENV_VARIABLES = {
	'DJANGO_DEBUG': 'true',
	'DJANGO_LOG_LEVEL': 'debug',
	'PORT': '8080',
}

def deploy_local_django_site(*secret_json_files_paths, system_site_packages=False, django_site_name='test_site',
							 extra_files_to_link='', extra_subdirs='', create_cache_table=False, superuser_password='',
							 just_build=False):
	"""Deploy a local Django site
	Starts by deploying a new virtual environment via "deploy_local_env()" and then creates a test site with symlinks to the existing project files. It runs the test server until it gets stopped (usually with ctrl + c).
	"""
	
	secret_json_files_paths = [Path(json_file_path) for json_file_path in secret_json_files_paths]
	for json_file_path in secret_json_files_paths:
		if not json_file_path.is_file():
			raise RuntimeError(
				'The provided file does not exists or is not accessible by you: {}'.format(json_file_path))
	
	environment_content = {}
	for json_file_path in secret_json_files_paths:
		environment_content.update(
			{key.upper(): value for key, value in json_loads(json_file_path.read_text()).items()})
	
	virtual_env, pyproject_toml = deploy_local_venv(system_site_packages=system_site_packages)
	current_directory = Path.cwd()
	base_dir = current_directory / django_site_name
	site_dir = base_dir / django_site_name
	root_from_site = Path('..') / '..'
	
	LOGGER.info('Removing test site directory: %s', base_dir)
	run(('rm', '-rfv', str(base_dir)), stdout=stderr)
	
	LOGGER.info('Creating a new test site')
	virtual_env('startproject', django_site_name, program='django-admin')
	
	if ('tool' in pyproject_toml) and ('setuptools' in pyproject_toml['tool']) and (
			'packages' in pyproject_toml['tool']['setuptools']) and (
			'find' in pyproject_toml['tool']['setuptools']['packages']) and (
			'include' in pyproject_toml['tool']['setuptools']['packages']['find']):
		for pattern in pyproject_toml['tool']['setuptools']['packages']['find']['include']:
			for resulting_path in current_directory.glob(pattern):
				base_content = base_dir / resulting_path.name
				content_from_base = Path('..') / resulting_path.name
				LOGGER.info('Linking module content: %s -> %s', base_content, content_from_base)
				base_content.symlink_to(content_from_base)
	
	PROJECT_TO_SITE_MAP = {
		'settings.py': 'local_settings.py',
		'urls.py'	: None,
	}
	extra_files_to_link = extra_files_to_link.split(',')
	project_to_site_map = PROJECT_TO_SITE_MAP | dict(zip(extra_files_to_link, [None ] *len(extra_files_to_link)))
	
	for project_file_name, site_file_name in project_to_site_map.items():
		if (current_directory / project_file_name).exists():
			site_file = site_dir / project_file_name if site_file_name is None else site_file_name
			LOGGER.info('Cleaning site file: %s', site_file)
			site_file.unlink(missing_ok=True)
			file_from_site = root_from_site / project_file_name
			LOGGER.info('Linking file: %s -> %s', site_file, file_from_site)
			site_file.symlink_to(file_from_site)
		else:
			LOGGER.warning("Couldn't find file in project directory: %s", project_file_name)
	
	extra_subdirs = extra_subdirs.split(',')
	for extra_subdir_name in extra_subdirs:
		extra_subdir = base_dir / extra_subdir_name
		if extra_subdir.is_dir():
			rmtree(extra_subdir)
		elif extra_subdir.exists():
			raise NotADirectoryError(extra_subdir)
		LOGGER.info('Creating directory: %s', extra_subdir)
		extra_subdir.mkdir(parents=True)
	
	manage_py = base_dir / 'manage.py'
	if create_cache_table:
		LOGGER.info('Creating the cache table')
		virtual_env(str(manage_py), 'createcachetable', '--settings=test_site.local_settings', env=environ |environment_content)
	
	LOGGER.info('Applying migrations')
	virtual_env(str(manage_py), 'migrate', '--settings=test_site.local_settings', env=environ |environment_content)
	
	result = [
		'######################################################################',
		'',
		'You can run this again with:',
		'',
		'env DJANGO_DEBUG=true `./venv/bin/python -m env_pipes vars_from_file --uppercase_vars {secret_files}` ./venv/bin/python ./test_site/manage.py runserver --settings=test_site.local_settings'.format
			(secret_files=' '.join([str(s) for s in secret_json_files_paths])),
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
		
		if (name == 'venv') or (name == 'project_toml'):
			venv, project_toml = deploy_local_venv()
			if name == 'venv':
				value = venv
				self.__setattr__('project_toml', project_toml)
			else:
				value = project_toml
				self.__setattr__('venv', venv)
		elif name == 'base_dir':
			value = self.parent_dir / self.site_name
		else:
			raise AttributeError(name)
		
		self.__setattr__(name, value)
		return value
	
	def __init__(self, site_name, project_dir=Path.cwd(), parent_dir=Path.cwd(),
				 virtual_environment_project_toml=(None, None)):
		"""
		Magic initiation

		:param str site_name: the site name, the only required value
		:returns None: init shouldn't return
		"""
		
		self.site_name = site_name
		self.project_dir = Path(project_dir)
		self.parent_dir = Path(parent_dir)
		virtual_environment, project_toml = virtual_environment_project_toml
		if (virtual_environment is not None) and (project_toml is not None):
			self.venv = virtual_environment
			self.project_toml = project_toml
	
	def _relative_to_project(self, path):
		"""

		"""
		
		path = Path(path)
		if self.project_dir in path.parents:
			return Path('.').joinpath('..' * (path.parents.index(self.project_dir) + 1)) / path.name
		else:
			return (self.project_dir / path.name).absolute
	
	def start(self, overwrite=True):
		"""
		Start the Django project
		Runs the basic "django-admin startproject" and also links the related files
		"""
		
		if overwrite and self.base_dir.exist():
			LOGGER.info('Deleting current site: %s', self.base_dir)
			rmtree(self.base_dir)
		
		LOGGER.info('Creating new site: %s', self.site_name)
		self.venv('startproject', self.site_name, program='django-admin', cwd=self.parent_dir)
		
		if ('tool' in self.pyproject_toml) and ('setuptools' in self.pyproject_toml['tool']) and (
				'packages' in self.pyproject_toml['tool']['setuptools']) and (
				'find' in self.pyproject_toml['tool']['setuptools']['packages']) and (
				'include' in self.pyproject_toml['tool']['setuptools']['packages']['find']):
			for pattern in self.pyproject_toml['tool']['setuptools']['packages']['find']['include']:
				for resulting_path in self.project_dir.glob(pattern):
					base_content = self.base_dir / resulting_path.name
					content_from_base = self._relative_to_project(base_content)
					LOGGER.info('Linking module content: %s -> %s', base_content, content_from_base)
					base_content.symlink_to(content_from_base)