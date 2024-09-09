#!python
"""Developers automated tools
Several tools to automate development related tasks.
"""

from json import loads as json_loads
from logging import getLogger
from os import environ
from pathlib import Path
from subprocess import run
from sys import executable, stderr
from webbrowser import open as webbrowser_open

from tomli import load as tomli_load

__version__ = '0.0.9'

LOGGER = getLogger(__name__)

DEFAULT_EXTRA_ENV_VARIABLES = {
	'DJANGO_DEBUG': 'true',
	'DJANGO_LOG_LEVEL': 'debug',
	'PORT': '8080',
}


def deploy_local_venv(system_site_packages=False):
	"""Deploy a local virtual environment
	Based on the current working directory, creates a python3 virtual environment (of the default python 3 on the system) on "./venv/" and populates it with the dependencies described on the "./pyproject.toml" file.
	"""
	
	current_directory = Path.cwd()
	
	venv_dir = current_directory / 'venv'
	if venv_dir in Path(executable).parents:
		raise RuntimeError("You can't run this command from your virtual environment")
	
	if venv_dir.exists():
		LOGGER.info('Cleaning up existing "venv" directory: %s', venv_dir)
		run(('rm', '-rfv', str(venv_dir)), stdout=stderr)
	
	venv_extra_params = []
	if system_site_packages:
		venv_extra_params.append('--system-site-packages')
	
	LOGGER.info('Creating new "venv"')
	run(('python3', '-m', 'venv', 'venv') + tuple(venv_extra_params), stdout=stderr)
	
	LOGGER.info('Upgrading pip')
	run((str(venv_dir / 'bin' / 'pip'), 'install', '--upgrade', 'pip'), stdout=stderr)
	
	pyproject_toml_path = current_directory / 'pyproject.toml'
	
	if not pyproject_toml_path.exists():
		raise RuntimeError('Missing "{}" file'.format(pyproject_toml_path))
	
	with pyproject_toml_path.open('rb') as pyproject_toml_f:
		pyproject_toml = tomli_load(pyproject_toml_f)
	
	if ('build-system' in pyproject_toml) and ('requires' in pyproject_toml['build-system']):
		LOGGER.info('Installing build related modules')
		run((str(venv_dir / 'bin' / 'pip'), 'install', *pyproject_toml['build-system']['requires']), stdout=stderr)
	
	if ('project' in pyproject_toml) and ('dependencies' in pyproject_toml['project']):
		LOGGER.info('Installing dependencies')
		run((str(venv_dir / 'bin' / 'pip'), 'install', *pyproject_toml['project']['dependencies']), stdout=stderr)
	
	if ('project' in pyproject_toml) and ('optional-dependencies' in pyproject_toml['project']):
		for section, modules in pyproject_toml['project']['optional-dependencies'].items():
			LOGGER.info('Installing optional dependencies: %s', section)
			run((str(venv_dir / 'bin' / 'pip'), 'install', *modules), stdout=stderr)
	
	return pyproject_toml


def deploy_local_django_site(*secret_json_files_paths, system_site_packages=False, django_site_name='test_site', superuser_password='', just_build=False):
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
	
	pyproject_toml = deploy_local_venv(system_site_packages=system_site_packages)
	current_directory = Path.cwd()
	base_dir = current_directory / django_site_name
	site_dir = base_dir / django_site_name
	venv_dir = current_directory / 'venv'
	root_from_site = Path('..') / '..'
	
	LOGGER.info('Removing test site directory: %s', base_dir)
	run(('rm', '-rfv', str(base_dir)), stdout=stderr)
	
	LOGGER.info('Creating a new test site')
	run((venv_dir / 'bin' / 'django-admin', 'startproject', django_site_name), stdout=stderr)
	
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
	run((str(venv_dir / 'bin' / 'python'), str(manage_py), 'createcachetable', '--settings=test_site.local_settings'),
		env=environ | environment_content)
	LOGGER.info('Applying migrations')
	run((str(venv_dir / 'bin' / 'python'), str(manage_py), 'migrate', '--settings=test_site.local_settings'),
		env=environ | environment_content)
	
	result = [
		'######################################################################',
		'',
		'You can run this again with:',
		'',
		'env DJANGO_DEBUG=true `./venv/bin/python -m env_pipes vars_from_file --uppercase_vars {secret_files}` ./venv/bin/python ./test_site/manage.py runserver --settings=test_site.local_settings'.format(
			secret_files=' '.join([str(s) for s in secret_json_files_paths])),
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
		run((str(venv_dir / 'bin' / 'python'), str(manage_py), 'createsuperuser', '--noinput',
			 '--settings=test_site.local_settings'), env=environ | environment_content | super_user_details)
		
		result += [
			'Then go to http://localhost:8000/admin and use credentials {user}:{password}'.format(user=current_user,
																								  password=superuser_password),
			'',
		]
	
	LOGGER.info('\n'.join(result + ['######################################################################']))
	
	if not just_build:
		webbrowser_open('http://localhost:8000/admin')
		return run(
			(str(venv_dir / 'bin' / 'python'), str(manage_py), 'runserver', '--settings=test_site.local_settings'),
			env=environ | environment_content | {'DJANGO_DEBUG': 'true'})


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
