""" Config helper module for discord.py bot """

from helpers.iohelpers import read_file_json, write_file_json
from init.logutils import log, separator

from typing import Any, Type
from copy import deepcopy
from os.path import join, exists
from time import sleep

# Small helpers
def correct_type(value: Any, expected: Type, default: Any) -> Any:
    """ Correct a config value type. 

    Return corrected value. """

    if isinstance(value, expected):
        return value
    
    return default

def correct_value_in(value: Any, allowed: tuple[Any, ...], default: Any) -> Any:
    """ Correct a config value given an 'allowlist' 
    
    Return corrected value. """

    if value in allowed:
        return value
    
    return default

# Defaults
def get_default_yt_dlp_config_data() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_playlist": True,
        "format": "bestaudio[ext=m4a]/bestaudio",
        "no_warnings": True,
        "getcomments": False,
        "writeautomaticsub": False,
        "writesubtitles": False,
        "listsubtitles": False
    }

def get_other_default_config_data() -> dict[str, Any]:
    return {
        "command_prefix": "?",
        "enable_activity": False,
        "activity_name": "with the API",
        "activity_type": "playing",
        "activity_state": "In Discord",
        "status_type": None,
        "enable_file_backups": True,
        "enable_logging": True,
        "log_level": "normal",
        "use_sharding": False,
        "auto_delete_unused_guild_data": True,
        "max_queue_track_limit": 100,
        "max_track_history_limit": 200,
        "max_query_limit": 25,
        "max_playlist_limit": 10,
        "max_playlist_track_limit": 100,
        "max_playlist_name_length": 50
    }

def get_default_modules_config_data() -> dict[str, bool]:
    return {
        "enable_ModerationCog": True,
        "enable_RolesCog": True,
        "enable_UtilsCog": True,
        "enable_MusicCog": True,
        "enable_PlaylistCog": True,
        "enable_VoiceCog": True,
        "enable_MyCog": False
    }

def get_default_config_data() -> dict[str, Any]:
    config = {
        "yt_dlp_options": get_default_yt_dlp_config_data(),
    }
    config.update(get_other_default_config_data())
    config.update(get_default_modules_config_data())

    return config

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
