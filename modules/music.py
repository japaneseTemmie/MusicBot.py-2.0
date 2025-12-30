""" Simple music module for discord.py bot.

Handles queue management and track playback. """

from settings import COOLDOWNS, CAN_LOG, LOGGER
from init.logutils import log, separator, log_to_discord_log
from helpers.timehelpers import format_to_minutes, format_to_seconds
from helpers.guildhelpers import (
    check_guild_state, check_channel, user_has_role, update_guild_state, update_guild_states, update_query_extraction_state,
    get_default_state
)
from helpers.queuehelpers import (
    check_input_length, check_queue_length,
    update_loop_queue_add, update_loop_queue_remove, update_loop_queue_replace,
    split, get_next_visual_track, get_previous_visual_track,
    find_track, replace_track_in_queue, reposition_track_in_queue, remove_track_from_queue, skip_tracks_in_queue,
    get_queue_indices, get_pages, add_filters, clear_filters, get_added_filter_string, get_removed_filter_string, get_active_filter_string,
    validate_page_number
)
from helpers.voicehelpers import (
    set_voice_status, close_voice_clients, check_users_in_channel
)
from helpers.extractorhelpers import fetch_query, fetch_queries, add_results_to_queue
from embedgenerator import (
    generate_added_track_embed, generate_current_track_embed, generate_epoch_embed, generate_extraction_progress_embed, generate_generic_track_embed,
    generate_queue_embed, generate_removed_tracks_embed, generate_skipped_tracks_embed,
)
from error import Error
from webextractor import SourceWebsite
from audioplayer import AudioPlayer
from bot import Bot, ShardedBot

import discord
import asyncio
from time import monotonic, time as get_unix_timestamp
from copy import deepcopy
from random import randint, shuffle
from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands

class MusicCog(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client
        self.guild_states = self.client.guild_states
        
        self.max_track_limit = self.client.max_track_limit
        self.max_history_track_limit = self.client.max_history_track_limit
        self.max_query_limit = self.client.max_query_limit
        
        self.player = AudioPlayer(self.client)

    async def cog_unload(self):
        """ Cleanup function called when destroying the cog. Cleans up voice clients and guild states. """
        
        await close_voice_clients(self.guild_states, self.client)
        self.guild_states.clear()

        log(f"[{self.__class__.__name__.upper()}] Cleaned all guild states.")
        separator()

    @app_commands.command(name="add", description="Adds a track to the queue. See entry in /help for more info.")
    @app_commands.describe(
        queries="A semicolon separated list of URLs or search queries. Refer to help entry for valid URLs.",
        search_provider="[EXPERIMENTAL] The website to search for each search query on. URLs ignore this. (default YouTube)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def add_track(self, interaction: Interaction, queries: str, search_provider: app_commands.Choice[str]=None):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked! Please wait for the other action first."):
            return

        await interaction.response.defer(thinking=True)
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        is_queue_length_ok = await check_queue_length(interaction, self.max_track_limit, queue)
        if not is_queue_length_ok:
            return
        queries_split = await check_input_length(interaction, self.max_query_limit, split(queries))

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        allowed_query_types = (
            SourceWebsite.YOUTUBE.value, 
            SourceWebsite.YOUTUBE_PLAYLIST.value, 
            SourceWebsite.YOUTUBE_SEARCH.value, 
            SourceWebsite.SOUNDCLOUD.value,
            SourceWebsite.SOUNDCLOUD_PLAYLIST.value,
            SourceWebsite.SOUNDCLOUD_SEARCH.value,
            SourceWebsite.BANDCAMP_PLAYLIST.value,
            SourceWebsite.BANDCAMP.value,
            SourceWebsite.NEWGROUNDS.value
        )
        provider = search_provider.value if search_provider else None

        found = await fetch_queries(self.guild_states, interaction, queries_split, allowed_query_types=allowed_query_types, provider=provider)

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)

        if isinstance(found, Error):
            await interaction.followup.send(found.msg)
        elif isinstance(found, list):
            added = await add_results_to_queue(interaction, found, queue, self.max_track_limit)
            
            if is_looping_queue:
                await update_loop_queue_add(self.guild_states, interaction)

            await update_guild_state(self.guild_states, interaction, False, "is_modifying")

            if not voice_client.is_playing() and\
                not voice_client.is_paused():
                await self.player.play_next(interaction)
            
            embed = generate_added_track_embed(results=added)

            await interaction.followup.send(embed=embed)

    @add_track.error
    async def handle_add_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            
            """ This only gets triggered if the bot somehow cleaned up the guild state while
            performing a task that's still not yet completed (like extracting something).
             
            Achievable by forcefully disconnecting the bot using the Discord UI while it's extracting something through the Discord client.
            Is it something to worry about? Not really. The state is clean and no errors pile up. Normally, regular users can't force disconnect
            the bot. Only through /leave (which is locked in that state). """
            
            return # Don't care just don't fill up the logs.
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="playnow", description="Plays the given query without saving it to the queue first. See entry in /help for more info.")
    @app_commands.describe(
        query="URL or search query. Refer to help entry for valid URLs.",
        search_provider="[EXPERIMENTAL] The website to search for the search query on. URLs ignore this. (default YouTube)",
        keep_current_track="Keeps the current playing track (if any) by re-inserting it at the start of the queue. (default True)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def play_track_now(self, interaction: Interaction, query: str, search_provider: app_commands.Choice[str]=None, keep_current_track: bool=True):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nPlease wait for the current action first."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if current_track is not None and keep_current_track:
            # Must check queue length before re-inserting
            is_queue_length_ok = await check_queue_length(interaction, self.max_track_limit, queue)
            is_queue_not_being_modified = await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.")

            if not is_queue_length_ok or\
                not is_queue_not_being_modified:
                return

            await update_guild_state(self.guild_states, interaction, True, "is_modifying")

        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        allowed_query_types = (
            SourceWebsite.YOUTUBE.value, 
            SourceWebsite.YOUTUBE_SEARCH.value, 
            SourceWebsite.SOUNDCLOUD.value, 
            SourceWebsite.SOUNDCLOUD_SEARCH.value, 
            SourceWebsite.BANDCAMP.value,
            SourceWebsite.NEWGROUNDS.value
        )
        provider = search_provider.value if search_provider else None
        extracted_track = await fetch_query(self.guild_states, interaction, query, allowed_query_types=allowed_query_types, provider=provider)

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)

        if isinstance(extracted_track, dict):
            if current_track is not None and keep_current_track:
                queue.insert(0, current_track)
                await update_guild_state(self.guild_states, interaction, False, "is_modifying")

            await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
            if voice_client.is_playing() or voice_client.is_paused():
                await update_guild_state(self.guild_states, interaction, True, "stop_flag")
            
            await self.player.play_track(interaction, voice_client, extracted_track)

            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

            await interaction.followup.send(f"Now playing: **{extracted_track['title']}**")
        elif isinstance(extracted_track, Error):
            await interaction.followup.send(extracted_track.msg)

    @play_track_now.error
    async def handle_play_track_now_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) and\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_states(self.guild_states, interaction, (False, False, False), ("is_modifying", "is_extracting", "voice_client_locked"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="skip", description="Skips to next track in the queue.")
    @app_commands.describe(
        amount="The amount of tracks to skip. Must be <= 25. (default 1)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def skip_track(self, interaction: Interaction, amount: int=1):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "user_interrupted_playback"))

        skipped = await skip_tracks_in_queue(queue, current_track, is_looping, amount)
        if isinstance(skipped, Error):
            await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "user_interrupted_playback"))

            await interaction.followup.send(skipped.msg)
            return

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        else:
            await self.player.play_next(interaction)

        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        if len(skipped) > 1:
            embed = generate_skipped_tracks_embed(skipped)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"Skipped track **{current_track['title']}**.")

    @skip_track.error
    async def handle_skip_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="nextinfo", description="Shows information about the next track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_next_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "is_reading_queue", True, "Queue is already being read, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        await update_guild_state(self.guild_states, interaction, True, "is_reading_queue")
        
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        filters = self.guild_states[interaction.guild.id]["filters"]
        
        next_track = await get_next_visual_track(is_random, is_looping, track_to_loop, filters, queue, queue_to_loop)
        if isinstance(next_track, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")
            
            await interaction.followup.send(next_track.msg)
            return
        
        embed = generate_generic_track_embed(next_track, "Next track")

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

        await interaction.followup.send(embed=embed)

    @show_next_track.error
    async def handle_show_next_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="previousinfo", description="Shows information about the previous track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_previous_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_reading_history", True, "Track history is already being read, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        await update_guild_state(self.guild_states, interaction, True, "is_reading_history")
    
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        history = self.guild_states[interaction.guild.id]["queue_history"]
        
        previous = await get_previous_visual_track(current_track, history)
        if isinstance(previous, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_reading_history")
            
            await interaction.followup.send(previous.msg)
            return
        
        embed = generate_generic_track_embed(previous, "Previous track")
        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")
        
        await interaction.followup.send(embed=embed)

    @show_previous_track.error
    async def handle_show_previous_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="pause", description="Pauses track playback.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def pause_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]
        start_time = self.guild_states[interaction.guild.id]["start_time"]

        if voice_client.is_paused():
            await interaction.followup.send("I'm already paused!")
            return

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

        voice_client.pause()
        await update_guild_state(self.guild_states, interaction, int(monotonic() - start_time), "elapsed_time")

        if can_update_status:
            await update_guild_state(self.guild_states, interaction, f"Listening to '{current_track['title']}' (paused)", "voice_status")
            await set_voice_status(self.guild_states, interaction)

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send("Paused track playback.")

    @pause_track.error
    async def handle_pause_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="resume", description="Resumes track playback.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def resume_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]
        elapsed_time = self.guild_states[interaction.guild.id]["elapsed_time"]
        
        if not voice_client.is_paused():
            await interaction.followup.send("I'm not paused!")
            return

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

        voice_client.resume()
        await update_guild_state(self.guild_states, interaction, int(monotonic() - elapsed_time), "start_time")

        if can_update_status:
            await update_guild_state(self.guild_states, interaction, f"Listening to '{current_track['title']}'", "voice_status")
            await set_voice_status(self.guild_states, interaction)

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send("Resumed track playback.")

    @resume_track.error
    async def handle_resume_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="stop", description="Stops the current track and resets bot state.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def stop_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))
        voice_client.stop()

        if can_update_status:
            await update_guild_state(self.guild_states, interaction, None, "voice_status")
            await set_voice_status(self.guild_states, interaction)

        self.guild_states[interaction.guild.id] = await get_default_state(voice_client, interaction.channel)

        await interaction.followup.send(f"Stopped track **{current_track['title']}** and reset bot state.")

    @stop_track.error
    async def handle_stop_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="restart", description="Restarts the current track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def restart_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        
        await self.player.play_track(interaction, voice_client, current_track, state="restart")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Restarted track **{current_track['title']}**.")

    @restart_track.error
    async def handle_restart_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="select", description="Selects a track from the queue and plays it. See entry in /help for more info.")
    @app_commands.describe(
        track_name="Name (or index, in case <by_index> is True) of the track to select.",
        by_index="Select track by its index. (default False)",
        keep_current_track="Keeps the current playing track (if any) by re-inserting it at the start of the queue. (defaut False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def select_track(self, interaction: Interaction, track_name: str, by_index: bool=False, keep_current_track: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to select.") or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_state(self.guild_states, interaction, True, "is_modifying")

        found = await find_track(track_name, queue, by_index)
        if isinstance(found, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_modifying")

            await interaction.followup.send(found.msg)
            return
        
        track_dict = queue.pop(found[1])
        if keep_current_track and current_track is not None:
            queue.insert(0, current_track)

        await update_guild_states(self.guild_states, interaction, (False, True), ("is_modifying", "voice_client_locked"))
        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        
        await self.player.play_track(interaction, voice_client, track_dict)
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Selected track **{track_dict['title']}**.")

    @select_track.error
    async def handle_select_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False, False), ("is_modifying", "voice_client_locked", "stop_flag"))

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="select-random", description="Selects a random track from the queue and plays it. See entry in /help for more info.")
    @app_commands.describe(
        keep_current_track="Keeps the current track (if any) by re-inserting it at the start of the queue. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def select_random_track(self, interaction: Interaction, keep_current_track: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to select.") or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "voice_client_locked"))

        random_track = queue.pop(randint(0, len(queue) - 1))
        if keep_current_track and current_track is not None:
            queue.insert(0, current_track)

        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        
        await self.player.play_track(interaction, voice_client, random_track)
        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "voice_client_locked"))

        await interaction.followup.send(f"Now playing: **{random_track['title']}**")

    @select_random_track.error
    async def handle_select_random_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False, False), ("is_modifying", "voice_client_locked", "stop_flag"))

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="replace", description="Replaces a track with another one. See entry in /help for more info.")
    @app_commands.describe(
        old_track_name="Name (or index, in case <by_index> is True) of the track to replace.",
        new_track_query="URL or search query. Refer to help entry for valid URLs.",
        search_provider="[EXPERIMENTAL] The provider to use for search queries. URLs ignore this. (default YouTube)",
        by_index="Replace a track by its index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def replace_track(self, interaction: Interaction, old_track_name: str, new_track_query: str, search_provider: app_commands.Choice[str]=None, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to replace.") or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        result = await replace_track_in_queue(self.guild_states, interaction, queue, old_track_name, new_track_query, by_index=by_index, provider=search_provider)
        if isinstance(result, Error):
            await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
            await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)

            await interaction.followup.send(result.msg)
            return

        if is_looping_queue:
            await update_loop_queue_replace(self.guild_states, interaction, result[1], result[0])

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)

        await interaction.followup.send(
            f"Replaced track **{result[1]['title']}** with **{result[0]['title']}**."
        )

        await check_users_in_channel(self.guild_states, interaction)

    @replace_track.error
    async def handle_replace_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="loop", description="Loops the current or specified track. Functions as a toggle.")
    @app_commands.describe(
        track_name="The track to loop's name or index (if <by_index> is True). (defaults to current track)",
        by_index="Whether or not to search for track by its index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def loop_track(self, interaction: Interaction, track_name: str=None, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            (not track_name and not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!")) or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)
        
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        if not is_looping or (is_looping and track_name):
            if track_name is not None:
                if not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
                    not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to loop."):
                    return

                found_track = await find_track(track_name, queue, by_index)

                if isinstance(found_track, Error):
                    await interaction.followup.send(found_track.msg)
                    return
                
                await update_guild_state(self.guild_states, interaction, found_track[0], "track_to_loop")
            else:
                await update_guild_state(self.guild_states, interaction, current_track, "track_to_loop")
            await update_guild_state(self.guild_states, interaction, True, "is_looping")
            
            await interaction.followup.send(f"Loop enabled!\nWill loop '**{self.guild_states[interaction.guild.id]['track_to_loop']['title']}**'.")
        else:
            await update_guild_states(self.guild_states, interaction, (None, False), ("track_to_loop", "is_looping"))
            await interaction.followup.send("Loop disabled!")

    @loop_track.error
    async def handle_loop_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="random", description="Randomizes track selection. Functions as a toggle.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def randomize_track_selection(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        is_random = self.guild_states[interaction.guild.id]["is_random"]

        if not is_random:
            await update_guild_state(self.guild_states, interaction, True, "is_random")
            await interaction.followup.send("Track randomization enabled!\nWill choose a random track from the queue at next playback.")
        else:
            await update_guild_state(self.guild_states, interaction, False, "is_random")
            await interaction.followup.send("Track randomization disabled!")

    @randomize_track_selection.error
    async def handle_randomize_track_selection_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return  
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="queueloop", description="Loops the queue. Functions as a toggle.")
    @app_commands.describe(
        include_current_track="Whether or not to keep the current track. Has no effect when disabling. (default True)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def loop_queue(self, interaction: Interaction, include_current_track: bool=True):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if not queue and not is_looping_queue:
            await interaction.followup.send("Queue is empty, cannot enable queue loop!")
            return

        if not is_looping_queue:
            new_queue = deepcopy(queue)
            if current_track is not None and include_current_track:
                new_queue.insert(0, current_track)

            await update_guild_states(self.guild_states, interaction, (True, new_queue), ("is_looping_queue", "queue_to_loop"))
            
            await interaction.followup.send(f"Queue loop enabled!\nWill loop **{len(new_queue)}** tracks at the end of the queue.")
        else:
            await update_guild_state(self.guild_states, interaction, False, "is_looping_queue")
            queue_to_loop.clear()
            
            await interaction.followup.send("Queue loop disabled!")

    @loop_queue.error
    async def handle_loop_queue_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="clear", description="Removes every track from the queue.")
    @app_commands.describe(
        clear_history="Include track history in removal. (default False)",
        clear_loop_queue="Include the loop queue in removal. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def clear_queue(self, interaction: Interaction, clear_history: bool=False, clear_loop_queue: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        track_history = self.guild_states[interaction.guild.id]["queue_history"]

        track_count = len(queue)
        track_history_count = len(track_history)

        await update_guild_state(self.guild_states, interaction, True, "is_modifying")

        queue.clear()
        if clear_history:
            track_history.clear()
        if clear_loop_queue:
            queue_to_loop.clear()

        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        await interaction.followup.send(
            f"The queue is now empty.\n"
            f"Removed **{track_count}** items from queue{f' and **{track_history_count}** items from track history' if clear_history else ''}."
        )

    @clear_queue.error
    async def handle_clear_queue_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) and\
        self.guild_states.get(interaction.guild.id, None) is None:
            await interaction.response.send_message("Cannot clear queue.\nReason: No longer in voice channel.")
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="remove", description="Removes given tracks from the queue. See entry in /help for more info.")
    @app_commands.describe(
        track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to remove.",
        by_index="Remove tracks by their index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def remove_track(self, interaction: Interaction, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to remove.") or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_copy = deepcopy(queue)
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        await update_guild_state(self.guild_states, interaction, True, "is_modifying")

        track_names_split = split(track_names)
        result = await remove_track_from_queue(track_names_split, queue, by_index)
        
        if isinstance(result, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_modifying")
            
            await interaction.followup.send(result.msg)
            return

        if is_looping_queue:
            await update_loop_queue_remove(self.guild_states, interaction, result)

        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        removed_tracks_indices = await get_queue_indices(queue_copy, result) if not by_index else track_names_split

        embed = generate_removed_tracks_embed(result, removed_tracks_indices)
        await interaction.followup.send(embed=embed)

    @remove_track.error
    async def handle_remove_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="reposition", description="Repositions a track from its original index to a new index. See entry in /help for more info.")
    @app_commands.describe(
        track_name="The name (or index, if <by_index> is True) of the track to reposition.",
        new_index="The new index of the track. Must be > 0 and <= maximum queue index.",
        by_index="Reposition a track by its index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reposition_track(self, interaction: Interaction, track_name: str, new_index: int, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to reposition.") or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]

        await update_guild_state(self.guild_states, interaction, True, "is_modifying")

        result = await reposition_track_in_queue(track_name, new_index, queue, by_index)
        if isinstance(result, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_modifying")

            await interaction.followup.send(result.msg)
            return

        await update_guild_state(self.guild_states, interaction, False, "is_modifying")
        
        await interaction.followup.send(f"Repositioned track **{result[0]['title']}** from index **{result[1]}** to **{result[2]}**.")

    @reposition_track.error
    async def handle_reposition_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="shuffle", description="Shuffles the queue randomly.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def shuffle_queue(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to shuffle.") or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        if len(queue) < 2:
            await interaction.followup.send("There are not enough tracks to shuffle! (Need 2 atleast)")
            return

        await update_guild_state(self.guild_states, interaction, True, "is_modifying")

        shuffle(queue)

        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        await interaction.followup.send("Queue shuffled successfully!")

    @shuffle_queue.error
    async def handle_shuffle_queue_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_modifying")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="seek", description="Seeks to specified position in current track. See entry in /help for more info.")
    @app_commands.describe(
        position="The position to seek to. Must be HH:MM:SS or shorter version (ex. 1:30)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def seek_to(self, interaction: Interaction, position: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        # We may want to keep this as a fallback in case the 'current_track' state is not clean. (unlikely but possible)
        if not voice_client.is_playing() and\
            not voice_client.is_paused():
            await interaction.followup.send("No track is currently playing!")
            return

        position_in_seconds = format_to_seconds(position.strip())
        if position_in_seconds is None:
            await interaction.followup.send("Invalid time format.\nBe sure to format it to **HH:MM:SS**.\nAdditionally, **MM** and **SS** must not be > **59**.")
            return
        
        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))
        await self.player.play_track(interaction, voice_client, current_track, position_in_seconds, "seek")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Set track (**{current_track['title']}**) position to **{format_to_minutes(position_in_seconds)}**.")

    @seek_to.error
    async def handle_seek_to_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="rewind", description="Rewinds the track by the specified time. See entry in /help for more info.")
    @app_commands.describe(
        time="The amount of time to rewind by. Must be HH:MM:SS or shorter version (ex. 1:50)."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def rewind_track(self, interaction: Interaction, time: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if not voice_client.is_playing() and\
            not voice_client.is_paused():
            await interaction.followup.send("No track is currently playing!")
            return

        time_in_seconds = format_to_seconds(time.strip())
        if not time_in_seconds:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        start_time = self.guild_states[interaction.guild.id]["start_time"]
        if not voice_client.is_paused():
            await update_guild_state(
                self.guild_states,
                interaction,
                min(int(monotonic() - start_time), format_to_seconds(current_track["duration"])),
                "elapsed_time"
            )
        
        rewind_time = self.guild_states[interaction.guild.id]["elapsed_time"] - time_in_seconds

        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))        
        await self.player.play_track(interaction, voice_client, current_track, rewind_time, "rewind")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        elapsed_time = self.guild_states[interaction.guild.id]["elapsed_time"]
        await interaction.followup.send(f"Rewound track (**{current_track['title']}**) by **{format_to_minutes(time_in_seconds)}**. Now at **{format_to_minutes(elapsed_time)}**")

    @rewind_track.error
    async def handle_rewind_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="forward", description="Forwards the track by the specified time. See entry in /help for more info.")
    @app_commands.describe(
        time="The amount of time to forward by. Must be HH:MM:SS or shorter version (ex. 2:00)."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def forward_track(self, interaction: Interaction, time: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        if not voice_client.is_playing() and\
            not voice_client.is_paused():
            await interaction.followup.send("No track is currently playing!")
            return

        time_in_seconds = format_to_seconds(time.strip())
        if not time_in_seconds:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        start_time = self.guild_states[interaction.guild.id]["start_time"]
        if not voice_client.is_paused():
            await update_guild_state(
                self.guild_states,
                interaction,
                min(int(monotonic() - start_time), format_to_seconds(current_track["duration"])),
                "elapsed_time"
            )

        position = self.guild_states[interaction.guild.id]["elapsed_time"] + time_in_seconds

        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))
        await self.player.play_track(interaction, voice_client, current_track, position, "forward")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Forwarded track (**{current_track['title']}**) by **{format_to_minutes(time_in_seconds)}**. Now at **{format_to_minutes(position)}**.")

    @forward_track.error
    async def handle_forward_track_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)

    @app_commands.command(name="queue", description="Shows tracks of a queue page.")
    @app_commands.describe(
        page="The queue page to view. Must be > 0."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_queue(self, interaction: Interaction, page: int):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to view.") or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "is_reading_queue", True, "I'm already reading the queue!"):
            return
        
        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]

        await update_guild_state(self.guild_states, interaction, True, "is_reading_queue")

        queue_pages = await asyncio.to_thread(get_pages, queue)
        total_pages = len(queue_pages)
        page -= 1

        result = await validate_page_number(total_pages, page)
        if isinstance(result, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")
            await interaction.followup.send(result.msg)

            return

        queue_page = queue_pages[page]
        queue_indices = await get_queue_indices(queue, queue_page)

        embed = generate_queue_embed(queue_page, queue_indices, page, len(queue_pages))

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")
        
        await interaction.followup.send(embed=embed)

    @show_queue.error
    async def handle_show_queue_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="history", description="Shows tracks of a history page.")
    @app_commands.describe(
        page="The history page to view. Must be > 0."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_history(self, interaction: Interaction, page: int):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue_history", [], "Track history is empty. Nothing to view.") or\
            not await check_guild_state(self.guild_states, interaction, "is_reading_history", True, "I'm already reading track history!"):
            return
        
        await interaction.response.defer(thinking=True)
        
        track_history = self.guild_states[interaction.guild.id]["queue_history"]
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_history")
        
        history_pages = await asyncio.to_thread(get_pages, track_history)
        total_pages = len(history_pages)
        page -= 1

        result = await validate_page_number(total_pages, page)
        if isinstance(result, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_reading_history")
            await interaction.followup.send(result.msg)

            return

        history_page = history_pages[page]
        history_indices = await get_queue_indices(track_history, history_page)

        embed = generate_queue_embed(history_page, history_indices, page, len(history_pages), True)

        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")

        await interaction.followup.send(embed=embed)

    @show_history.error
    async def handle_show_history_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
            
        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="extraction-progress", description="Show info about the current extraction process. (if any)")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_extraction(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", False, "I'm not extracting anything!"):
            return

        await interaction.response.defer(thinking=True)

        name = self.guild_states[interaction.guild.id]["progress_item_name"]
        total = self.guild_states[interaction.guild.id]["progress_total"]
        current = self.guild_states[interaction.guild.id]["progress_current"]
        website = self.guild_states[interaction.guild.id]["progress_source_website"]

        embed = generate_extraction_progress_embed(name, total, current, website)

        await interaction.followup.send(embed=embed)

    @show_extraction.error
    async def handle_show_extraction_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="stop-extraction", description="Submits a request to stop any currently running extraction process.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def stop_extraction(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", False, "I'm not extracting anything!") or\
            not await check_guild_state(self.guild_states, interaction, "can_extract", False, "I'm not extracting anything!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        await update_guild_state(self.guild_states, interaction, False, "can_extract")

        await interaction.followup.send("Successfully completed request. Extraction process should stop shortly.")

    @stop_extraction.error
    async def handle_stop_extraction_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="epoch", description="Shows the elapsed time since the first track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_start_time(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        first_track_start_date = self.guild_states[interaction.guild.id]["first_track_start_date"]

        if not first_track_start_date:
            await interaction.followup.send("Play a track first.")
            return
        
        formatted_start_time = format_to_minutes(int(get_unix_timestamp() - first_track_start_date.timestamp()))
        formatted_join_time = first_track_start_date.strftime("%d/%m/%Y @ %H:%M:%S")

        embed = generate_epoch_embed(formatted_join_time, formatted_start_time)

        await interaction.followup.send(embed=embed)

    @show_start_time.error
    async def handle_show_start_time_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="yoink", description="DMs current track info to the user who invoked the command.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def dm_track_info(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(ephemeral=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]

        embed = generate_generic_track_embed(current_track)
        
        await interaction.user.send(embed=embed)
        await interaction.followup.send("Message sent!")

    @dm_track_info.error
    async def handle_dm_track_info_error(self, interaction: Interaction, error: Exception):
        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandInvokeError):
            if isinstance(error.original, discord.errors.Forbidden):
                await send_func("I cannot send a message to you! Check your privacy settings and try again.", ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="filter", description="Applies filters for track playback.")
    @app_commands.describe(
        author="The author to match.",
        min_duration="The minimum duration range to match. Must be HH:MM:SS.",
        max_duration="The maximum duration range to match. Must be HH:MM:SS.",
        website="The website to match."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        website=[
            app_commands.Choice(name=SourceWebsite.YOUTUBE.value, value=SourceWebsite.YOUTUBE.value),
            app_commands.Choice(name=SourceWebsite.SOUNDCLOUD.value, value=SourceWebsite.SOUNDCLOUD.value),
            app_commands.Choice(name=SourceWebsite.BANDCAMP.value, value=SourceWebsite.BANDCAMP.value),
            app_commands.Choice(name=SourceWebsite.NEWGROUNDS.value, value=SourceWebsite.NEWGROUNDS.value)
        ]
    )
    @app_commands.guild_only
    async def apply_track_filters(self, interaction: Interaction, min_duration: str=None, max_duration: str=None, author: str=None, website: app_commands.Choice[str]=None):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked! Wait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        filters = self.guild_states[interaction.guild.id]["filters"]
        min_duration_in_seconds, max_duration_in_seconds = format_to_seconds(min_duration), format_to_seconds(max_duration)

        if (min_duration and min_duration_in_seconds is None) or\
            (max_duration and max_duration_in_seconds is None):
        
            await interaction.followup.send("Invalid duration.\nFormat must be **HH:MM:SS**.\nAdditionally, **MM** and **SS** must not be > **59**.")
            return
        
        added = await add_filters(filters, {
            "uploader": author,
            "min_duration": min_duration_in_seconds,
            "max_duration": max_duration_in_seconds,
            "source_website": website.value if website else None
        })

        if not added:
            await interaction.followup.send("No filters applied.")
            return

        added_count = len(added)

        await interaction.followup.send(
            f"Applied **{added_count}** track filter{'s' if added_count > 1 else ''}.\n"+
            await get_added_filter_string(filters, added)
        )

    @apply_track_filters.error
    async def handle_apply_track_filters_error(self, interaction: Interaction, error: Exception):        
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred")

    @app_commands.command(name="clear-filter", description="Clears given filters.")
    @app_commands.describe(
        min_duration="Whether or not to clear the minimum duration filter. (default False)",
        max_duration="Whether or not to clear the maximum duration filter. (default False)",
        author="Whether or not to clear the author filter. (default False)",
        website="Whether or not to clear the website filter. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def clear_track_filters(self, interaction: Interaction, min_duration: bool=False, max_duration: bool=False, author: bool=False, website: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked! Wait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        filters = self.guild_states[interaction.guild.id]["filters"]

        removed = await clear_filters(filters, {
            "uploader": author,
            "min_duration": min_duration,
            "max_duration": max_duration,
            "source_website": website
        })

        if not removed:
            await interaction.followup.send("No filters removed.")
            return
        
        removed_count = len(removed)

        await interaction.followup.send(
            f"Cleared **{removed_count}** filter{'s' if removed_count > 1 else ''}.\n"+
            await get_removed_filter_string(removed)
        )

    @clear_track_filters.error
    async def handle_clear_track_filters_error(self, interaction: Interaction, error: Exception):        
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred")

    @app_commands.command(name="view-filters", description="View the currently active filters.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_filters(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked! Wait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        filters = self.guild_states[interaction.guild.id]["filters"]

        if not filters:
            await interaction.followup.send("No filters are currently active.")
            return
        
        filter_count = len(filters)

        await interaction.followup.send(
            f"There {'are' if filter_count > 1 else 'is'} **{filter_count}** currently active filter{'s' if filter_count > 1 else ''}.\n"+
            await get_active_filter_string(filters)
        )

    @show_filters.error
    async def handle_show_filters_error(self, interaction: Interaction, error: Exception):        
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred")

    @app_commands.command(name="nowplaying", description="Shows rich information about the current track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_current_track_info(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        filters = self.guild_states[interaction.guild.id]["filters"]
        info = self.guild_states[interaction.guild.id]["current_track"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        queue_state_being_modified = self.guild_states[interaction.guild.id]["is_reading_queue"] or self.guild_states[interaction.guild.id]["is_modifying"]
        
        if voice_client.is_playing():
            fixed_elapsed_time = min(int(monotonic() - self.guild_states[interaction.guild.id]["start_time"]), format_to_seconds(info["duration"]))
            elapsed_time = format_to_minutes(fixed_elapsed_time)
        else:
            elapsed_time = format_to_minutes(int(self.guild_states[interaction.guild.id]["elapsed_time"]))
        
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        embed = generate_current_track_embed(
            info=info,
            queue=queue,
            queue_to_loop=queue_to_loop,
            track_to_loop=track_to_loop,
            elapsed_time=elapsed_time,
            looping=is_looping,
            random=is_random,
            is_looping_queue=is_looping_queue,
            is_modifying_queue=queue_state_being_modified,
            filters=filters
        )
        await interaction.followup.send(embed=embed)

    @show_current_track_info.error
    async def handle_show_current_track_info_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="allow-greetings", description="Enables/Disables the bot from greeting users that join the current voice channel.")
    @app_commands.describe(
        enable="New value of the flag."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def set_allow_greetings(self, interaction: Interaction, enable: bool):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "allow_greetings", enable, f"Setting is already {'enabled' if enable else 'disabled'}.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked! Wait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        await update_guild_state(self.guild_states, interaction, enable, "allow_greetings")

        await interaction.followup.send("Settings updated!")

    @set_allow_greetings.error
    async def handle_set_allow_greetings_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="allow-voice-status-edit", description="Enables/Disables the bot from changing the voice status to 'Listening to...'")
    @app_commands.describe(
        enable="New value of the flag."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def set_allow_voice_status_edit(self, interaction: Interaction, enable: bool):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "allow_voice_status_edit", enable, f"Setting is already {'enabled' if enable else 'disabled'}.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked! Wait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)
        
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_status = self.guild_states[interaction.guild.id]["voice_status"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_states(self.guild_states, interaction, (True, enable), ("voice_client_locked", "allow_voice_status_edit"))
        
        if not enable and voice_status is not None:
            await update_guild_state(self.guild_states, interaction, None, "voice_status")
            await set_voice_status(self.guild_states, interaction)
        elif current_track is not None and voice_status is None:
            status = f"Listening to '{current_track['title']}' {'(paused)' if voice_client.is_paused() else ''}"
            
            await update_guild_state(self.guild_states, interaction, status, "voice_status")
            await set_voice_status(self.guild_states, interaction)

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send("Settings updated!")

    @set_allow_voice_status_edit.error
    async def handle_set_voice_status_edit_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
        await send_func("An unknown error occurred.", ephemeral=True)