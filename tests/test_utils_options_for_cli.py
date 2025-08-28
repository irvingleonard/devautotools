#!python
"""
Testing the _utils.options_for_cli function
"""

from unittest import TestCase

from devautotools._utils import options_for_cli

class OptionsForCLITest(TestCase):
	"""
	Tests for the _utils.options_for_cli function
	"""

	def test_empty(self):
		"""
		Testing "_utils.options_for_cli" function without options
		"""

		input_args = {}
		expected_result = []
		self.assertEqual(expected_result, options_for_cli(input_args))

	def test_simple_flag(self):
		"""
		Testing "_utils.options_for_cli" function with a simple flag
		"""

		input_args  = {'f' : True}
		expected_result = ['-f']
		self.assertEqual(expected_result, options_for_cli(input_args))

	def test_long_flag(self):
		"""
		Testing "_utils.options_for_cli" function with a long flag
		"""

		input_args = {'foo' : True}
		expected_result = ['--foo']
		self.assertEqual(expected_result, options_for_cli(input_args))

	def test_simple_value(self):
		"""
		Testing "_utils.options_for_cli" function with a simple value
		"""

		input_args = {'h' : 'spam'}
		expected_result = ['-h', 'spam']
		self.assertEqual(expected_result, options_for_cli(input_args))

	def test_long_value(self):
		"""
		Testing "_utils.options_for_cli" function with a long value
		"""

		input_args = {'ham' : 'spam'}
		expected_result = ['--ham', 'spam']
		self.assertEqual(expected_result, options_for_cli(input_args))

	def test_multiple_values(self):
		"""
		Testing "_utils.options_for_cli" function with multiple values
		"""

		input_args = {
			'f' : True,
			'foo' : 'eggs',
			'ham' : 'spam',
			'h'	: True,
		}
		expected_result = ['-f', '--foo', 'eggs', '--ham', 'spam', '-h']
		self.assertEqual(expected_result, options_for_cli(input_args))

	def test_sanitize_keys(self):
		"""
		Testing "_utils.options_for_cli" function with key sanitization
		"""

		input_args = {'ham_eggs-spam' : 'foo_bar'}
		expected_result = ['--ham-eggs-spam', 'foo_bar']
		self.assertEqual(expected_result, options_for_cli(input_args, sanitize_keys=True))