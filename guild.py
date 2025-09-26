""" Guild helper functions for discord.py bot """

from settings import PATH
from init.logutils import log, separator

import asyncio
import discord
from os.path import join, isdir, exists
from os import listdir, makedirs
from shutil import rmtree
from sys import exit as sysexit

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
    """ Delete a guild directory using rmtree. """
    
    try:
        if isdir(path):
            rmtree(path)

            log(f"Removed tree {path}")
    except OSError as e:
        log(f"An error occurred while deleting {path}\nErr: {e}")

def delete_guild_dirs(to_delete: list[str]) -> bool:
    for path in to_delete:
        delete_guild_tree(path)

def ensure_guild_data_path(path: str) -> None:
    if not exists(path):
        log(f"Creating {path} directory.")

        try:
            makedirs(path, exist_ok=True)
            log(f"Created guild data directory at {path}")
        except OSError as e:
            log(f"An error occurred while creating {path}\nErr: {e}")
            sysexit(1)
    else:
        log(f"Found guild data at {path}.")

async def ensure_guild_data(client, guilds: list[discord.Guild]) -> None:
    """ Compare the guilds the bot's currently in
    with the guild IDs in the guild_data directory
    and delete any that aren't in the `guilds` parameter list. """
    
    guild_count = len(guilds)
    guild_data_path = join(PATH, "guild_data")

    ensure_guild_data_path(guild_data_path)
    separator()

    log(f"{client.user.name} is in {guild_count} {'guilds' if guild_count > 1 else 'guild'}.")
    if guild_count > 2400 and guild_count < 2500:
        log(f"{client.user.name} is close to 2500 guilds. Consider enabling sharding in config.json")
        await asyncio.sleep(5)

    separator()
    log(f"Checking for leftover guilds in {guild_data_path}.")
    to_delete = get_guilds_to_delete(client.user.name, guilds)

    if to_delete:
        delete_guild_dirs(to_delete)
    else:
        log("Success! No issues found.")