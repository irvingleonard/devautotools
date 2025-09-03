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

# Normalized Django settings system

This module proposes a normalized system to handle Django settings by loading from the environment. 

## The settings module

There should be a settings module (that could be named anything you want) which should contain several things. Generally you'll create a `settings.py` file in your app and fill it with something like:
```
#You should probably check these functions' documentation (these are completely optional)
from devautotools import path_for_setting, setting_is_true

#...

#Check the EXPECTED_VALUES_FROM_ENV section to learn how to populate this dict. Example content could be
#EXPECTED_VALUES_FROM_ENV = {
#    'EXAMPLE_SECTION': {
#        'FOO',
#        'IS_BAR',
#        'SPAM',
#    }
#    'OMELETTE_SECTION': {
#        'EGGS',
#        'HAM',
#    }
#}
EXPECTED_VALUES_FROM_ENV = {}

#Check the IMPLICIT_ENVIRONMENTAL_SETTINGS section to learn how to populate this dict. Example content could be
#IMPLICIT_ENVIRONMENTAL_SETTINGS = {
#    'FOO': 'omelette',
#    'IS_BAR': 'yes',
#}
IMPLICIT_ENVIRONMENTAL_SETTINGS = {}

#...

def normalized_settings(**django_settings):
	
	#Your configuration logic goes here
	pass
```

### EXPECTED_VALUES_FROM_ENV

This is a dictionary of `section: {names}` where each "name" would be a variable to be captured from the environment. The structure for the expected values is:
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
The section can be named in any way you want but a good naming convention should be used to avoid collisions when merging different modules.

The sections enable you to handle multiple settings at a time, simplifying the group check with the use of set logic against the list of all the loaded settings (which should live in `ENVIRONMENTAL_SETTINGS_KEYS`). Ex: let's say that some settings `foo_user` and `foo_password` can be provided to enable some functionality `foo`, but it only makes sense if both are provided together (providing only one wouldn't work). In such case you could do:
```
EXPECTED_VALUES_FROM_ENV = {
    'FOO' : {
        'foo_user',
        'foo_password',
    }
}

#...

#Then in your "normalized_settings" function you could do
if EXPECTED_VALUES_FROM_ENV['FOO'].issubset(ENVIRONMENTAL_SETTINGS_KEYS):
    #configure foo
else:
    warn('foo is not configured')
```

### IMPLICIT_ENVIRONMENTAL_SETTINGS

This is a constant that can be used to provide "default" values to any environmental variable. It's a simple dictionary having `name: value` which will be added to the captured values during the processing. Ex:
```
IMPLICIT_ENVIRONMENTAL_SETTINGS = {
  'FOO_BAR' : 'this or that',
  'spam': 'no: ham & eggs',
  'DJANGO_LOG_LEVEL': 'debug',
}
```
You can use it to provide default values across apps (modules). Ex: app `bar` can set a default for a variable used by app `foo`.

### normalized_settings(**django_settings)

This is a function able to "process" the settings for the app in question. It should know about all the sections and produce the expected values based on the provided variables. It must return the updated `django_settings`. Ex:
```
if 'FOO' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
    django_settings['foo'] = django_settings['ENVIRONMENTAL_SETTINGS']['FOO']

#You can leverage "setting_is_true" for booleans
if 'IS_BAR' in django_settings['ENVIRONMENTAL_SETTINGS_KEYS']:
    django_settings['is_bar'] = setting_is_true(django_settings['ENVIRONMENTAL_SETTINGS']['IS_BAR'])

#The "path_for_setting" function is available for settings expecting a path (you can provide the content too; check the function's documentation for details)
spam = path_for_setting(django_settings, 'SPAM')
if spam is not None:
    django_settings['spam'] = spam

#You can also use your sections and django_settings['ENVIRONMENTAL_SETTINGS_KEYS'] to handle multiple settings at a time.
if EXPECTED_VALUES_FROM_ENV['OMELETTE_SECTION'].issubset(django_settings['ENVIRONMENTAL_SETTINGS_KEYS']):
    django_settings['ham_omelette'] = (django_settings['ENVIRONMENTAL_SETTINGS']['EGGS'], django_settings['ENVIRONMENTAL_SETTINGS']['HAM'])

return django_settings
```
You shouldn't pull defaults directly in this function, something like `django_settings['foo'] = django_settings['ENVIRONMENTAL_SETTINGS'].get('FOO', 'spam')` is not good, you should instead use the [`IMPLICIT_ENVIRONMENTAL_SETTINGS`](#IMPLICIT_ENVIRONMENTAL_SETTINGS) constant:
```
IMPLICIT_ENVIRONMENTAL_SETTINGS = {
  'FOO': 'spam',
}
```
This allows every `normalized_settings` function to "know" about the default value for each variable.

## django_normalized_settings(*settings_module_names, django_settings, loose_list=True)

In your Django site's settings you should trigger the system by calling this function. It's usually used as:
```
from devautotools import django_normalized_settings

#...

settings_module_names = (
    'devautotools',
    'foo.settings',
    'bar.settings',
)
global_state = globals()
global_state |= django_normalized_settings(*settings_module_names, django_settings=globals())
```
Each value in `settings_module_names` should be an importable module potentially containing `EXPECTED_VALUES_FROM_ENV`, `IMPLICIT_ENVIRONMENTAL_SETTINGS`, and/or `common_settings`.

The `loose_list` parameter can be set to avoid aborting the execution if any of the modules fails to load; it will generate an exception log instead and continue the execution.

It will leverage [`django_settings_env_capture`](#django_settings_env_captureexpected_sections) to load the variables from the environment and its rules apply.

## Utility functions

These are some functions that you can leverage on your `normalized_settings`' logic.

### setting_is_true(value)

It compares the provided string (`value`) to the known "true" values (in the `TRUTH_LOWERCASE_STRING_VALUES` constant) in a case-insensitive way and returns and actual boolean.

### path_for_setting(django_settings, env_var_name, lowercase=False)

Given an environment variable name, find the correct value for the corresponding setting. The logic is:

1. if the env_var_name is found, it's returned as is. This is usually the case when the file is managed outside and the path is provided to Django.
2. if env_var_name + "_CONTENT" is found (ex: FOO_CONTENT) then the content of the variable is written to a temporary file and the path to such file is returned.
3. if env_var_name + "_BASE64" is found (ex: FOO_BASE64) then the content of the variable is base64 decoded, then written to a temporary file, and the path to such file is returned. You can provide binary content using this method but keep in mind the buffer limits of your operating system.

The file is created using [mkstemp](https://docs.python.org/3/library/tempfile.html#tempfile.mkstemp) and any related limitations or security considerations apply. The file is automatically removed when the Python interpreter ends using [atexit](https://docs.python.org/3/library/atexit.html) + [os.remove](https://docs.python.org/3/library/os.html#os.remove).

The `lowercase` parameter, if provided, makes the function create the `env_var_name`'s variations with the suffixes in lowercase (instead of the default uppercase).

## Local normalized_settings

This module provides its own version of `normalized_settings` that covers very basic Django settings for your convenience.

It requires the value of `BASE_DIR` to be set:
- If you extend the builtin/autogenerated `settings.py` by doing `from settings import *` in your custom settings module (with a different name than `settings`) or simply adding more values to the original `settings.py`, then you don't have to worry about this, Django already sets the value.
- If you start your own `settings.py` from scratch, please set such value to the directory containing the site.

**_Settings requiring booleans are retrieved via [`setting_is_true`](#setting_is_truevalue)._**

**_Settings requiring paths are retrieved via [`path_for_setting`](#path_for_settingdjango_settings-env_var_name-lowercasefalse)._**

The supported settings include:
- the `DEBUG` value, a boolean, will be loaded from the `DJANGO_DEBUG` environmental variable. It will be set to `False` by default.
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
- the database values could be supplied while prefixed with `DJANGO_DATABASE_` otherwise the builtin database (SQlite) will be used. Database `OPTIONS` should be prefixed with `DJANGO_DATABASE_OPTIONS_` which are all tried to resolve as paths and expected to be lowercase (ex: `DJANGO_DATABASE_OPTIONS_foo`, `DJANGO_DATABASE_OPTIONS_bar_content`).
- Some email options are simply used as is: [`DJANGO_EMAIL_BACKEND`](https://docs.djangoproject.com/en/stable/ref/settings/#email-backend), [`DJANGO_EMAIL_HOST`](https://docs.djangoproject.com/en/stable/ref/settings/#email-host), [`DJANGO_EMAIL_FILE_PATH`](https://docs.djangoproject.com/en/stable/ref/settings/#email-file-path), [`DJANGO_EMAIL_HOST_USER`](https://docs.djangoproject.com/en/stable/ref/settings/#email-host-user), [`DJANGO_EMAIL_HOST_PASSWORD`](https://docs.djangoproject.com/en/stable/ref/settings/#email-host-password), and [`DJANGO_EMAIL_SUBJECT_PREFIX`](https://docs.djangoproject.com/en/stable/ref/settings/#email-subject-prefix).
- There's a distinction in Django's email system between system and user emails. To account for that, there are two settings to set the "From:" value: [`DJANGO_SERVER_EMAIL`](https://docs.djangoproject.com/en/stable/ref/settings/#server-email) and [`DJANGO_DEFAULT_FROM_EMAIL`](https://docs.djangoproject.com/en/stable/ref/settings/#default-from-email). If both values are provided then each will go to the corresponding setting. If only one is provided, then both settings will be populated with that value.
- Some email options are converted to integers: [`DJANGO_EMAIL_PORT`](https://docs.djangoproject.com/en/stable/ref/settings/#email-port) and [`DJANGO_EMAIL_TIMEOUT`](https://docs.djangoproject.com/en/stable/ref/settings/#email-timeout)
- For the email connection SSL settings, you need to provide either [`DJANGO_EMAIL_USE_SSL`](https://docs.djangoproject.com/en/stable/ref/settings/#email-use-ssl) or [`DJANGO_EMAIL_USE_TLS`](https://docs.djangoproject.com/en/stable/ref/settings/#email-use-tls), which are boolean values. The former is preferred if you provide both (in that case `DJANGO_EMAIL_USE_TLS` will be ignored).
- For email connection using certificate authentication you should provide [`DJANGO_EMAIL_SSL_CERTFILE`](https://docs.djangoproject.com/en/stable/ref/settings/#email-ssl-certfile) and [`DJANGO_EMAIL_SSL_KEYFILE`](https://docs.djangoproject.com/en/stable/ref/settings/#email-ssl-keyfile) which are treated as paths.
- The email addresses of admins and managers are provided via [`DJANGO_ADMINS`](https://docs.djangoproject.com/en/stable/ref/settings/#admins) and [`DJANGO_MANAGERS`](https://docs.djangoproject.com/en/stable/ref/settings/#managers). Its content is parsed using [`getaddresses`](https://docs.python.org/3/library/email.utils.html#email.utils.getaddresses). If both values are provided then each will go to the corresponding setting. If only one is provided, then both settings will be populated with that value.

All the variables that this function consumes are prefixed with `DJANGO_` which means that it doesn't require entries in `EXPECTED_VALUES_FROM_ENV`.

## django_settings_env_capture(**expected_sections)

This is an internal utilitarian function that will scan the environmental variables and pick the ones described in the `expected_sections` parameter or anything that starts with `DJANGO_`.

If you start the section name with `required_` or end it with `_required` (case-insensitive) they will be considered a requirement and failure to load all its variables from the environment will raise a `RuntimeError`. Variable names will be used "as is" to pull the variable from the environment (watch the case, no conversion is done). It will generate a warning for all the variables in the `expected_sections` that it couldn't find. The result will be a dict of `variable_name: variable_value`.
