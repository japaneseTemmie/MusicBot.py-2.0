from helpers.iohelpers import open_file, write_file
from init.logutils import log, separator

from copy import deepcopy
from os.path import join, exists
from sys import exit as sysexit
from time import sleep
from typing import NoReturn, Any, Optional

def get_default_yt_dlp_config_data() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_playlist": True,
        "format": "bestaudio/best",
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
        "default_status": None,
        "enable_file_backups": True,
        "enable_logging": True,
        "log_level": "normal",
        "use_sharding": False
    }

def get_default_modules_config_data() -> dict[str, bool]:
    return {
        "enable_ModerationCog": True,
        "enable_RolesCog": True,
        "enable_UtilsCog": True,
        "enable_MusicCog": True,
        "enable_PlaylistCog": True,
        "enable_VoiceCog": True,
        "enable_DevCog": True,
        "enable_MyCog": False
    }

def get_default_config_data() -> dict[str, Any]:
    config = {
        "yt_dlp_options": get_default_yt_dlp_config_data(),
    }
    config.update(get_other_default_config_data())
    config.update(get_default_modules_config_data())

    return config

def get_expected_modules() -> tuple[list[Optional[str]], list[Optional[str]]]:
    """ Get a tuple of lists containing default enabled and disabled modules. """
    
    enabled, disabled = [], []

    for k, v in get_default_modules_config_data().items():
        enabled.append(k) if v else disabled.append(k)

    return enabled, disabled

def add_other_missing_settings_to_config(config: dict[str, Any], expected_settings: dict[str, Any]) -> None:
    """ Compares the `expected_settings` keys with `config`'s keys and replaces missing ones with default ones. """
    
    for key in expected_settings:
        if key not in config:
            config[key] = expected_settings[key]

def add_missing_modules_to_config(config: dict[str, Any], expected_enabled_modules: list[str], expected_disabled_modules: list[str]) -> None:
    """ Compares the module-related keys in `config` with given `expected_enabled_modules` and `expected_disabled_modules`, if a key is missing, it'll add it accordingly. """
    
    for module_name in expected_enabled_modules:
        if module_name not in config:
            config[module_name] = True

    for module_name in expected_disabled_modules:
        if module_name not in config:
            config[module_name] = False

def add_missing_yt_dlp_options_to_config(config: dict[str, Any], expected_yt_dlp_options: dict[str, Any]) -> None:
    """ Compares the `expected_yt_dlp_config` keys with `config`'s `yt_dlp_options`'s keys and replaces missing keys with default ones. """

    if "yt_dlp_options" not in config:
        config["yt_dlp_options"] = expected_yt_dlp_options
        return

    for key in expected_yt_dlp_options:
        if key not in config["yt_dlp_options"]:
            config["yt_dlp_options"][key] = expected_yt_dlp_options[key]

def check_config(config: dict[str, Any]) -> dict | None:
    """ Checks if config file has any missing keys. If so, adds them with default values. """
    
    orig_config = deepcopy(config)
    expected_yt_dlp_options = get_default_yt_dlp_config_data()
    expected_other_settings = get_other_default_config_data()

    expected_enabled_modules, expected_disabled_modules = get_expected_modules()

    add_missing_yt_dlp_options_to_config(config, expected_yt_dlp_options)
    add_other_missing_settings_to_config(config, expected_other_settings)
    add_missing_modules_to_config(config, expected_enabled_modules, expected_disabled_modules)

    if config != orig_config:
        return config
    
    return None

def ensure_config(path: str, default_data: dict[str, Any]) -> dict | NoReturn:
    """ Checks if config file exists. If not, creates a new one with default settings.
    
    Also checks the output content for missing keys and applies the default key if missing. """
    
    if not exists(path):
        log(f"Creating config file because config.json does not exist at {path}")
        success = write_file(path, default_data, True)

        if success == False:
            sysexit(1)

        log(f"Created config file at {path}")

    log(f"Config file found at {path}")
    
    content = open_file(path, True)

    if content is None:
        sysexit(1)

    log(f"Found {len(content.keys())} entries in {path}")
    separator()

    log("Checking config file..")
    sleep(0.5)
    new_content = check_config(content)

    if new_content is not None:
        log("Updating config file..")
        sleep(0.5)
        write_file(path, new_content, True)
    else:
        log("Config file is up to date.")
    separator()

    return content

def get_config_data(dir: str) -> dict | NoReturn:
    """ Return a hashmap of the `config.json` file.
     
    This function also ensures that there are no missing keys and file exists. """
    
    path = join(dir, "config.json")
    default_data = get_default_config_data()

    return ensure_config(path, default_data)
