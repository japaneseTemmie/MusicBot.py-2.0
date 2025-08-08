""" I/O Helpers for discord.py bot """

from settings import *
from helpers import *

def open_file(file_path: str, json_mode: bool) -> dict | str | bool:
    """ Open a file and return its contents.\n
    Use `json_mode` to work with json files.\n
    Returns: file contents (either in plain text or hashmap depending on mode) or False on read fail.\n
    Must be sent to a thread. """
    
    try:
        with open(file_path) as f:
            return load(f) if json_mode else f.read()
    except Exception as e:
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(e)

        return False

def write_file(file_path: str, content: dict | str, json_mode: bool) -> bool:
    """ Write to a file and return None.\n
    Use json mode to work with JSON files.\n
    Returns a boolean.\n
    Must be sent to a thread. """
    
    try:
        with open(file_path, "w") as f:
            dump(content, f, indent=4) if json_mode else f.write(content)
        return True
    except Exception as e:
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(e)

        return False

def ensure_paths(path: str, file: str | None, file_content_on_creation: str | dict={}) -> bool:
    if not exists(path):
        try:
            makedirs(path, exist_ok=True)
        except Exception as e:
            if CAN_LOG and LOGGER is not None:
                LOGGER.exception(e)

            return False

    if file and not exists(file):
        json_mode = isinstance(file_content_on_creation, dict)
        result = write_file(file, file_content_on_creation, json_mode)
        if not result:
            return False
        
    return True