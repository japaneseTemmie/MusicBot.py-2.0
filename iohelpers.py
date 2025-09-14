""" I/O Helpers for discord.py bot """
from json import load, dump
from os import makedirs
from os.path import exists
from init.logutils import log

def open_file(file_path: str, json_mode: bool) -> dict | str | None:
    """ Open a file and return its contents.
    
    Use `json_mode` to work with json files.
    
    Returns: file contents (either in plain text or hashmap depending on mode) or None.
    
    Must be sent to a thread if working with an asyncio loop. As I/O blocks the main thread. """
    
    try:
        with open(file_path) as f:
            return load(f) if json_mode else f.read()
    except OSError as e:
        log(f"An error occurred while opening {file_path}.\nErr: {e}")
        return None

def write_file(file_path: str, content: dict | str, json_mode: bool) -> bool:
    """ Write to a file and return None.

    Use json mode to work with JSON files.

    Returns a boolean.

    Must be sent to a thread if working with an asyncio loop. As I/O blocks the main thread. """
    
    try:
        with open(file_path, "w") as f:
            dump(content, f, indent=4) if json_mode else f.write(content)
        return True
    except OSError as e:
        log(f"An error occurred while writing to {file_path}.\nErr: {e}")
        return False

def ensure_paths(path: str, file: str | None=None, file_content_on_creation: str | dict={}) -> bool:
    """ Ensure that a path and, optionally, a file exist.

    If a file nane (as regular path) is passed and doesn't exist at `path`, it will be created with
    the contents of `file_content_on_creation` argument.

    Returns a boolean.
     
    Must be sent to a thread if working with an asyncio loop. As I/O blocks the main thread. """
    
    if not exists(path):
        try:
            makedirs(path, exist_ok=True)
        except OSError as e:
            log(f"An error occurred while making directory {path}.\nErr: {e}")
            return False

    if file and not exists(file):
        json_mode = isinstance(file_content_on_creation, dict)
        result = write_file(file, file_content_on_creation, json_mode)
        if not result:
            return False
        
    return True
