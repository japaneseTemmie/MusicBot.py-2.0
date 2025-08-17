from copy import deepcopy
from os.path import join, exists
from sys import exit as sysexit
from time import sleep

from iohelpers import open_file, write_file
from init.logutils import log, separator

from typing import NoReturn

def get_default_yt_dlp_config_data() -> dict:
    return {
        "quiet": True,
        "no_playlist": True,
        "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
        "no_warnings": True
    }

def get_default_config_data() -> dict:
    return {
        "yt_dlp_options": get_default_yt_dlp_config_data(),
        "command_prefix": "?",
        "enable_activity": False,
        "activity_name": "with the API",
        "activity_type": "playing",
        "default_status": None,
        "enable_file_backups": True,
        "enable_logging": True,
        "log_level": "normal",
        "use_sharding": False,
        "enable_ModerationCog": True,
        "enable_RoleManagerCog": True,
        "enable_UtilsCog": True,
        "enable_MusicCog": True,
        "enable_MyCog": False
    }

def add_missing_modules_to_config(data: dict, expected_enabled: list[str], expected_disabled: list[str]) -> None:
    for mod in expected_enabled:
        if mod not in data:
            data[mod] = True

    for mod in expected_disabled:
        if mod not in data:
            data[mod] = False

def add_missing_yt_dlp_to_config(data: dict, expected_config: dict) -> None:
    if data["yt_dlp_options"] != expected_config:
        data["yt_dlp_options"] = expected_config

def check_config(data: dict) -> dict | None:
    orig_data = deepcopy(data)
    expected_yt_dlp_options = get_default_yt_dlp_config_data()
    expected_enabled_modules = [
        "enable_ModerationCog",
        "enable_RoleManagerCog",
        "enable_UtilsCog",
        "enable_MusicCog"
    ]
    expected_disabled_modules = [
        "enable_MyCog"
    ]

    add_missing_modules_to_config(data, expected_enabled_modules, expected_disabled_modules)
    add_missing_yt_dlp_to_config(data, expected_yt_dlp_options)

    if data != orig_data:
        return data
    
    return None

def ensure_config(path: str, default_data: dict) -> dict | NoReturn:
    if not exists(path):
        log(f"Creating config file because config.json does not exist at {path}")
        success = write_file(path, default_data, True)

        if success == False:
            log(f"An error occurred while writing to {path}")
            sysexit(1)

        log(f"Created config file at {path}")

    log(f"Config file found at {path}")
    
    content = open_file(path, True)

    log(f"Found {len(content.keys())} entries in {path}")
    separator()

    log("Checking config file..")
    sleep(0.5)
    new_data = check_config(content)

    if new_data is not None:
        log("Updating config file..")
        sleep(0.5)
        success = write_file(path, new_data, True)

        if success == False:
            log(f"An error occured while updating file {path}")
    else:
        log("Config file is up to date.")
    separator()

    return content

def get_config_data(dir: str) -> dict | NoReturn:
    path = join(dir, "config.json")
    default_data = get_default_config_data()

    return ensure_config(path, default_data)
