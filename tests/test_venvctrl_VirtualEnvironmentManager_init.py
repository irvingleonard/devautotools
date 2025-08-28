#!python
"""
Testing the VirtualEnvironmentManager.__init__ method
"""

from pathlib import Path
from unittest import TestCase
from shutil import rmtree
from sys import version_info

from devautotools import VirtualEnvironmentManager


class VirtualEnvironmentManagerInitTest(TestCase):
	"""
	Tests for the VirtualEnvironmentManager.__init__ method
	"""

	VENV_DIRECTORY_NAME = 'test_venv_safe_to_delete'

	def test_with_directory(self):
		"""
		Test that we got a working python binary available
		"""

		venv = VirtualEnvironmentManager(self.VENV_DIRECTORY_NAME)
		self.assertTrue((Path.cwd() / self.VENV_DIRECTORY_NAME).exists())
