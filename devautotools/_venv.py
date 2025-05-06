#!python
"""Virtual environments
Some helper functionality around virtual environments.
"""

from logging import getLogger
from pathlib import Path

from tomli import load as tomli_load

from ._venvctrl import VirtualEnvironmentManager

LOGGER = getLogger(__name__)

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