""" I/O Helpers for discord.py bot """

from init.logutils import log, log_to_discord_log

from json import JSONDecodeError, load, dump
from os import makedirs
from os.path import exists, join
from logging import Logger

def open_file(file_path: str, json_mode: bool, can_log: bool=False, logger: Logger | None=None) -> dict | str | None:
    """ Open a file and return its contents.
    
    Use `json_mode` to work with JSON files.
    
    Returns: file contents (either in plain text or hashmap depending on mode) or None (if failed).
    
    Must be sent to a thread if working with an asyncio loop. As I/O blocks the main thread. """
    
    try:
        with open(file_path) as f:
            return load(f) if json_mode else f.read()
    except (OSError, JSONDecodeError) as e:
        log(f"An error occurred while opening {file_path}.\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return None

def write_file(file_path: str, content: dict | str, json_mode: bool, can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Write to a file and return None.

    Use `json_mode` to work with JSON files.

    Returns a boolean indicating success.

    Must be sent to a thread if working with an asyncio loop. As I/O blocks the main thread. """
    
    try:
        with open(file_path, "w") as f:
            dump(content, f, indent=4) if json_mode else f.write(content)

        return True
    except OSError as e:
        log(f"An error occurred while writing to {file_path}.\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return False

def make_path(directory: str, can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Create a directory tree.
     
    Must be sent to a thread if working with an asyncio loop. """
    
    try:
        makedirs(directory, exist_ok=True)
        return True
    except OSError as e:
        log(f"An error occurred while making directory {directory}.\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return False

def ensure_paths(path: str, file_name: str=None, file_content_on_creation: str | dict=None, can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Ensure that a path and, optionally, a file exist.

    If a file name is passed as `file_name` and doesn't exist at `path`, it will be created with
    the contents of `file_content_on_creation` argument.

    Returns a boolean indicating success.
     
    Must be sent to a thread if working with an asyncio loop. As I/O blocks the main thread. """
    
    if not exists(path):
        result = make_path(path, can_log=can_log, logger=logger)
        if not result:
            return False

    file_path = join(path, file_name)
    if file_name and not exists(file_path):
        json_mode = isinstance(file_content_on_creation, dict)
        result = write_file(file_path, file_content_on_creation if file_content_on_creation is not None else '', json_mode)

        if not result:
            return False
        
    return True
