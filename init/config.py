""" Config helper module for discord.py bot """

from helpers.iohelpers import read_file_json, write_file_json
from helpers.confighelpers import get_default_config_data
from init.logutils import log, separator

from typing import Any
from copy import deepcopy
from os.path import join, exists
from time import sleep

# Config manipulation
def add_to_config(data: dict[str, Any], defaults: dict[str, Any]) -> None:
    """ Compare `defaults`' keys with `data`'s keys and if any are missing, add them accordingly. """

    for key, value in defaults.items():
        if key not in data:
            data[key] = value
        elif isinstance(value, dict):
            add_to_config(data[key], defaults[key])

def add_missing_settings(config: dict[str, Any]) -> None:
    """ Check config and compare it to default settings, if any keys are missing, add them accordingly. """

    default = get_default_config_data()

    # Check if keys are missing
    add_to_config(config, default)

def check_config(config: dict[str, Any]) -> dict[str, Any] | None:
    """ Checks if config file has any missing keys. If so, adds them with default values. """
    
    orig_config = deepcopy(config)

    add_missing_settings(config)

    if config != orig_config:
        return config
    
    return None

def ensure_config(path: str, default_data: dict[str, Any]) -> dict[str, Any] | None:
    """ Checks if config file exists. If not, creates a new one with default settings.
    
    Also checks the output content for missing keys and applies the default key if missing. """
    
    if not exists(path):
        log(f"Creating config file because config.json does not exist at {path}")
        result = write_file_json(path, default_data)

        if result == False:
            return None

        log(f"Created config file at {path}")

    log(f"Config file found at {path}")
    
    content = read_file_json(path)

    if content is None:
        return None

    log(f"Found {len(content.keys())} entries in {path}")
    separator()

    log("Checking config file..")
    sleep(0.5)
    new_content = check_config(content)

    if new_content is not None:
        log("Updating config file..")
        sleep(0.5)

        result = write_file_json(path, new_content)
        if result == False:
            log("Failed to update config file contents.")
        else:
            content = new_content
    else:
        log("Config file is up to date.")
    separator()

    return content

def get_config_data(dir: str) -> dict[str, Any] | None:
    """ Return a hashmap of the `config.json` file.
     
    This function also ensures that there are no missing keys and file exists. """
    
    path = join(dir, "config.json")
    default_data = get_default_config_data()

    return ensure_config(path, default_data)
