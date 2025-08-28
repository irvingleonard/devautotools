#!python
"""Developers automated tools (Docker)
Several tools to automate Docker related tasks.
"""

from json import loads as json_loads
from logging import getLogger
from os import environ
from pathlib import Path
from subprocess import run

DEFAULT_EXTRA_ENV_VARIABLES = {
	'DJANGO_DEBUG': 'true',
	'DJANGO_LOG_LEVEL': 'debug',
	'PORT': '8080',
}
LOGGER = getLogger(__name__)

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