#!python
"""Miscellaneous utility functions for the devautotools package.

This module provides helper functions that are used across the package,
primarily for tasks related to command-line interface (CLI) generation
and other common operations.
"""

def options_for_cli(options={}, /, sanitize_keys=False):
	"""Convert keyword arguments to a list of command-line options.

	:param options: Keyword arguments where the key is the option name and the value is the option's value.
	:type options: dict
	:return: A list of strings representing the command-line options.
	:rtype: list[str]
	"""

	cli_content = []
	for option, value in options.items():
		if len(option) == 1:
			option = f'-{option}'
		else:
			if sanitize_keys:
				option = option.replace("_", "-")
			option = f'--{option}'
		if not isinstance(value, bool):
			cli_content += [option, value]
		elif value:
			cli_content.append(option)
	return cli_content
