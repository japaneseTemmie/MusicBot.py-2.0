""" FFmpeg helper functions for discord.py bot """

from settings import CAN_LOG, LOGGER
from init.constants import (
    PLAYBACK_END_GRACE_PERIOD, 
    STREAM_VALIDATION_TIMEOUT, MAX_RETRY_COUNT, CRASH_RECOVERY_TIME_WINDOW, 
    FFMPEG_RECONNECT_TIMEOUT_SECONDS, FFMPEG_READ_WRITE_TIMEOUT_MILLIS,
    IS_STREAM_URL_ALIVE_REQUEST_HEADERS
)
from init.logutils import log_to_discord_log, log
from helpers.extractorhelpers import resolve_expired_url
from helpers.guildhelpers import update_guild_state, update_guild_states
from helpers.timehelpers import format_to_minutes, format_to_seconds

import aiohttp
import discord
from discord.interactions import Interaction
from typing import Any, Awaitable
from time import monotonic

# FFmpeg options, stream validation and ffmpeg crash handler.
async def get_ffmpeg_options(position: int) -> dict[str, str]:
    """ Return a hashmap containing ffmpeg `before_options` and `options` in their respective keys.

    Additionally, seek position may be passed as function parameter `position`, which will be added after the `-ss` flag in `options`. """
    
    return {
        "before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max {FFMPEG_RECONNECT_TIMEOUT_SECONDS} -rw_timeout {FFMPEG_READ_WRITE_TIMEOUT_MILLIS}",
        "options": f"-vn -ss {position}"
    }

async def is_stream_url_alive(url: str) -> bool:
    """ Check if a stream URL is accessible asynchronously with timeout in seconds.
    
    Returns True if the stream can be accessed, otherwise False. """

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(STREAM_VALIDATION_TIMEOUT)) as session:
            async with session.get(url, headers=IS_STREAM_URL_ALIVE_REQUEST_HEADERS) as response:
                return response.status == 200
    except Exception as e:
        log_to_discord_log(f"An error occured while validating stream URL {url}\nErr: {e}", "error", CAN_LOG, LOGGER)
        return False

async def handle_player_crash(
        interaction: Interaction, 
        current_track: dict[str, Any], 
        voice_client: discord.VoiceClient,
        resume_time: int,
        play_track_func: Awaitable
    ) -> bool:

    """ Handles unexpected stream crashes by resolving the expired URL and spawning a new ffmpeg process.
    
    Returns True for a successful recovery, False otherwise. """

    try:
        # Keep a copy of the old title and source website and replace it when re-fetching a stream to match the custom playlist track name assigned by users.
        old_title = str(current_track["title"])
        old_source_website = str(current_track["source_website"])

        log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Resolving new stream URL for crash handler in guild ID {interaction.guild.id}")

        new_track = await resolve_expired_url(current_track["webpage_url"])
        if new_track is None or not await is_stream_url_alive(new_track["url"]): # Validate new stream before passing it to play_track()
            log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Re-fetched stream in guild ID {interaction.guild.id} is invalid. Skipping..")
            return False
        
        new_track["title"] = old_title
        new_track["source_website"] = old_source_website

        await play_track_func(
            interaction, 
            voice_client, 
            new_track, 
            resume_time,
            "retry"
        )

        return True
    except Exception as e:
        log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)
        return False

async def track_ended_early(track: dict[str, Any], start_time: int) -> bool:
    """ Check if a track has ended early with a grace period to avoid false positives. """
    
    current_time = int(monotonic() - start_time)
    track_duration_in_seconds = format_to_seconds(track["duration"])
    expected_elapsed_time = track_duration_in_seconds - PLAYBACK_END_GRACE_PERIOD
    
    return current_time < expected_elapsed_time

async def recovery_count_over_limit(recovery_count: int, last_recovery_time: float) -> bool:
    """ Check if recovery count is over the limit in a time window and return True if so. Otherwise False. """
    
    current_time = monotonic()

    if recovery_count >= MAX_RETRY_COUNT and\
        current_time - last_recovery_time <= CRASH_RECOVERY_TIME_WINDOW:

        return True

    return False

async def get_approximate_resume_time(current_time: int, track_duration_in_seconds: int) -> int:
    """ Given a crash time and the total duration, return the approximate resume time. """
    
    return max(0, int(current_time - (track_duration_in_seconds - current_time) * 0.1))

async def check_player_crash(interaction: Interaction, guild_states: dict[str, Any], play_track_func: Awaitable) -> bool:
    """ Check if the voice player has crashed. 
    
    If so, try to restore playback at a position close to where it crashed. """
    
    current_track = guild_states[interaction.guild.id]["current_track"]
    user_forced = guild_states[interaction.guild.id]["user_interrupted_playback"]
    crash_recovery_count = guild_states[interaction.guild.id]["crash_recovery_count"]
    last_recovery_time = guild_states[interaction.guild.id]["last_recovery_time"]
    start_time = guild_states[interaction.guild.id]["start_time"]
    voice_client = guild_states[interaction.guild.id]["voice_client"]
    recovery_success = False

    if current_track is not None and not user_forced:
        if await track_ended_early(current_track, start_time) and not\
            await recovery_count_over_limit(crash_recovery_count, last_recovery_time):
            
            await update_guild_state(guild_states, interaction, True, "voice_client_locked")

            approximate_resume_time = await get_approximate_resume_time(int(monotonic() - start_time), format_to_seconds(current_track["duration"]))
            await interaction.channel.send(
                f"Looks like the playback crashed at **{format_to_minutes(approximate_resume_time)}** due to a faulty stream.\nAttempting to recover.."
            )

            recovery_success = await handle_player_crash(interaction, current_track, voice_client, approximate_resume_time, play_track_func)

            await update_guild_state(guild_states, interaction, False, "voice_client_locked")

            if recovery_success:
                log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Recovered player crash in guild ID {interaction.guild.id}")

                await update_guild_states(guild_states, interaction, (crash_recovery_count + 1, monotonic()), ("crash_recovery_count", "last_recovery_time"))

                await interaction.channel.send(f"Successfully recovered playback.\nNow playing at **{format_to_minutes(approximate_resume_time)}**.")
                return recovery_success
            else:
                log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Failed to recover player crash in guild ID {interaction.guild.id}")
                
                await interaction.channel.send(f"Failed to recover.\nSkipping..")

    if user_forced:
        await update_guild_state(guild_states, interaction, False, "user_interrupted_playback")

    return recovery_success
