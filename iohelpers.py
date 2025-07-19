""" I/O Helpers for discord.py bot """

from settings import *

def open_file(file_path: str, json_mode: bool) -> dict | str | int:
    """ Open a file and return its contents.\n
    Use `json_mode` to work with json files.\n
    Returns: file contents (either in plain text or hashmap depending on mode) or READ_FAIL return code.\n
    Must be sent to a thread. """
    
    with open(file_path) as f:
        try:
            content = load(f) if json_mode else f.read()
            
            return content
        except Exception as e:
            if CAN_LOG and LOGGER is not None:
                LOGGER.exception(e)

            return RETURN_CODES["READ_FAIL"]

def write_file(file_path: str, content: dict | str, json_mode: bool) -> None | int:
    """ Write to a file and return None.\n
    Use json mode to work with JSON files.\n
    Returns: None (success) or WRITE_FAIL return code.\n
    Must be sent to a thread """
    
    with open(file_path, "w") as f:
        try:
            dump(content, f, indent=4) if json_mode else f.write(content)
        except Exception as e:
            if CAN_LOG and LOGGER is not None:
                LOGGER.exception(e)

            return RETURN_CODES["WRITE_FAIL"]
        
def ensure_paths(path: str, file: str | None) -> int:
    if not exists(path):
        try:
            makedirs(path, exist_ok=True)
        except Exception as e:
            if CAN_LOG and LOGGER is not None:
                LOGGER.exception(e)

            return RETURN_CODES["WRITE_FAIL"]

    if file and not exists(file):
        result = write_file(file, {}, True)
        if result == RETURN_CODES["WRITE_FAIL"]:
            return RETURN_CODES["WRITE_FAIL"]
        
    return RETURN_CODES["WRITE_SUCCESS"]