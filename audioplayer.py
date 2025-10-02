""" Audio player wrapper module for discord.py bot. """

from settings import CAN_LOG, LOGGER
from bot import Bot
from init.logutils import log, log_to_discord_log
from timehelpers import format_to_seconds
from helpers import (
    get_ffmpeg_options, validate_stream, resolve_expired_url, check_player_crash,
    get_next_track, check_users_in_channel, set_voice_status, update_guild_state, update_guild_states
)

import asyncio
import discord
from discord.interactions import Interaction
from typing import Any
from datetime import datetime
from time import monotonic
from copy import deepcopy

class AudioPlayer:
    def __init__(self, client: Bot):
        self.client = client
        self.guild_states = self.client.guild_states

        self.max_history_track_limit = self.client.max_history_track_limit

    async def play_track(
            self, 
            interaction: Interaction, 
            voice_client: discord.VoiceClient, 
            track: dict[str, Any], 
            position: int=0, 
            state: str | None=None
        ) -> None:
        if not voice_client.is_connected() or\
            track is None:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_track() called with invalid parameters or conditions. Ignoring.")
            return

        history = self.guild_states[interaction.guild.id]["queue_history"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        first_track_start_date = self.guild_states[interaction.guild.id]["first_track_start_date"]
        can_edit_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]
        
        # Keep a copy of the old title and source website and replace it when re-fetching a stream to match the custom playlist track name assigned by users.
        old_title = str(track["title"])
        old_source_website = str(track["source_website"])

        position = max(0, min(position, format_to_seconds(track["duration"])))
        ffmpeg_options = await get_ffmpeg_options(position)

        try:
            is_stream_valid = await validate_stream(track["url"])
            if not is_stream_valid: # This won't work anymore. Need a new stream. Slow, but required or else everything breaks :3
                track = await resolve_expired_url(track["webpage_url"])

                if track is None:
                    raise ValueError("Unrecoverable stream.")
                
                track["title"] = old_title
                track["source_website"] = old_source_website

            source = discord.FFmpegPCMAudio(track["url"], options=ffmpeg_options["options"], before_options=ffmpeg_options["before_options"])
            voice_client.stop()
            voice_client.play(source, after=lambda e: self.handle_playback_end(e, interaction))
        except Exception as e:
            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
            if is_looping:
                await update_guild_state(self.guild_states, interaction, False, "is_looping")
            
            self.handle_playback_end(e, interaction)
            return

        if not first_track_start_date:
            await update_guild_state(self.guild_states, interaction, datetime.now(), "first_track_start_date")

        await update_guild_states(self.guild_states, interaction, (monotonic() - position, position), ("start_time", "elapsed_time"))
        
        """ Update track to loop if looping is enabled
        Cases in which this is useful:
        We already have a track set to loop, we use /playnow or something that overrides this, now we need to update the track to loop."""

        if is_looping and track_to_loop != track:
            await update_guild_state(self.guild_states, interaction, track, "track_to_loop")

        await update_guild_state(self.guild_states, interaction, track, "current_track")
        
        """ Only append if the maximum amount of tracks in the track history is not reached, if
            the position is less or equal to 0, if it's not looping the current track, and we're not
            altering the current track with commands like restart, seek, etc. """

        if not position > 0 and\
            not is_looping and\
            state is None:

            if len(history) >= self.max_history_track_limit:
                history.clear()

            history.append(track)

        if can_edit_status:
            await update_guild_state(self.guild_states, interaction, f"Listening to '{track['title']}'", "voice_status")
            await set_voice_status(self.guild_states, interaction)

    async def play_next(self, interaction: Interaction) -> None:
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
        stop_flag = self.guild_states[interaction.guild.id]["stop_flag"]
        voice_client_locked = self.guild_states[interaction.guild.id]["voice_client_locked"]

        send_func = interaction.channel.send if interaction.is_expired() else interaction.followup.send

        if stop_flag:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_next() called with stop_flag. Ignoring.")
            
            await update_guild_state(self.guild_states, interaction, False, "stop_flag")
            return
        elif voice_client_locked:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_next() called when voice client is locked. Ignoring.")
            return

        no_users_in_channel = await check_users_in_channel(self.guild_states, interaction)
        if no_users_in_channel:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] play_next() called with no users in channel. Ignoring.")
            return

        recovered_from_crash = await check_player_crash(interaction, self.guild_states, self.play_track)
        if recovered_from_crash:
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Recovered player crash in guild ID {interaction.guild.id}")
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

        try:
            await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
            await self.play_track(interaction, voice_client, track)
        finally:
            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        if not is_looping:
            await send_func(f"Now playing: **{track['title']}**")

    def handle_playback_end(self, error: Exception | None, interaction: Interaction) -> None:
        if error:
            asyncio.run_coroutine_threadsafe(interaction.channel.send("An error occurred while handling playback end."), self.client.loop)
            
            log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        asyncio.run_coroutine_threadsafe(self.play_next(interaction), self.client.loop)