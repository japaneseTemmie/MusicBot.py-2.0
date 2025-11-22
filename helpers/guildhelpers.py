""" Guild helper functions for discord.py bot """

from settings import CAN_LOG, LOGGER, PATH, ROLE_LOCKS, ROLE_FILE_CACHE, VOICE_OPERATIONS_LOCKED, FILE_OPERATIONS_LOCKED
from error import Error
from helpers.iohelpers import open_file, write_file, ensure_paths
from helpers.cachehelpers import get_cache, store_cache
from init.logutils import log

import asyncio
import discord
from discord.interactions import Interaction
from typing import Any
from os.path import join

async def open_guild_json(
        interaction: Interaction,
        file_name: str,
        file_locks: dict[int, asyncio.Lock],
        cache: dict,
        on_general_file_lock_error_msg: str,
        on_read_error_msg: str
    ) -> dict | Error:
    """ Safely read the content of a guild's file.

    Cache the content of a successful read.

    If successful, returns the file JSON structure. Error otherwise. """
    locked_error = await check_file_lock(msg_on_locked=on_general_file_lock_error_msg)
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
        file_locks: dict[int, asyncio.Lock],
        cache: dict,
        on_general_file_lock_msg: str,
        on_write_error_msg: str,
        backup: dict | None=None
    ) -> bool | Error:
    """ Safely write the modified content to a guild file.

    Cache new content if written successfully.
    
    Returns a boolean [True] or Error. """
    
    locked_error = await check_file_lock(msg_on_locked=on_general_file_lock_msg)
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
    
    If the role is in the guild and in `roles.json` and the user has it, return True.
    
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
        await interaction.response.send_message(f"I cannot verify your roles temporarily.\nError: {roles.msg}", ephemeral=True) 
        return False # A corrupted file can be abused to get access, therefore we cannot return True here.

    role_to_look_for = "playlist" if playlist else "music"
    role_id = roles.get(role_to_look_for, None)

    if not roles or\
        role_id is None:
        return True

    user_roles = interaction.user.roles
    role = discord.utils.get(interaction.guild.roles, id=int(role_id))

    if role is None:
        await interaction.response.send_message(f"I cannot verify your roles.\nError: Role (ID **{role_id}**) not found in guild.", ephemeral=True)
        return False

    if role in user_roles:
        return True
    
    await interaction.response.send_message(f"You do not have the required **{role_to_look_for}** role to use this command!", ephemeral=True)
    return False

# Function to add a file lock for a specific guild id if it doesn't exist
async def ensure_lock(interaction: Interaction, locks: dict) -> asyncio.Lock:
    """ Adds an `asyncio.Lock` object to a guild if not present.
     
    Returns the created lock. """
    
    if interaction.guild.id not in locks:
        locks[interaction.guild.id] = asyncio.Lock()

    return locks[interaction.guild.id]

# Functions for updating guild states
async def update_query_extraction_state(
        guild_states: dict[str, Any], 
        interaction: Interaction, 
        progress_current: int, 
        progress_total: int,
        progress_item_name: str | None,
        progress_source_website: str | None,
    ) -> None:
    """ Update the current extraction state. """
    
    if interaction.guild.id in guild_states:
        await update_guild_states(
            guild_states, 
            interaction, 
            (progress_current, progress_total, progress_item_name, progress_source_website), 
            ("progress_current", "progress_total", "progress_item_name", "progress_source_website")
        )

async def update_guild_state(guild_states: dict[str, Any], interaction: Interaction, value: Any, state: str) -> None:
    """ Update guild `state` with a new `value`. """
    
    if interaction.guild.id in guild_states:

        guild_state = guild_states[interaction.guild.id]
        if state not in guild_state:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] No '{state}' found in guild_states[{interaction.guild.id}]. Creating state with requested value..")
            
        guild_state[state] = value

async def update_guild_states(guild_states: dict[str, Any], interaction: Interaction, values: tuple[Any], states: tuple[str]) -> None:
    """ Bulk update guild `states` with `values`. """
    
    if interaction.guild.id in guild_states:        
        for state, value in zip(states, values):
            await update_guild_state(guild_states, interaction, value, state)

# Function to reset states
async def get_default_state(voice_client: discord.VoiceClient, current_text_channel: discord.TextChannel) -> dict[str, Any]:
    """ Return a hashmap of default guild states where `voice_client` and `interaction_channel` are passed as function parameters. """
    
    return {
        "voice_client": voice_client,
        "voice_client_locked": False,
        "stop_flag": False,
        "user_disconnect": False,
        "user_interrupted_playback": False,
        "is_looping": False,
        "is_random": False,
        "is_looping_queue": False,
        "is_modifying": False,
        "is_reading_queue": False,
        "is_reading_history": False,
        "is_extracting": False,
        "allow_greetings": True,
        "allow_voice_status_edit": True,
        "voice_status": None,
        "progress_current": 0,
        "progress_total": 0,
        "progress_item_name": None,
        "progress_source_website": None,
        "current_track": None,
        "track_to_loop": None,
        "first_track_start_date": None,
        "elapsed_time": 0,
        "start_time": 0,
        "queue": [],
        "queue_history": [],
        "queue_to_loop": [],
        "locked_playlists": {},
        "filters": {},
        "pending_cleanup": False,
        "handling_disconnect_action": False,
        "handling_move_action": False,
        "interaction_channel": current_text_channel,
        "greet_timeouts": {}
    }

# Functions for checking guild states and replying to interactions
async def check_channel(guild_states: dict[str, Any], interaction: Interaction) -> bool:
    """ Check different channel state scenarios and handle them by replying to `interaction`. """
    
    if interaction.guild.id not in guild_states or\
        interaction.guild.voice_client is None:
        await interaction.response.send_message("I'm not in any voice channel!")
        return False
    
    if not interaction.user.voice or\
        interaction.user.voice.channel != interaction.guild.voice_client.channel:
        await interaction.response.send_message("Join my voice channel first.")
        return False
    
    text_channel = guild_states.get(interaction.guild.id, {}).get("interaction_channel", None)

    if text_channel and interaction.channel != text_channel:
        await interaction.response.send_message(f"To avoid results in different channels, please run this command in **{text_channel.mention}**.")
        return False
    
    return True

async def check_vc_lock(reply_to_interaction: bool=False, interaction: Interaction | None=None, msg_on_locked: str | None=None) -> bool | Error:
    """ Check the `VOICE_OPERATIONS_LOCKED` flag.
    
    If True, return an error object or reply to the interaction with `msg_on_locked` or a default message and return False. """
    
    msg = msg_on_locked or "Voice connections temporarily disabled."
    
    if VOICE_OPERATIONS_LOCKED.is_set():
        
        if reply_to_interaction and interaction is not None:
            await interaction.response.send_message(msg) if not interaction.response.is_done() else\
            await interaction.followup.send(msg)
            return False
        else:
            return Error(msg)
    
    return True

async def check_file_lock(reply_to_interaction: bool=False, interaction: Interaction | None=None, msg_on_locked: str | None=None) -> bool | Error:
    """ Check the `FILE_OPERATIONS_LOCKED` flag.
    
    If True, return an error object or reply to an interaction with `msg_on_locked` or a default entry and return False. """
    
    msg = msg_on_locked or "Role/Playlist reading temporarily disabled."
    
    if FILE_OPERATIONS_LOCKED.is_set():
        
        if reply_to_interaction and interaction is not None:
            await interaction.response.send_message(msg) if not interaction.response.is_done() else\
            await interaction.followup.send(msg)
            return False
        else:
            return Error(msg)
        
    return True

async def check_guild_state(
        guild_states: dict[str, Any],
        interaction: Interaction,
        state: str,
        condition: Any,
        msg: str
    ) -> bool:

    """ Check a guild state.
    
    If it matches `condition`, reply to `interaction` with `msg` and return False, else return True. """
    
    if interaction.guild.id in guild_states:
        guild_state = guild_states[interaction.guild.id]
        
        if state not in guild_state:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Cannot check state '{state}'. Not found in guild_states[{interaction.guild.id}].")
            return False
        
        value = guild_state[state]

        if value == condition:
            await interaction.response.send_message(msg) if not interaction.response.is_done() else\
            await interaction.followup.send(msg)
            return False
        
        return True
