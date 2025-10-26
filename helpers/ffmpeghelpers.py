""" FFmpeg helper functions for discord.py bot """

from settings import CAN_LOG, LOGGER
from init.logutils import log_to_discord_log, log
from helpers.extractorhelpers import resolve_expired_url
from helpers.guildhelpers import update_guild_state
from helpers.timehelpers import format_to_minutes, format_to_seconds
from init.constants import PLAYBACK_END_GRACE_PERIOD

import asyncio
import discord
from discord.interactions import Interaction
from typing import Any, Awaitable
from time import monotonic

# FFmpeg options, stream validation and ffmpeg crash handler.
async def get_ffmpeg_options(position: int) -> dict[str, str]:
    """ Return a hashmap containing ffmpeg `before_options` and `options` in their respective keys.

    Additionally, seek position may be passed as function parameter `position`, which will be added after the `-ss` flag in `options`. """
    
    return {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10",
        "options": f"-vn -ss {position}"
    }

async def validate_stream(url: str) -> bool:
    """ Validate a stream URL by spawning an `ffprobe` subprocess asynchronously with a 10 second timeout.
    
    Returns True if the stream can be used for playback, otherwise False if the subprocess exits with 1, has invalid input or timeout is exhausted. """
    
    try:
        process = await asyncio.wait_for(asyncio.create_subprocess_exec(
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'stream=codec_type,codec_name,bit_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        ), timeout=10)

        stdout, _ = await process.communicate()

        output = stdout.decode().strip().splitlines()
        audio_stream_found = any(line and line == "audio" for line in output)

        return process.returncode == 0 and audio_stream_found
    except asyncio.TimeoutError:
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

        new_track = await resolve_expired_url(current_track["webpage_url"])
        if new_track is None:
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

async def check_player_crash(interaction: Interaction, guild_states: dict[str, Any], play_track_func: Awaitable) -> bool:
    """ Check if the voice player has crashed. 
    
    If so, try to restore playback at a position close to where it crashed. """
    
    current_track = guild_states[interaction.guild.id]["current_track"]
    user_forced = guild_states[interaction.guild.id]["user_interrupted_playback"]
    start_time = guild_states[interaction.guild.id]["start_time"]
    voice_client = guild_states[interaction.guild.id]["voice_client"]
    recovery_success = False

    if current_track is not None and not user_forced:
        current_time = int(monotonic() - start_time)
        track_duration_in_seconds = format_to_seconds(current_track["duration"])
        expected_elapsed_time = track_duration_in_seconds - PLAYBACK_END_GRACE_PERIOD
        
        playback_ended_unexpectedly = current_time < expected_elapsed_time

        if playback_ended_unexpectedly:
            await update_guild_state(guild_states, interaction, True, "voice_client_locked")

            approximate_resume_time = max(0, int(current_time - (track_duration_in_seconds - current_time) * 0.1))
            await interaction.channel.send(
                f"Looks like the playback crashed at **{format_to_minutes(approximate_resume_time)}** due to a faulty stream.\nAttempting to recover.."
            )

            recovery_success = await handle_player_crash(interaction, current_track, voice_client, approximate_resume_time, play_track_func)

            await update_guild_state(guild_states, interaction, False, "voice_client_locked")

            if recovery_success:
                log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Recovered player crash in guild ID {interaction.guild.id}")

                await interaction.channel.send(f"Successfully recovered playback. Now playing at **{format_to_minutes(approximate_resume_time)}**.")
                return recovery_success
            else:
                log(f"[GUILDSTATE][SHARD ID {interaction.guild.shard_id}] Failed to recover player crash in guild ID {interaction.guild.id}")
                
                await interaction.channel.send(f"Failed to recover. Skipping..")

    if user_forced:
        await update_guild_state(guild_states, interaction, False, "user_interrupted_playback")

    return recovery_success
