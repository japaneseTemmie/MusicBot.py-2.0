""" Guild helpers for discord.py bot """

from settings import CAN_LOG, LOGGER, PATH, ROLE_LOCKS, ROLE_FILE_CACHE
from error import Error
from iohelpers import open_file, write_file, ensure_paths
from helpers import check_file_lock, ensure_lock
from cachehelpers import get_cache, store_cache

import asyncio
import discord
from discord.interactions import Interaction
from os.path import join

async def open_guild_json(
        interaction: Interaction,
        file_name: str,
        file_locks: dict,
        cache: dict,
        on_general_file_lock_error_msg: str,
        on_read_error_msg: str
    ) -> dict | Error:
    """ Safely read the content of a guild's file.

    Cache the content of a successful read.

    If successful, returns the file JSON structure. Error otherwise. """
    locked_error = await check_file_lock(on_general_file_lock_error_msg)
    if isinstance(locked_error, Error):
        return locked_error
    
    file_lock = await ensure_lock(interaction, file_locks)

    async with file_lock:
        content = get_cache(cache, interaction.guild.id)
        if content:
            return content

        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, file_name)

        success = await asyncio.to_thread(ensure_paths, path, file_name, {}, CAN_LOG, LOGGER)
        if success == False:
            return Error("Failed to create guild data.")

        content = await asyncio.to_thread(open_file, file, True, CAN_LOG, LOGGER)
        if content is None:
            return Error(on_read_error_msg)
        
        store_cache(content, interaction.guild.id, cache)

        return content
    
async def write_guild_json(
        interaction: Interaction,
        content: dict,
        file_name: str,
        file_locks: dict,
        cache: dict,
        on_general_file_lock_msg: str,
        on_write_error_msg: str,
        backup: dict | None=None
    ) -> bool | Error:
    """ Safely write the modified content to a guild file.

    Cache new content if written successfully.
    
    Returns a boolean [True] or Error. """
    
    locked_error = await check_file_lock(on_general_file_lock_msg)
    if isinstance(locked_error, Error):
        return locked_error
    
    file_lock = await ensure_lock(interaction, file_locks)

    async with file_lock:
        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, file_name)
            
        success = await asyncio.to_thread(ensure_paths, path, file_name, {}, CAN_LOG, LOGGER)
        if success == False:
            return Error("Failed to create guild data.")

        result = await asyncio.to_thread(write_file, file, content, True, CAN_LOG, LOGGER)

        if result == False:
            if backup is not None:
                await asyncio.to_thread(write_file, file, backup, True, CAN_LOG, LOGGER)

            return Error(on_write_error_msg)
        
        store_cache(content, interaction.guild.id, cache)
        
        return True
    
async def user_has_role(interaction: Interaction, playlist: bool=False) -> bool:
    """ Check role ownership.
    
    If the role is in the guild or in the config file and the user has it, return True.
    
    if none of the above conditions are met, return False. """

    roles = await open_guild_json(
        interaction, 
        "roles.json", 
        ROLE_LOCKS, 
        ROLE_FILE_CACHE, 
        "Role reading temporarily disabled.", 
        "Failed to read role contents."
    )
    if isinstance(roles, Error):
        await interaction.response.send_message("I cannot verify your roles temporarily.", ephemeral=True) # A corrupted file can be abused to get access, therefore we cannot return True here.
        return False

    role_to_look_for = "playlist" if playlist else "music"
    role_id = roles.get(role_to_look_for, None)

    if not roles or\
        role_id is None:
        return True

    user_roles = interaction.user.roles
    role = discord.utils.get(interaction.guild.roles, id=int(role_id))

    if role in user_roles:
        return True
    
    await interaction.response.send_message(f"You do not have the required **{role_to_look_for}** role to use this command!", ephemeral=True)
    return False