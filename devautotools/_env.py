#!python
"""Environmental tools
Several tools to handle "env" related functions.
"""

from base64 import b64decode, b64encode
from configparser import ConfigParser
from json import dumps as json_dumps, load as json_load, loads as json_loads
from logging import getLogger
from pathlib import Path
from shlex import quote as shlex_quote

LOGGER = getLogger(__name__)

def env_vars_from_ini(*input_files, sep=' ', uppercase_vars=False):
	"""Env variables from INI files
	Parses INI files containing the variables and prints a line, ready to be fed to "env".
	"""

	result = {}

	for input_file in input_files:
		input_file = Path(input_file)
		if input_file.is_file():
			LOGGER.debug('Working with file: %s', input_file)
		else:
			LOGGER.error('Unable to access file: %s', input_file)

		config = ConfigParser()
		config.optionxform = str
		config.read_file(input_file.open())
		for section, content in config.items():
			LOGGER.debug('Adding settings from section %s', section)
			for key, value in content.items():
				if uppercase_vars:
					key = key.upper()
				result[key] = shlex_quote(str(value))

	return sep.join(['='.join((key, value)) for key, value in result.items()])

def env_vars_from_json(*input_files, sep=' ', uppercase_vars=False):
	"""Env variables from JSON files
	Parses JSON files containing the variables and prints a line, ready to be fed to "env".
	"""

	result = {}

	for input_file in input_files:
		input_file = Path(input_file)
		if input_file.is_file():
			LOGGER.debug('Working with file: %s', input_file)
		else:
			LOGGER.error('Unable to access file: %s', input_file)

		content = json_load(input_file.open())
		for key, value in content.items():
			if isinstance(value, (list, dict)):
				value = json_dumps(value)
			if uppercase_vars:
				key = key.upper()
			result[key] = shlex_quote(str(value))

	return sep.join(['='.join((key, value)) for key, value in result.items()])


def _pack_path(path_to_pack):
	"""Packs a path recursively
	Returns the file content encoded or creates a directory entry (a dict) and calls itself for each child.
	"""

	if path_to_pack.is_dir():
		result = {child_path.name : _pack_path(child_path) for child_path in path_to_pack.iterdir()}
	elif path_to_pack.is_file():
		result = b64encode(path_to_pack.read_bytes()).decode('utf-8')
	else:
		raise ValueError('Not a packable path: {}'.format(path_to_pack))

	return result

def _unpack_path(tree_node, parent_path, overwrite_files = False):
	"""Unpacks a path recursively
	Writes the content of the encoded file or creates a directory and calls itself for each child.
	"""

	parent_path = Path(parent_path)
	if not isinstance(tree_node, dict):
		raise ValueError('Malformed path pack')

	result = []
	for name, content in tree_node.items():
		content_path = parent_path / name
		if isinstance(content, str):
			if content_path.exists() and not overwrite_files:
				raise FileExistsError(str(content_path))
			else:
				content_path.write_bytes(b64decode(content))
				result.append(content_path)
		elif isinstance(content, dict):
			content_path.mkdir(exist_ok = True)
			result.append(content_path)
			result += _unpack_path(content, content_path, overwrite_files)
		else:
			raise ValueError('Malformed path pack')

	return result


class EnvironmentalPipes:
	"""Pipe data via environmental variables
	Several utility tools to handle complex data structures as environmental variables.
	"""

	@staticmethod
	def pack_path(*paths_to_pack, base64_result = False, quote_result = False):
		"""Content in paths as JSON
		Packs the content from the paths provided into a JSON object.
		"""

		result = {}
		for path_to_pack in paths_to_pack:
			target_path = Path(path_to_pack)
			if target_path.exists():
				LOGGER.debug('Working with path: %s', target_path)
			else:
				raise ValueError("The path does not exists or you can't access it: {}".format(target_path))

			result[target_path.name] = _pack_path(target_path)

		result = json_dumps(result)
		if base64_result:
			result = b64encode(result.encode('utf-8')).decode('utf-8')
		if quote_result:
			result = shlex_quote(result)

		return result

	@staticmethod
	def unpack_path(destination, content_file, create_destination = False, overwrite_files = False, base64_decode = False):
		"""Unpack JSON content into a directory
		Unpacks a JSON object created with "pack_path" into a directory
		"""

		destination_path = Path(destination)
		if destination_path.is_dir():
			LOGGER.debug('Working with directory: %s', destination_path)
		elif create_destination:
			if destination_path.exists():
				raise ValueError("Can't create directory on existing path: {}".format(destination_path))
			else:
				LOGGER.debug('Creating directory: %s', destination_path)
				destination_path.mkdir(parents = True)
		else:
			raise ValueError('"{}" is not a directory that you can access'.format(destination))

		if content_file == '-':
			content = input()
			if base64_decode:
				content = b64decode(content.encode('utf-8')).decode('utf-8')
		else:
			content_file_path = Path(content_file)
			try:
				if base64_decode:
					content = b64decode(content_file_path.read_bytes()).decode('utf-8')
				else:
					content = content_file_path.read_text()
			except Exception as error:
				raise RuntimeError('An error ocurred while reading the content file')

		content = json_loads(content)
		result = _unpack_path(content, destination_path, overwrite_files)

		return result
