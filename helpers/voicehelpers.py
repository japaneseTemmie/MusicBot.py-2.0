""" Voice helper functions for discord.py bot """

from settings import PLAYLIST_LOCKS, PLAYLIST_FILE_CACHE, ROLE_LOCKS, ROLE_FILE_CACHE, VOICE_OPERATIONS_LOCKED
from helpers.cachehelpers import invalidate_cache
from helpers.playlisthelpers import is_playlist_locked
from helpers.guildhelpers import update_guild_state, update_guild_states
from init.logutils import log, separator

import asyncio
import discord
from discord.ext import commands
from discord.interactions import Interaction
from typing import Any
from time import monotonic

# Connect behavior
async def greet_new_user_in_vc(guild_states: dict[str, Any], user: discord.Member) -> None:
    """ Say hi to `user` in the text channel the /join command was used in. """
    
    if user.guild.id in guild_states:
        can_greet = guild_states[user.guild.id]["allow_greetings"]
        text_channel = guild_states[user.guild.id]["interaction_channel"]
        current_track = guild_states[user.guild.id]["current_track"]
        voice_client = guild_states[user.guild.id]["voice_client"]
        timeout = guild_states[user.guild.id]["greet_timeouts"].get(user.id, False)

        if timeout or not can_greet:
            return
        
        welcome_text = f"Welcome to **{voice_client.channel.name}**, {user.mention}!"
        listening_text = f"Currently listening to: '**{current_track['title']}**' {'(paused)' if voice_client.is_paused() else ''}" if current_track is not None else\
        f"Currently listening to nothing.."

        await text_channel.send(f"{welcome_text}\n{listening_text}")
        guild_states[user.guild.id]["greet_timeouts"][user.id] = True
        
        await asyncio.sleep(10) # sleepy time :3
        guild_states[user.guild.id]["greet_timeouts"][user.id] = False

# Disconnect behavior
async def cleanup_guilds(guild_states: dict[str, Any], clients: list[discord.VoiceClient]) -> None:
    """ Clean up any inactive guild's data. Called at the end of `disconnect_routine()` """
    
    active_guild_ids = [client.guild.id for client in clients]

    for guild_id in guild_states.copy():
        if guild_id not in active_guild_ids:
            invalidate_cache(guild_id, guild_states)
            invalidate_cache(guild_id, PLAYLIST_LOCKS)
            invalidate_cache(guild_id, ROLE_LOCKS)
            invalidate_cache(guild_id, PLAYLIST_FILE_CACHE)
            invalidate_cache(guild_id, ROLE_FILE_CACHE)

            log(f"[GUILDSTATE] Cleaned up guild ID {guild_id} from guild states, cache and locks.")

async def check_users_in_channel(guild_states: dict[str, Any], member: discord.Member | Interaction) -> bool:
    """ Check if there are any users in a voice channel and disconnects if not.

    Returns True if none are left and the bot is disconnected, False otherwise. """
    
    if VOICE_OPERATIONS_LOCKED.is_set():
        return True # bot is disconnected

    voice_client = guild_states[member.guild.id]["voice_client"]
    locked_playlists = guild_states[member.guild.id]["locked_playlists"]
    is_extracting = guild_states[member.guild.id]["is_extracting"]
    handling_disconnect = guild_states[member.guild.id]["handling_disconnect_action"]

    if handling_disconnect:
        return True
    
    if len(voice_client.channel.members) > 1: # Bot counts as a member, therefore we must check if > 1
        return False

    if voice_client.is_connected() and\
        not voice_client.is_playing() and\
        not is_extracting and\
        not await is_playlist_locked(locked_playlists):

        log(f"[DISCONNECT][SHARD ID {member.guild.shard_id}] Disconnecting from channel ID {voice_client.channel.id} because no users are left in it and all conditions are met.")

        await update_guild_state(guild_states, member, True, "user_disconnect")
        if voice_client.is_paused():
            await update_guild_state(guild_states, member, True, "stop_flag")

        await voice_client.disconnect() # rest is handled by disconnect_routine() (hopefully)
        log(f"[DISCONNECT][SHARD ID {member.guild.shard_id}] Left channel ID {voice_client.channel.id}")
        return True

    return False

async def disconnect_routine(client: commands.Bot | commands.AutoShardedBot, guild_states: dict[str, Any], member: discord.Member | Interaction) -> None:
    """ Function that runs every voice_client.disconnect() call.
     
    Responsible for cleaning up the disconnected client and its guild data. """
    
    voice_client = guild_states[member.guild.id]["voice_client"]
    can_update_status = guild_states[member.guild.id]["allow_voice_status_edit"]
    has_pending_cleanup = guild_states[member.guild.id]["pending_cleanup"]
    handling_disconnect = guild_states[member.guild.id]["handling_disconnect_action"]
    user_initiated_disconnect = guild_states[member.guild.id]["user_disconnect"]
    
    if has_pending_cleanup or\
        handling_disconnect:
        log(f"[GUILDSTATE][SHARD ID {member.guild.shard_id}] Already handling a disconnect action for guild ID {member.guild.id}. Ignoring.")
        return

    await update_guild_states(guild_states, member, (True, True), ("pending_cleanup", "handling_disconnect_action"))

    if can_update_status and user_initiated_disconnect: # Prevents status from getting reset on network disconnects
        await update_guild_state(guild_states, member, None, "voice_status")
        await set_voice_status(guild_states, member)

    log(f"[GUILDSTATE][SHARD ID {member.guild.shard_id}] Waiting 10 seconds before cleaning up guild ID {member.guild.id}...")
    await asyncio.sleep(10) # Sleepy time :3 maybe it's a network issue

    if any(client.guild.id == member.guild.id for client in client.voice_clients): # Reconnected, all good
        log(f"[RECONNECT][SHARD ID {member.guild.shard_id}] Cleanup operation cancelled for guild ID {member.guild.id}")

        await update_guild_states(guild_states, member, (False, False), ("pending_cleanup", "handling_disconnect_action"))
        return
    
    """ Assumes the bot is disconnected before calling this function, which should be the case since disconnect_routine() gets triggered when there's a voice state update
    and the bot is no longer in a channel (after.channel is None) """
    voice_client.cleanup()

    """ Use this function instead of a simple 'del guild_states[member.guild.id]' so we catch
    any leftover guilds that were not properly cleaned up. """
    await cleanup_guilds(guild_states, client.voice_clients)

async def close_voice_clients(guild_states: dict[str, Any], client: commands.Bot | commands.AutoShardedBot) -> None:
    """ Close any leftover VCs and cleanup their open audio sources, if any. """

    log("Closing voice clients..")
    
    async def _close(vc: discord.VoiceClient):
        log(f"Closing connection to channel ID {vc.channel.id}..")
        
        can_edit_status = guild_states[vc.guild.id]["allow_voice_status_edit"]
        
        if vc.is_playing() or vc.is_paused():
            await update_guild_state(guild_states, vc, True, "stop_flag")
            vc.stop()

        if can_edit_status:
            await update_guild_state(guild_states, vc, None, "voice_status")
            await set_voice_status(guild_states, vc)

        try:
            await asyncio.wait_for(vc.disconnect(force=True), timeout=3) # API responds near immediately but the loop hangs for good 10 seconds if we don't pass a minimum timeout
        except asyncio.TimeoutError:
            pass
        
        vc.cleanup()
        log(f"Cleaned up channel ID {vc.channel.id}")
        
    await asyncio.gather(*[_close(vc) for vc in client.voice_clients])

    log("done")
    separator()

async def handle_channel_move(
        guild_states: dict[str, Any], 
        member: discord.Member | Interaction, 
        before_state: discord.VoiceState, 
        after_state: discord.VoiceState
    ) -> None:
    """ Function that runs every time the voice client is unexpectedly moved to another channel.

    Waits for users and resumes session in new channel. """

    handling_move_action = guild_states[member.guild.id]["handling_move_action"]
    voice_client = guild_states[member.guild.id]["voice_client"]
    text_channel = guild_states[member.guild.id]["interaction_channel"]
    can_update_status = guild_states[member.guild.id]["allow_voice_status_edit"]
    current_status = guild_states[member.guild.id]["voice_status"]
    start_time = guild_states[member.guild.id]["start_time"]
    elapsed_time = guild_states[member.guild.id]["elapsed_time"]

    if handling_move_action:
        log(f"[CHANNELSTATE][SHARD ID {member.guild.shard_id}] Already handling a move action for channel ID {after_state.channel.id}")
        return

    await update_guild_states(guild_states, member, (True, True), ("handling_move_action", "voice_client_locked"))

    if can_update_status and current_status:
        await before_state.channel.edit(status=None)

    if after_state.channel.type == discord.ChannelType.stage_voice:
        await text_channel.send("I've been moved to an unsupported stage channel. Don't jumpscare me like that!")

        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(guild_states, member, True, "stop_flag")

        await voice_client.disconnect()
        return

    if len(voice_client.channel.members) < 2:
        
        if voice_client.is_playing():
            voice_client.pause()
            elapsed_time = int(monotonic() - start_time)
            await update_guild_state(guild_states, member, elapsed_time, "elapsed_time")

        await text_channel.send(f"Waiting **10** seconds for users in new channel **{voice_client.channel.name}**.")

        await asyncio.sleep(10)

        no_users_in_channel = await check_users_in_channel(guild_states, member)
        if no_users_in_channel:
            await text_channel.send(f"Timeout exhausted, disconnected from channel **{voice_client.channel.name}**.")
            return

    if voice_client.is_paused():
        voice_client.resume()
        start_time = int(monotonic() - elapsed_time)
        await update_guild_state(guild_states, member, start_time, "start_time")

        if can_update_status and current_status:
            await set_voice_status(guild_states, member)

    await update_guild_states(guild_states, member, (False, False), ("voice_client_locked", "handling_move_action"))

    await text_channel.send(f"Resumed session in **{voice_client.channel.name}**.")

# Voice channel status
async def set_voice_status(guild_states: dict[str, Any], interaction: Interaction) -> None:
    """ Updates the `voice_client` channel status with the `voice_status` guild state. """
    
    if interaction.guild.id in guild_states:
        voice_client = guild_states[interaction.guild.id]["voice_client"]
        status = guild_states[interaction.guild.id]["voice_status"]

        await voice_client.channel.edit(status=status)
