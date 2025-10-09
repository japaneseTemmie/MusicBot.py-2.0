""" Help system functions for discord.py bot """

from helpers.iohelpers import open_file
from init.logutils import log, separator

from os.path import join, exists

def open_help_file(dir: str) -> dict[str, str] | None:
    """ Attempts to open the `help.json` file in the `dir` folder. If unreadable or missing, returns None. Otherwise, returns the contents of the file in hashmap. """
    
    path = join(dir, "help.json")
    if not exists(path):
        log(f"No help file found. /help will not be available.")
        separator()
        
        return None

    log(f"Help file found at {path}")
    
    content = open_file(path, True)
    if content is None:
        log("No /help will be available.")

        return None
    
    log(f"Found {len(content.keys())} entries in help file.")

    separator()
    return content