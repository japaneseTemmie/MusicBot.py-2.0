""" Guild helper functions for discord.py bot """

from settings import PATH, CAN_LOG, LOGGER, CAN_AUTO_DELETE_GUILD_DATA
from init.constants import MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED
from init.logutils import log, log_to_discord_log, separator
from helpers.iohelpers import make_path

import asyncio
import discord
from os.path import join, isdir, exists
from os import scandir
from shutil import rmtree

 # I/O for guild_data
def delete_guild_tree(path: str) -> bool:
    """ Delete a guild data directory. """
    
    try:
        if isdir(path):
            rmtree(path)

            log(f"Removed tree {path}")
    except (OSError, PermissionError, FileNotFoundError) as e:
        log(f"An error occurred while deleting {path}\nErr: {e}")
        return False

    return True

def delete_guild_dirs(to_delete: list[str]) -> bool:
    """ Delete guild data directories from a list of guild IDs. """
    
    success = True
    for path in to_delete:
        deleted_successfully = delete_guild_tree(path)
        if not deleted_successfully:
            success = False

    return success

def ensure_guild_data_path(guild_data_path: str) -> bool:
    """ Ensures the given guild data path exists. """
    
    if not exists(guild_data_path):
        result = make_path(guild_data_path, can_log=CAN_LOG, logger=LOGGER)
        if not result:
            return False
        
        log(f"Created {guild_data_path} directory.")
    else:
        log(f"Found guild data at {guild_data_path}.")

    return True

async def ensure_guild_data() -> bool:
    """ Ensures the guild data directory exists. 
    
    Returns a success value. """

    guild_data_path = join(PATH, "guild_data")

    guild_data_exists = await asyncio.to_thread(ensure_guild_data_path, guild_data_path)
    separator()

    if not guild_data_exists:
        return False

    return True

# Finder functions
def is_in_guild(guild_id: int, guild_ids: set[int]) -> bool:
    return guild_id in guild_ids

def find_guilds_to_delete(user: str, guild_ids: set[int]) -> list[str]:
    """ Find guilds that aren't in the bot's known list and schedule them for deletion. """
    
    folders = []
    to_delete = []
    path = join(PATH, "guild_data")

    try:
        with scandir(path) as iterator:
            folders = list(iterator)
    except Exception as e:
        log(f"Unable to iterate over {path} due to error, skipping guild cleanup.\nErr: {e}")
        return to_delete

    for entry in folders:
        if entry.is_dir() and entry.name.isdigit() and not is_in_guild(int(entry.name), guild_ids):
            log(f"{user} is not in guild ID {entry.name}, will be scheduled for removal.")

            full_file_path = join(path, entry.name)
            to_delete.append(full_file_path)

    return to_delete

# Housekeeping
async def check_guild_count(user_name: str, guild_count: int, is_sharded_flag: bool) -> None:
    """ Log guild count information and warn on sharding if guild count is close to the limit. """
    
    log(f"{user_name} is in {guild_count} {'guilds' if guild_count > 1 else 'guild'}.")
    
    if is_sharded_flag:
        return

    message = None
    if guild_count > MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED:
        message = f"{user_name} has exceeded {MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED} guilds. This may cause an issue. Consider enabling sharding in config.json"
    elif guild_count > MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED - 100:
        message = f"{user_name} is close to {MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED} guilds. Consider enabling sharding in config.json"
        
    if message is not None:
        log(message)
        log_to_discord_log(message, "warning", CAN_LOG, LOGGER)
        
        await asyncio.sleep(3)

async def check_guild_data(user_name: str, guilds: list[discord.Guild], is_sharded_flag: bool) -> bool:
    """ Compare the guilds the bot's currently in
    with the guild IDs in the `guild_data` directory
    and delete any that aren't in the `guilds` list. 
    
    Return a success value. """

    guild_data_path = join(PATH, "guild_data")
    guild_count = len(guilds)
    guild_ids = set([guild.id for guild in guilds])

    await check_guild_count(user_name, guild_count, is_sharded_flag)
    separator()

    if CAN_AUTO_DELETE_GUILD_DATA:
        log(f"Checking for leftover guilds in {guild_data_path}.")

        to_delete = await asyncio.to_thread(find_guilds_to_delete, user_name, guild_ids)

        if to_delete:
            deleted_successfully = await asyncio.to_thread(delete_guild_dirs, to_delete)
            if not deleted_successfully:
                separator()
                return False
        else:
            log("Success! No issues found.")
    else:
        log("Skipping guild check as per config value.")

    log("done")
    separator()

    return True