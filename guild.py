""" Guild checks helper functions for discord.py bot """

from settings import *

def is_in_guild(id: int, guilds: list[discord.Guild]) -> bool:
    return discord.utils.get(guilds, id=int(id)) is not None

def get_guilds_to_delete(user: str, guilds: list[discord.Guild]) -> list[str]:
    """ Find guilds that aren't in the bot's known list and schedule them for deletion. """
    
    path = join(PATH, "guild_data")
    folders = listdir(path)
    to_delete = []

    for id in folders:
        if id.isdigit() and not is_in_guild(id, guilds):
            log(f"{user} is not in guild ID {id}, will be scheduled for removal.")

            full_file_path = join(path, id)
            to_delete.append(full_file_path)

    return to_delete

def delete_guild_tree(path: str) -> None:
    try:
        if isdir(path):
            rmtree(path)

            log(f"Removed tree {path}")
    except OSError as e:
        log(f"An OS error occurred while deleting path {path}\nErr: {e}")

def delete_guild_dirs(to_delete: list[str]) -> bool:
    for path in to_delete:
        delete_guild_tree(path)

def check_guild_data_path(path: str) -> None:
    if not exists(path):
        log(f"Creating {path} directory.")

        try:
            makedirs(path, exist_ok=True)
            log(f"Created guild data directory at {path}")
        except OSError as e:
            log(f"An error occurred while creating {path}\nErr: {e}")
            sysexit(0)
    else:
        log(f"Found guild data at {path}.")

async def check_guilds(bot_user: str, guilds: list[discord.Guild]) -> None:
    """ Compare the guilds the bot's currently in\n
    with the guild IDs in the guild_data directory\n
    and delete any that aren't in the guilds parameter list. """

    if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
        return
    
    """ 
    Lock VoiceClient and file operations first to prevent
    any changes made by users during deletion.
    Then, release the locks.
    """

    VOICE_OPERATIONS_LOCKED_PERMANENTLY.set()
    FILE_OPERATIONS_LOCKED_PERMANENTLY.set()
    
    guild_count = len(guilds)

    check_guild_data_path(join(PATH, "guild_data"))
    log(f"{bot_user} is in {guild_count} {'guilds' if guild_count > 1 else 'guild'}.")
    log("Checking for missing guilds.")

    to_delete = get_guilds_to_delete(bot_user, guilds)
    if to_delete:
        delete_guild_dirs(to_delete)
    else:
        log("Success! No issues found.")

    VOICE_OPERATIONS_LOCKED_PERMANENTLY.clear()
    FILE_OPERATIONS_LOCKED_PERMANENTLY.clear()