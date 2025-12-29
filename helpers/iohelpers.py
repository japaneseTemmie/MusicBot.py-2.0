""" I/O Helpers for discord.py bot """

from init.logutils import log, log_to_discord_log

from logging import Logger
from json import JSONDecodeError, load, dump
from os import makedirs
from os.path import exists, join

def read_file_bytes(file_path: str, buf_size: int=-1, can_log: bool=False, logger: Logger | None=None) -> bytes | None:
    """ Open and read a file.
    
    Optionally, read up to n bytes using the `buf_size` argument. 

    Return bytes or None on failure.
     
    Must be sent to a thread if working with an asyncio loop. """

    try:
        with open(file_path, "rb") as f:
            return f.read(buf_size)
    except OSError as e:
        log(f"An error occurred while reading file {file_path} as bytes\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return None

def read_file_json(file_path: str, encoding: str="utf-8", can_log: bool=False, logger: Logger | None=None) -> dict | None:
    """ Open and read a file as JSON.
    
    Optionally, specify a different encoding string using the `encoding` argument.

    Return a dictionary or None on failure.
     
    Must be sent to a thread if working with an asyncio loop. """
    
    try:
        with open(file_path, encoding=encoding) as f:
            return load(f)
    except (OSError, JSONDecodeError) as e:
        log(f"An error occurred while opening file {file_path} as JSON\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return None

def read_file_text(file_path: str, buf_size: int=-1, encoding: str="utf-8", can_log: bool=False, logger: Logger | None=None) -> str | None:
    """ Open a file and return its contents.
    
    Optionally, read up to n characters using the `buf_size` argument.

    Optionally, specify a different encoding string using the `encoding` argument.

    Return file contents as string or None on failure.
    
    Must be sent to a thread if working with an asyncio loop. """
    
    try:
        with open(file_path, encoding=encoding) as f:
            return f.read(buf_size)
    except OSError as e:
        log(f"An error occurred while opening {file_path} as string.\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return None

def write_file_bytes(file_path: str, content: bytes, can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Open and write content to a file as bytes.
    
    Return a success boolean value.
     
    Must be sent to a thread if working with an asyncio loop. """
    
    try:
        with open(file_path, "wb") as f:
            f.write(content)

        return True
    except OSError as e:
        log(f"An error occurred while writing to {file_path} as bytes\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return False

def write_file_json(file_path: str, content: dict, encoding: str="utf-8", can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Open and write content to a file as JSON.

    Optionally, specify a different encoding string using the `encoding` argument. 
    
    Return a success boolean value.
     
    Must be sent to a thread if working with an asyncio loop. """
    
    try:
        with open(file_path, "w", encoding=encoding) as f:
            dump(content, f, indent=4)

        return True
    except OSError as e:
        log(f"An error occurred while writing to {file_path} as JSON\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return False

def write_file_text(file_path: str, content: str, encoding: str="utf-8", can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Open and write content to a file as string.

    Optionally, specify a different encoding string using the `encoding` argument.

    Return a success boolean value.

    Must be sent to a thread if working with an asyncio loop. """
    
    try:
        with open(file_path, "w", encoding=encoding) as f:
            f.write(content)

        return True
    except OSError as e:
        log(f"An error occurred while writing to {file_path} as string.\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return False

def make_path(directory: str, can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Create a directory tree.

    Returns a boolean indicating success.
     
    Must be sent to a thread if working with an asyncio loop. """
    
    try:
        makedirs(directory, exist_ok=True)
        return True
    except OSError as e:
        log(f"An error occurred while making directory {directory}.\nErr: {e}")
        log_to_discord_log(e, can_log=can_log, logger=logger)

        return False

def ensure_paths(path: str, file_name: str | None=None, file_content_on_creation: str | bytes | dict | None=None, can_log: bool=False, logger: Logger | None=None) -> bool:
    """ Ensure that a path and, optionally, a file exist.

    If a file name is passed as `file_name` and doesn't exist at `path`, it will be created with
    the contents of `file_content_on_creation` argument. (which will be empty by default)

    Returns a boolean indicating success.
     
    Must be sent to a thread if working with an asyncio loop. As I/O blocks the main thread. """
    
    if not exists(path):
        result = make_path(path, can_log=can_log, logger=logger)
        if not result:
            return False

    if file_name is not None:
        if isinstance(file_content_on_creation, bytes):
            writer = write_file_bytes
        elif isinstance(file_content_on_creation, dict):
            writer = write_file_json
        else:
            writer = write_file_text

        full_fp = join(path, file_name)
        if file_content_on_creation is None:
            file_content_on_creation = ""

        if not exists(full_fp):
            result = writer(full_fp, file_content_on_creation, can_log=can_log, logger=logger)

            if not result:
                return False
        
    return True
