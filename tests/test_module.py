#!python
"""
Testing the whole module
"""

from unittest import TestCase

import devautotools

class ModuleTest(TestCase):
    """
    Tests for the module
    """
    def test_dummy(self):
        """
        Dummy test, checking for correct syntax
        """

        devautotools
        self.assertEqual(True, True)  # add assertion here
