from os.path import join, exists
from iohelpers import open_file
from logutils import log, separator

def open_help_file(dir: str) -> dict | None:
    path = join(dir, "help.json")
    if not exists(path):
        log(f"No help file found. /help will not be available.")
        separator()
        
        return None

    log(f"Help file found at {path}")
    
    content = open_file(path, True)
    if content is None:
        log(f"An error occurred while opening {path}.\nNo /help will be available.")
        separator()

        return None
    
    log(f"Found {len(content.keys())} entries in help file.")

    separator()
    return content