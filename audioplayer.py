""" Audio player wrapper module for discord.py bot. """

from settings import CAN_LOG, LOGGER
from bot import Bot, ShardedBot
from init.logutils import log, log_to_discord_log
from helpers.timehelpers import format_to_seconds
from helpers.ffmpeghelpers import (
    get_ffmpeg_options, is_stream_url_alive, resolve_expired_url, check_player_crash
)
from helpers.guildhelpers import update_guild_state, update_guild_states
from helpers.voicehelpers import set_voice_status, check_users_in_channel
from helpers.queuehelpers import get_next_track

import asyncio
import discord
from discord.interactions import Interaction
from enum import Enum
from typing import Any
from datetime import datetime
from time import monotonic
from copy import deepcopy

class PlayerStopReason(Enum):
    STOP_FLAG = 1
    VC_LOCKED = 2
    NO_USERS_IN_CHANNEL = 3
    CRASH_RECOVERY = 4

class AudioPlayer:
    def __init__(self, client: Bot | ShardedBot):
        self.client = client
        self.guild_states = self.client.guild_states

        self.max_history_track_limit = self.client.max_history_track_limit

    async def submit_track_to_player(
            self, 
            interaction: Interaction,
            voice_client: discord.VoiceClient, 
            track: dict[str, Any], 
            position: int,
            is_looping: bool
        ) -> dict[str, Any] | None:
        """ Submit a track to the voice client player. 
        
        Return track or None if something went wrong while spawning an FFmpeg subprocess (not FFmpeg runtime error). """

        # Keep a copy of the old title and source website and replace it when re-fetching a stream to match the custom playlist track name assigned by users.
        old_title = str(track["title"])
        old_source_website = str(track["source_website"])

        position = max(0, min(position, format_to_seconds(track["duration"])))
        ffmpeg_options = await get_ffmpeg_options(position)

        try:
            is_stream_valid = await is_stream_url_alive(track["url"], self.client.stream_url_check_session)
            if not is_stream_valid: # This won't work anymore. Need a new stream. Slow, but required or else everything breaks :3
                log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Resolving expired URL in guild ID {interaction.guild.id}")
                track = await resolve_expired_url(track["webpage_url"])

                if track is None or not await is_stream_url_alive(track["url"], self.client.stream_url_check_session):
                    log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Re-fetched stream in guild ID {interaction.guild.id} is invalid, raising error..")
                    raise ValueError("Unrecoverable stream.")
                
                track["title"] = old_title
                track["source_website"] = old_source_website

            source = discord.FFmpegPCMAudio(track["url"], options=ffmpeg_options["options"], before_options=ffmpeg_options["before_options"])
            voice_client.stop()
            voice_client.play(source, after=lambda e: self.handle_playback_end(e, interaction))
        except Exception as e:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] An error occurred while spawning an FFmpeg process in guild ID {interaction.guild.id}. Check log for more info.")
            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
            if is_looping:
                await update_guild_state(self.guild_states, interaction, False, "is_looping")
            
            self.handle_playback_end(e, interaction)
            return None
        
        return track

    async def update_player_states(self, interaction: Interaction, position: int, track: dict[str, Any], state: str | None) -> None:
        """ Update player guild states after playing a track. """
        
        history = self.guild_states[interaction.guild.id]["queue_history"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        first_track_start_date = self.guild_states[interaction.guild.id]["first_track_start_date"]
        can_edit_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]

        if not first_track_start_date:
            await update_guild_state(self.guild_states, interaction, datetime.now(), "first_track_start_date")

        await update_guild_states(self.guild_states, interaction, (monotonic() - position, position), ("start_time", "elapsed_time"))
        
        # Update track to loop if looping is enabled
        if is_looping and track_to_loop != track:
            await update_guild_state(self.guild_states, interaction, track, "track_to_loop")

        await update_guild_state(self.guild_states, interaction, track, "current_track")

        if not position > 0 and\
            not is_looping and\
            state is None:

            history_length = len(history)
            if history_length >= self.max_history_track_limit:
                history.pop(0)

            history.append(track)

        if can_edit_status:
            await update_guild_state(self.guild_states, interaction, f"Listening to '{track['title']}'", "voice_status")
            await set_voice_status(self.guild_states, interaction)

    async def check_player_stop_flags(self, interaction: Interaction) -> int | None:
        """ Check some protection flags (`stop_flag`, `voice_client_locked`) and run some voice client checks.
         
        Returns a `PlayerStopReason` value if a check fails. """

        stop_flag = self.guild_states[interaction.guild.id]["stop_flag"]
        voice_client_locked = self.guild_states[interaction.guild.id]["voice_client_locked"]
        
        if stop_flag:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_next() called with stop_flag in guild ID {interaction.guild.id}. Ignoring.")
            
            await update_guild_state(self.guild_states, interaction, False, "stop_flag")
            return PlayerStopReason.STOP_FLAG.value
        elif voice_client_locked:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_next() called when voice client is locked in guild ID {interaction.guild.id}. Ignoring.")
            return PlayerStopReason.VC_LOCKED.value

        no_users_in_channel = await check_users_in_channel(self.guild_states, interaction)
        if no_users_in_channel:
            return PlayerStopReason.NO_USERS_IN_CHANNEL.value

        recovered_from_crash = await check_player_crash(interaction, self.client.stream_url_check_session, self.guild_states, self.play_track)
        if recovered_from_crash:
            return PlayerStopReason.CRASH_RECOVERY.value
        
    async def play_track(
            self, 
            interaction: Interaction, 
            voice_client: discord.VoiceClient, 
            track: dict[str, Any], 
            position: int=0, 
            state: str | None=None
        ) -> bool:
        """ Play a track on an available voice client. 
        
        A track must be a dict containing a `url` key that points to a valid stream readable by ffmpeg and track metadata such as `title`, `duration`, etc.. 
        
        Return a boolean indicating success. """
        
        if not voice_client.is_connected() or\
            track is None:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_track() called with invalid parameters or conditions. Ignoring.")
            return

        is_looping = self.guild_states[interaction.guild.id]["is_looping"]

        updated_track = await self.submit_track_to_player(interaction, voice_client, track, position, is_looping)
        if updated_track is not None:
            await self.update_player_states(interaction, position, updated_track, state)
            return True
        
        return False

    async def play_next(self, interaction: Interaction) -> None:
        """ Play the next track available in the queue. """
        
        if interaction.guild.id not in self.guild_states:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_next() called with non-existent guild state. Ignoring.")
            return

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        filters = self.guild_states[interaction.guild.id]["filters"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]

        send_func = interaction.channel.send if interaction.is_expired() else interaction.followup.send

        stop_reason = await self.check_player_stop_flags(interaction)
        if stop_reason is not None:
            return

        if not queue and not\
            is_looping and not\
            queue_to_loop:
            await update_guild_states(self.guild_states, interaction, (None, 0, 0), ("current_track", "start_time", "elapsed_time"))
            
            if can_update_status:
                await update_guild_state(self.guild_states, interaction, None, "voice_status")
                await set_voice_status(self.guild_states, interaction)

            await send_func("Queue is empty.")
            return
    
        if not queue and queue_to_loop:
            new_queue = deepcopy(queue_to_loop)
            await update_guild_state(self.guild_states, interaction, new_queue, "queue")

            queue = self.guild_states[interaction.guild.id]["queue"]

        track = await get_next_track(is_random, is_looping, track_to_loop, filters, queue)

        play_success = False
        try:
            await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
            play_success = await self.play_track(interaction, voice_client, track)

            await update_guild_states(self.guild_states, interaction, (0, 0), ("crash_recovery_count", "last_recovery_time"))
        finally:
            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        if not is_looping and play_success:
            await send_func(f"Now playing: **{track['title']}**")

    def handle_playback_end(self, error: Exception | None, interaction: Interaction) -> None:
        """ Handles playback end or error based on the provided voice client. """
        
        if error:
            log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        asyncio.run_coroutine_threadsafe(self.play_next(interaction), self.client.loop)