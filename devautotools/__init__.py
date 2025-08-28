#!python
"""Developers automated tools
Several tools to automate development related tasks.
"""

from ._django import deploy_local_django_site, django_common_settings, django_settings_env_capture, setting_is_true, DjangoLinkedSite
from ._docker import start_local_docker_container, stop_local_docker_container
from ._env import env_vars_from_ini, env_vars_from_json, EnvironmentalPipes
from ._venv import deploy_local_venv
from ._venvctrl import VirtualEnvironmentManager

__version__ = '1.0.0'