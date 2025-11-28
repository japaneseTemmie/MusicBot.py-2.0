""" Guild helper functions for discord.py bot """

from settings import PATH, CAN_LOG, LOGGER
from init.constants import MAX_GUILD_COUNT_BEFORE_SHARDING_REQUIRED
from init.logutils import log, log_to_discord_log, separator
from helpers.iohelpers import make_path

import asyncio
import discord
from os.path import join, isdir, exists
from os import listdir
from shutil import rmtree

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

def delete_guild_tree(path: str) -> bool:
    """ Delete a guild data directory. """
    
    try:
        if isdir(path):
            rmtree(path)

            log(f"Removed tree {path}")
    except OSError as e:
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
        
        await asyncio.sleep(5)

async def ensure_guild_data() -> bool:
    """ Ensures the guild data directory exists. 
    
    Returns a success value. """

    guild_data_path = join(PATH, "guild_data")

    guild_data_exists = await asyncio.to_thread(ensure_guild_data_path, guild_data_path)
    separator()

    if not guild_data_exists:
        return False

    return True

async def check_guild_data(user_name: str, guilds: list[discord.Guild], is_sharded_flag: bool) -> bool:
    """ Compare the guilds the bot's currently in
    with the guild IDs in the `guild_data` directory
    and delete any that aren't in the `guilds` list. 
    
    Return a success value. """

    guild_count = len(guilds)
    guild_data_path = join(PATH, "guild_data")

    await check_guild_count(user_name, guild_count, is_sharded_flag)

    separator()
    log(f"Checking for leftover guilds in {guild_data_path}.")

    if not exists(guild_data_path):
        log(f"{guild_data_path} does not exist. Skipping guild check.")
        separator()
        
        return False

    to_delete = await asyncio.to_thread(get_guilds_to_delete, user_name, guilds)

    if to_delete:
        deleted_successfully = await asyncio.to_thread(delete_guild_dirs, to_delete)
        if not deleted_successfully:
            return False
    else:
        log("Success! No issues found.")

    log("done")
    separator()

    return True