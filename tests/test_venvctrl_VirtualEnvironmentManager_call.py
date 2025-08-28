#!python
"""
Testing the VirtualEnvironmentManager class
"""

from pathlib import Path
from unittest import TestCase
from shutil import rmtree
from sys import version_info

from devautotools import VirtualEnvironmentManager

class VirtualEnvironmentManagerTest(TestCase):
    """
    Tests with a regular directory
    """
    
    VENV_DIRECTORY_NAME = 'test_venv_safe_to_delete'
    
    @classmethod
    def setUpClass(cls):
        """
        Set up the virtual environment on a local directory
        """
        
        cls.venv = VirtualEnvironmentManager(cls.VENV_DIRECTORY_NAME)
    
    @classmethod
    def tearDownClass(cls):
        """
        Delete the virtual environment
        """
        
        rmtree(Path.cwd() / cls.VENV_DIRECTORY_NAME)
        
    def test_python_version(self):
        """
        Test that we got a working python binary available
        """
        
        self.assertEqual('Python {}.{}.{}\n'.format(*version_info[:3]), self.venv('--version', capture_output=True).stdout)


class TempVirtualEnvironmentManagerTest(TestCase):
    """
    Tests with a regular directory
    """
    
    @classmethod
    def setUpClass(cls):
        """
        Setup the virtual environment on a local directory
        """
        
        cls.venv = VirtualEnvironmentManager(None)
    
    def test_python_version(self):
        """
        Test that we got a working python binary available
        """
        
        self.assertEqual('Python {}.{}.{}\n'.format(*version_info[:3]), self.venv('--version', capture_output=True).stdout)