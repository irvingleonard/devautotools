# devautotools

This module contains a diverse collection of functionalities to make python devs' work easier (hopefully). Most of them are very opinionated so they might not work for you, but if you're ok with the values used, or don't care, it might save you some time. This is a command line based tool, so, feel free to `--help` yourself around. This document assumes that you have the module installed in `~/venv` which could be accomplished with:
```
python3 -m venv ~/venv
~/venv/bin/python -m pip install --upgrade pip
~/venv/bin/pip install devautotools
```
The Windows version would use `~/venv/Scripts/python.exe` and `~/venv/Scripts/pip.exe` instead.

## deploy_local_venv

There are many ways of managing virtual environments and several tools for that. Here we assume that you're not using any of those, just a `venv/` directory in the root of your project. This function will re-create such environment based on the OS default python 3 and install ALL the dependencies. It works solely with projects that use `pyproject.toml` files. It will fail if the dependencies are handled on `setup.py`, the old way of doing so. You can use the supplied options to change the way the `env` command is called or the way `pip install` is run. It would work as simple as:
```
~/venv/bin/python -m devautotools deploy_local_venv
```
(remember that this will affect the current working directory)

## deploy_local_django_site

For when you're working on a Django app and just creating the virtual environment with the dependencies is not enough. It does start with the virtual environment, by leveraging [deploy_local_venv](#deploy_local_venv), but also creates a `test_site` which uses symlinks to the app and everything else required. It will apply the migrations and start the test server. Assuming that you have a `conf/my-settings.json` file with your values, a simple call would be:
```
~/venv/bin/python -m devautotools deploy_local_django_site --superuser_password SuperSecretThing conf/my-settings.json
```
(remember that this will affect the current working directory)

## start_local_docker_container

Assuming you have a `Dockerfile` in the current working directory, this will create the image and run it. The names will be derived from the current working directory. You can provide path to JSON files containing environment variables to send to the container. Such file should be treated as `key: value` attributes (doesn't support deep/complex objects).

## stop_local_docker_container

Would do the opposite of [start_local_docker_container](#start_local_docker_container). It derives the container name from the current working directory so it's a very weak logic.

## env_vars_from_ini

Produces a string of `key="value"` based on the provided `ini` file data, to be used with the `env` command. This can be used to instantiate a container with variables stored on an `ini` file. There's an `uppercase_vars` switch to convert all the keys to uppercase, which is usually what you'll want. The separator (`sep`) parameter can be used to replace the builtin space (` `) separator with anything else. 

## env_vars_from_json

Produces a string of `key="value"` based on the provided `json` file data, to be used with the `env` command. This can be used to instantiate a container with variables stored on a `json` file. It has the same `uppercase_vars` and `sep` parameters, as [`env_vars_from_ini`](#env_vars_from_ini). The values will be cast to string, so, complex structures might be unable to be used this way.

## Normalized Django settings system

This module proposes a normalized system to handle Django settings loading from the environment.

### EXPECTED_VALUES_FROM_ENV

It starts by defining a setting called `EXPECTED_VALUES_FROM_ENV` which is a dictionary of `section: {names}`. The structure for the expected values is:
```
EXPECTED_VALUES_FROM_ENV = {
    THIS_IS_AN_OPTIONAL_SECTION = {
        'OPTIONAL_VARIABLE_1',
        'foo',
        'SPAM',
    },
    another_optional_section = {
        'foo_BAR',
        'HAM_EGGS',
        'spam_spam_spam',
    },
    required_section = {
        'zar_dar',
        'SPAM_SPAM',
        'another_required_variable',
    },
    this_section_is_required = {
        'dar_par',
        'ham_spam',
    }
}
```
The section can be named in any way you want but a good naming convention should be used to avoid collisions when merging different apps.

The sections enable you to handle multiple settings at a time, simplifying the group check with the use of set logic against the list of all the loaded settings (which should live in `ENVIRONMENTAL_SETTINGS_KEYS`).

Ex: let's say that some settings `foo_user` and `foo_password` can be provided to enable some functionality `foo`, but it only makes sense if both are provided together (providing only one wouldn't work). In such case you could do:
```
EXPECTED_VALUES_FROM_ENV = {
    'FOO_OPTIONALS' : {
        'foo_user',
        'foo_password',
    }
}

...

if EXPECTED_VALUES_FROM_ENV['FOO_OPTIONALS'].issubset(ENVIRONMENTAL_SETTINGS_KEYS):
    #configure foo
else:
    warn('foo is not fingured')
```

### django_settings_env_capture(**expected_sections)

Is a utilitarian function that will scan the environmental variables and pick the ones described in the `expected_sections` parameter or anything that starts with `DJANGO_`.

If you start the section name with `required_` or end it with `_required` (case-insensitive) they will be considered a requirement and failure to load all its variables from the environment will raise a `RuntimeError`. Variable names will be used "as is" to pull the variable from the environment (watch the case, no conversion is done). It will generate a warning for all the variables in the `expected_sections` that it couldn't find. The result will be a dict of `variable_name: variable_value`.

### settings.common_settings

The third part of the system is a function able to "process" the settings for the app in question. It should know about all the sections and produce the expected values based on the provided variables.

Generally you'll create a `local_settings.py` file in your app and fill it with something like:
```
#Check the django_settings_env_capture section to understand its behavior
from devautotools import django_settings_env_capture, setting_is_true
#...
#Check the EXPECTED_VALUES_FROM_ENV section to learn how to populate this dict
EXPECTED_VALUES_FROM_ENV = {}
#...
def common_settings(settings_globals, parent_callables=None):
	"""Common values for Django
	Generates Django values for your settings.py file. It's usually added as:

	global_state = globals()
	global_state |= common_settings(globals())

	:param settings_globals: the caller's "globals"
	:param parent_callables: an optional list of parent "common_settings" callables
	:type parent_callables: [callable]|None
	:return: new content for "globals"
	"""

	django_settings = settings_globals.copy()

	if 'EXPECTED_VALUES_FROM_ENV' not in django_settings:
		django_settings['EXPECTED_VALUES_FROM_ENV'] = {}
	django_settings['EXPECTED_VALUES_FROM_ENV'] |= EXPECTED_VALUES_FROM_ENV

	if parent_callables is None:
		if 'ENVIRONMENTAL_SETTINGS' not in django_settings:
			django_settings['ENVIRONMENTAL_SETTINGS'] = {}
		django_settings['ENVIRONMENTAL_SETTINGS'] |= django_settings_env_capture(**EXPECTED_VALUES_FROM_ENV)
		django_settings['ENVIRONMENTAL_SETTINGS_KEYS'] = frozenset(django_settings['ENVIRONMENTAL_SETTINGS'].keys())
	elif parent_callables:
		parent_common_settings = parent_callables.pop(0)
		django_settings = parent_common_settings(django_settings, parent_callables=parent_callables)
	else:
		if 'ENVIRONMENTAL_SETTINGS' not in django_settings:
			django_settings['ENVIRONMENTAL_SETTINGS'] = {}
		django_settings['ENVIRONMENTAL_SETTINGS'] |= django_settings_env_capture(**django_settings['EXPECTED_VALUES_FROM_ENV'])
		django_settings['ENVIRONMENTAL_SETTINGS_KEYS'] = frozenset(django_settings['ENVIRONMENTAL_SETTINGS'].keys())
	
	#Start configuring stuff here, pulling the values from django_settings['ENVIRONMENTAL_SETTINGS'].
	#You can also use your sections and django_settings['ENVIRONMENTAL_SETTINGS_KEYS'] to handle multiple settings at a time.
```
Your configuration code shouldn't edit `EXPECTED_VALUES_FROM_ENV`, `ENVIRONMENTAL_SETTINGS`, or `ENVIRONMENTAL_SETTINGS_KEYS` otherwise it could destroy the ability of the function to work alongside their siblings.

This logic will set `EXPECTED_VALUES_FROM_ENV` to an empty dict if not present. All the values loaded will be added to a dict `ENVIRONMENTAL_SETTINGS` which is initialized if it doesn't exist already. It will also create or re-create a frozenset `ENVIRONMENTAL_SETTINGS_KEYS` out of the `ENVIRONMENTAL_SETTINGS` keys.

Then there are different ways to use this function:

#### Iteratively 

In this case each `common_settings` parses the whole environment by itself looking only for the variables that apply to it. Using multiple of these together is quite straightforward, by making the project's `settings.py` look like this:
```
from devautotools import django_common_settings
from foo.settings import common_settings as foo_common_settings
from bar.settings import common_settings as bar_common_settings

#...

global_state = globals()
global_state |= django_common_settings(globals())
global_state |= foo_common_settings(globals())
global_state |= bar_common_settings(globals())
```
As long as those functions followed the suggested boilerplate code and didn't do any destructive change (like removing stuff from `EXPECTED_VALUES_FROM_ENV`, `ENVIRONMENTAL_SETTINGS`, or `ENVIRONMENTAL_SETTINGS_KEYS`) you should get the same result regardless of the order in which you call them (unless you override values across functions or if you have a collision of `EXPECTED_VALUES_FROM_ENV` sections).

#### Recursively

You could "simplify" the calling via recursion, in which case the environment is only parsed once. This way, each layer adds its sections to `EXPECTED_VALUES_FROM_ENV` until it reaches the deepest one which calls `django_settings_env_capture`. On the way back, each layer process the values in `ENVIRONMENTAL_SETTINGS` and adds its own settings. In this scenario, the project's `settings.py` would look like this:
```
from devautotools import django_common_settings
from foo.settings import common_settings as foo_common_settings
from bar.settings import common_settings as bar_common_settings

#...

global_state = globals()
global_state |= bar_common_settings(globals(), parent_callables=[foo_common_settings,django_common_settings])
```
In this arrangement the execution will occur in the same order as the previous section. It always goes from deep to shallow.

Again, as long as those functions followed the suggested boilerplate code and didn't do any destructive change (like removing stuff from `EXPECTED_VALUES_FROM_ENV`, `ENVIRONMENTAL_SETTINGS`, or `ENVIRONMENTAL_SETTINGS_KEYS`) you should get the same result regardless of the order in which you call them (unless you override values across functions or if you have a collision of `EXPECTED_VALUES_FROM_ENV` sections).

#### Mixed

As long as your `common_settings` functions followed the suggested boilerplate code and didn't do any destructive change (like removing stuff from `EXPECTED_VALUES_FROM_ENV`, `ENVIRONMENTAL_SETTINGS`, or `ENVIRONMENTAL_SETTINGS_KEYS`) you could mix recursive calls with iterative calls safely. The execution order will be important in the case of values overrides across functions or if you have a collision of `EXPECTED_VALUES_FROM_ENV` sections.

### setting_is_true(value)

Utility function that compares the provided string (`value`) to the known "true" values (the `TRUTH_LOWERCASE_STRING_VALUES` constant) in a case-insensitive way and returns and actual boolean.

### django_common_settings

This module provides its own version of `common_settings` that covers very basic Django settings.

It requires the value of `BASE_DIR` to be set:
- If you extend the builtin/autogenerated `settings.py` by doing `from settings import *` in your custom settings module (with a different name than `settings`) or simply adding more values to the original `settings.py`, then you don't have to worry about this, Django already sets the value.
- If you start your own `settings.py` from scratch, please set such value to the directory containing the site.

String to bool conversion is made via [`setting_is_true`](#setting_is_true).

The supported settings include:
- the `DEBUG` value will be loaded from the `DJANGO_DEBUG` environmental variable and cast to bool. It will be set to `False` by default.
- the `DJANGO_LOG_LEVEL` variable will be used to configure the logging system. The logging section will always have the same structure, and it will take the first value in the `POSSIBLE_LOG_LEVELS` constant as the default log level. The structure is
```
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'DEBUG' if django_settings['DEBUG'] else django_log_level,
            'propagate': True,
        },
    },
}
```
- the `STORAGES`, `STATIC_URL`, and `STATIC_ROOT` values are configured with hardcoded values. The function will attempt to create these directories.
  - `default` storage goes to `<BASE_DIR>/storage/media`
  - `staticfiles` storage goes to `<BASE_DIR>/storage/staticfiles`
  - `staticfiles` path is set to `/static/`.
- the database values could be supplied while prefixed with `DJANGO_DATABASE_` otherwise the builtin database (SQlite) will be used. Database `OPTIONS` should be prefixed with `DJANGO_DATABASE_OPTIONS_` and any of the file related options should be suffixed with `_path`, `_base64` or `_content`. The content will be decoded first (in the case of `_base64`) and the copied to a temporary file in the default temp region (check [mkstemp's documentation](https://docs.python.org/3/library/tempfile.html#tempfile.mkstemp)) or simply referenced in the case of `_path`, and used to configure the SSL settings for the database connection (possible option values are set in the `SSL_FILE_OPTIONS` constant).

All the variables that this function consumes are prefixed with `DJANGO_` which means that it doesn't require entries in `EXPECTED_VALUES_FROM_ENV`.