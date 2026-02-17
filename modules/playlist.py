""" Playlist module for discord.py bot. """

from settings import CAN_LOG, LOGGER, MAX_QUEUE_TRACK_LIMIT, MAX_QUERY_LIMIT, MAX_PLAYLIST_LIMIT
from init.constants import COOLDOWNS
from bot import Bot, ShardedBot
from managers.playlistmanager import PlaylistManager
from audioplayer import AudioPlayer
from error import Error
from webextractor import SourceWebsite, SearchWebsiteID
from init.logutils import log, log_to_discord_log
from helpers.embedhelpers import (
    generate_added_track_embed, generate_queue_page_embed, generate_removed_tracks_embed,
    generate_renamed_tracks_embed, generate_playlists_embed
)
from helpers.guildhelpers import (
    user_has_role, check_channel, check_guild_state, update_guild_state, update_guild_states, update_query_extraction_state,
)
from helpers.playlisthelpers import (
    is_playlist_locked, lock_playlist, unlock_playlist, unlock_all_playlists
)
from helpers.queuehelpers import (
    get_pages, check_input_length, check_queue_length, split, get_random_tracks_from_queue, sanitize_name, validate_page_number
)
from helpers.voicehelpers import check_users_in_channel

from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands
from copy import deepcopy
from typing import Callable, Awaitable, Any

class PlaylistCog(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client
        self.guild_states = self.client.guild_states

        self.playlist = PlaylistManager(self.client)
        self.player = AudioPlayer(self.client)

    async def handle_error(
            self, 
            interaction: Interaction, 
            error: Exception, 
            unlock_playlists: bool=True, 
            *callbacks: Callable[[], Awaitable[Any]]
        ) -> None:
        """ Handle unexpected exceptions that occur in commands. 
        
        `callbacks` may be a list of async functions to call before sending a message to the user. 
        
        By default this function unlocks all playlists after executing callbacks. """

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        if interaction.guild and interaction.guild.id not in self.guild_states:
            """ This only gets triggered if the bot somehow cleaned up the guild state while
            performing a task that's still not yet completed (like extracting something).
             
            Achievable by forcefully disconnecting the bot using the Discord UI while it's extracting something through the Discord client.
            Is it something to worry about? Not really. The state is clean and no errors pile up. Normally, regular users can't force disconnect
            the bot. Only through /leave (which is locked in that state). """
            
            return # Don't care just don't fill up the logs.
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await send_func(str(error), ephemeral=True)
            return

        for callback in callbacks:
            try:
                await callback()
            except Exception as e:
                log(f"Error in error handler callback: {e}")

        if unlock_playlists:
            await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="playlist-view", description="Shows the tracks of a playlist page.")
    @app_commands.describe(
        playlist_name="The playlist to display's name.",
        page="The page to show. Must be > 0 and <= maximum playlist index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_VIEW_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_playlist(self, interaction: Interaction, playlist_name: str, page: int):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return

        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return

        playlist_name = await sanitize_name(playlist_name)
        
        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)

        playlist = await self.playlist.get_playlist(content, playlist_name)
        
        await unlock_playlist(locked, content, playlist_name)
        
        if isinstance(playlist, Error):
            await interaction.followup.send(playlist.msg)
            return

        playlist_pages = await get_pages(playlist)
        total_pages = len(playlist_pages)
        page -= 1

        result = await validate_page_number(total_pages, page)
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return

        playlist_page = playlist_pages[page]

        embed = generate_queue_page_embed(playlist_page, page, total_pages, False, True)

        await interaction.followup.send(embed=embed)

        await check_users_in_channel(self.guild_states, interaction)

    @show_playlist.error
    async def handle_show_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-save-queue", description="Creates or updates a playlist with the current queue. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The new playlist's name.",
        add_current_track="Whether or not to add the current track, if any. (default True)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_SAVE_QUEUE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def save_queue_in_playlist(self, interaction: Interaction, playlist_name: str, add_current_track: bool=True):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return

        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name, True)

        queue = deepcopy(self.guild_states[interaction.guild.id]["queue"])
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        if not queue and not current_track:
            await unlock_playlist(locked, content, playlist_name)

            await interaction.followup.send("Queue is empty. Nothing to add.")
            return
        
        if current_track is not None and add_current_track:
            queue.insert(0, current_track)

        result = await self.playlist.add_queue(interaction, content, playlist_name, queue)
        
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            added = result[1]

            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added, True, playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @save_queue_in_playlist.error
    async def handle_save_queue_in_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-save-history", description="Creates or updates a playlist with the current history. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to create or update's name."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_SAVE_HISTORY_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def save_history_in_playlist(self, interaction: Interaction, playlist_name: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nPlease wait for the other action first.") or\
            not await check_guild_state(self.guild_states, interaction, "queue_history", [], "Queue history is empty. Nothing to add."):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        history = self.guild_states[interaction.guild.id]["queue_history"]

        if await is_playlist_locked(locked):
            await interaction.followup.send("A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name, True)

        result = await self.playlist.add_queue(interaction, content, playlist_name, history)

        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_success = result[0]
            added = result[1]

            if not isinstance(write_success, Error):
                embed = generate_added_track_embed(added, True, playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_success.msg)

    @save_history_in_playlist.error
    async def handle_save_history_in_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-save-current-track", description="Saves the current track to a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify or create's name.",
        index="The index at which the track should be placed. Must be > 0. (default last one)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_SAVE_CURRENT_TRACK_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def save_current_track_in_playlist(self, interaction: Interaction, playlist_name: str, index: int=None):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if await is_playlist_locked(locked):
            await interaction.followup.send("A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name, True)

        result = await self.playlist.place(interaction, content, playlist_name, current_track, index)
        
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            added_track = result[1]
            index = result[2]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Placed track **{added_track['title']}** at index **{index}** of playlist **{playlist_name}**.")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @save_current_track_in_playlist.error
    async def handle_save_current_in_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-select", description="Selects tracks in a playlist and adds them to the queue. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The name of the playlist to select.",
        clear_current_queue="Whether or not to clear the current queue. (default False)",
        range_start="The range to start track selection from. (defaults to start)",
        range_end="The range where track selection will stop. (defaults to end)",
        random_order="Whether or not tracks in the range should be randomly selected. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_SELECT_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def select_playlist(self, interaction: Interaction, playlist_name: str, range_start: int=1, range_end: int=None, random_order: bool=False, clear_current_queue: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]

        if clear_current_queue:
            queue.clear()
            queue_to_loop.clear()

        is_queue_length_ok = await check_queue_length(interaction, MAX_QUEUE_TRACK_LIMIT, queue)
        if not is_queue_length_ok:
            return

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        
        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)
        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        result = await self.playlist.select(self.guild_states, MAX_QUEUE_TRACK_LIMIT, interaction, content, playlist_name, range_start, range_end, random_order)
        
        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        await unlock_playlist(locked, content, playlist_name)
        
        if isinstance(result, list):
            if not voice_client.is_playing() and\
                not voice_client.is_paused():
                await self.player.play_next(interaction)

            embed = generate_added_track_embed(result)
            await interaction.followup.send(embed=embed)
        elif isinstance(result, Error):
            await interaction.followup.send(result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @select_playlist.error
    async def handle_select_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(
            interaction, 
            error, 
            True,
            lambda: update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting")),
            lambda: update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        )

    @app_commands.command(name="playlist-create", description="Creates a new empty playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The new playlist's name. Must be < 50 (default) characters."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_CREATE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def create_playlist(self, interaction: Interaction, playlist_name: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name, True)

        result = await self.playlist.create(interaction, content, playlist_name)

        await unlock_playlist(locked, content, playlist_name)
            
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        else:
            await interaction.followup.send(f"Playlist **{playlist_name}** has been created.")

        await check_users_in_channel(self.guild_states, interaction)

    @create_playlist.error
    async def handle_create_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-delete", description="Deletes a saved playlist or its contents. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to delete's name.",
        erase_contents_only="Whether or not to erase only the contents. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_DELETE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def delete_playlist(self, interaction: Interaction, playlist_name: str, erase_contents_only: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)

        result = await self.playlist.delete(interaction, content, playlist_name, erase_contents_only)
        
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            removed_tracks = result[1]
            removed_tracks_length = len(removed_tracks)

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"**{removed_tracks_length}** {'tracks have' if removed_tracks_length > 1 else 'track has'} been removed from playlist **{playlist_name}**.")
            else:
                await interaction.followup.send(write_result.msg)
        else:
            await interaction.followup.send(f"Playlist **{playlist_name}** has been deleted.")

        await check_users_in_channel(self.guild_states, interaction)

    @delete_playlist.error
    async def handle_delete_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-remove", description="Remove specified track(s) from a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to remove tracks from's name.",
        track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to remove.",
        by_index="Remove tracks by their index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_REMOVE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def remove_playlist_track(self, interaction: Interaction, playlist_name: str, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)

        track_names_split = split(track_names)
        result = await self.playlist.remove(interaction, content, playlist_name, track_names_split, by_index)

        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            removed_tracks = result[1]

            if not isinstance(write_result, Error):
                embed = generate_removed_tracks_embed(removed_tracks, True, playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @remove_playlist_track.error
    async def handle_remove_playlist_track_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-reset", description="Deletes all playlists saved in the current guild. See entry in /help for more info.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_RESET_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def delete_all_playlists(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
                
        result = await self.playlist.delete_all(interaction, locked)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        else:
            await interaction.followup.send('Structure rewritten successfully.')

        await check_users_in_channel(self.guild_states, interaction)

    @delete_all_playlists.error
    async def handle_delete_all_playlists_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-rename", description="Renames a playlist to a new specified name. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to rename's name.",
        new_playlist_name="New name to assign to the playlist. Must be <= 50 (default) characters."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_RENAME_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def rename_playlist(self, interaction: Interaction, playlist_name: str, new_playlist_name: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        new_playlist_name = await sanitize_name(new_playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)

        result = await self.playlist.rename(interaction, content, playlist_name, new_playlist_name)
        
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            old_name = result[1]
            new_name = result[2]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Renamed playlist **{old_name}** to **{new_name}**.")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @rename_playlist.error
    async def handle_rename_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-replace", description="Replaces a playlist track with a different one. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        old_track_name="The name (or index, if <by_index> is True) of the track to replace.",
        new_track_query="URL or search query. Refer to help entry for valid URLs.",
        search_provider="[EXPERIMENTAL] The provider used for search query. URLs ignore this. (default YouTube)",
        by_index="Replace a track by its index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_REPLACE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name=SourceWebsite.SOUNDCLOUD_SEARCH.value, value=SearchWebsiteID.SOUNDCLOUD_SEARCH.value),
            app_commands.Choice(name=SourceWebsite.YOUTUBE_SEARCH.value, value=SearchWebsiteID.YOUTUBE_SEARCH.value)
        ]
    )
    @app_commands.guild_only
    async def replace_playlist_track(
            self, 
            interaction: Interaction, 
            playlist_name: str, 
            old_track_name: str, 
            new_track_query: str, 
            search_provider: app_commands.Choice[str]=None, 
            by_index: bool=False
        ):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it."):
            return

        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        provider = search_provider.value if search_provider else SearchWebsiteID.YOUTUBE_SEARCH.value

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        result = await self.playlist.replace(self.guild_states, interaction, content, playlist_name, old_track_name, new_track_query, provider, by_index)
        
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            old_track = result[1]
            new_track = result[2]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Replaced track **{old_track['title']}** with track **{new_track['title']}**")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @replace_playlist_track.error
    async def handle_replace_playlist_track_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(
            interaction, 
            error, 
            True,
            lambda: update_guild_state(self.guild_states, interaction, False, "is_extracting"),
            lambda: update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        )

    @app_commands.command(name="playlist-reposition", description="Repositions a playlist track to a new index. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        track_name="The name (or index, in case <by_index> is True) of the track to reposition.",
        new_index="The new index of the track. Must be > 0 and < maximum playlist index.",
        by_index="Reposition a track by its index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_REPOSITION_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reposition_playlist_track(self, interaction: Interaction, playlist_name: str, track_name: str, new_index: int, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)

        result = await self.playlist.reposition(interaction, content, playlist_name, track_name, new_index, by_index)
        
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            track = result[1]
            old_index = result[2]
            new_index = result[3]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Repositioned track **{track['title']}** from index **{old_index}** to **{new_index}**")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @reposition_playlist_track.error
    async def handle_reposition_playlist_track_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-add", description="Adds specified tracks to a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        queries="A semicolon separated list of URLs or search queries. Refer to help entry for valid URLs.",
        search_provider="[EXPERIMENTAL] The provider to use for search queries. URLs ignore this. (default YouTube)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_ADD_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name=SourceWebsite.SOUNDCLOUD_SEARCH.value, value=SearchWebsiteID.SOUNDCLOUD_SEARCH.value),
            app_commands.Choice(name=SourceWebsite.YOUTUBE_SEARCH.value, value=SearchWebsiteID.YOUTUBE_SEARCH.value)
        ]
    )
    @app_commands.guild_only
    async def add_playlist_track(self, interaction: Interaction, playlist_name: str, queries: str, search_provider: app_commands.Choice[str]=None):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it."):
            return

        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        provider = search_provider.value if search_provider else SearchWebsiteID.YOUTUBE_SEARCH.value

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name, True)
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        queries_split = await check_input_length(interaction, MAX_QUERY_LIMIT, split(queries))

        allowed_query_types = (
            SourceWebsite.YOUTUBE.value, 
            SourceWebsite.YOUTUBE_SEARCH.value, 
            SourceWebsite.SOUNDCLOUD.value, 
            SourceWebsite.SOUNDCLOUD_SEARCH.value, 
            SourceWebsite.NEWGROUNDS.value,
            SourceWebsite.BANDCAMP.value
        )
        result = await self.playlist.add(self.guild_states, interaction, content, playlist_name, queries_split, allowed_query_types, provider)

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            added_tracks = result[1]
            
            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added_tracks, True, playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @add_playlist_track.error
    async def handle_add_playlist_track_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(
            interaction, 
            error, 
            True,
            lambda: update_guild_state(self.guild_states, interaction, False, "is_extracting"),
            lambda: update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        ) 

    @app_commands.command(name="playlist-copy", description="Copies a playlist to a new/existing one. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to duplicate's name.",
        target_playlist_name="The new playlist's name. Must not be the same as the playlist to duplicate's name."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_COPY_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def copy_playlist(self, interaction: Interaction, playlist_name: str, target_playlist_name: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, True) or\
            not await check_channel(self.guild_states, interaction):
            return

        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send("A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        target_playlist_name = await sanitize_name(target_playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)
        await lock_playlist(content, locked, target_playlist_name, True)
        
        result = await self.playlist.copy(interaction, content, playlist_name, target_playlist_name)

        await unlock_playlist(locked, content, playlist_name)
        await unlock_playlist(locked, content, target_playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            added = result[1]

            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added, True, target_playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

    @copy_playlist.error
    async def handle_copy_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-move", description="Merges a playlist with another one. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The name of the playlist to merge.",
        target_playlist_name="The name of the playlist to move contents to."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_MOVE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def move_playlist(self, interaction: Interaction, playlist_name: str, target_playlist_name: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send("A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        target_playlist_name = await sanitize_name(target_playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)
        await lock_playlist(content, locked, target_playlist_name, True)

        result = await self.playlist.move(interaction, content, playlist_name, target_playlist_name)

        await unlock_playlist(locked, content, playlist_name)
        await unlock_playlist(locked, content, target_playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_success = result[0]
            moved = result[1]

            if not isinstance(write_success, Error):
                embed = generate_added_track_embed(moved, True, target_playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_success.msg)

    @move_playlist.error
    async def handle_move_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-copy-tracks", description="Copies track(s) from a playlist to a new/existing one. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to copy tracks from's name",
        target_playlist_name="The playlist to copy tracks to's name.",
        track_names="A semicolon separated list of track names (or indices, if <by_index> is true) to copy.",
        by_index="Copy tracks by their index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_COPY_TRACKS_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def copy_playlist_tracks(self, interaction: Interaction, playlist_name: str, target_playlist_name: str, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        
        if await is_playlist_locked(locked):
            await interaction.followup.send("A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        target_playlist_name = await sanitize_name(target_playlist_name)
        
        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)
        await lock_playlist(content, locked, target_playlist_name, True)
        
        result = await self.playlist.copy_items(interaction, content, split(track_names), playlist_name, target_playlist_name, by_index)
        
        await unlock_playlist(locked, content, playlist_name)
        await unlock_playlist(locked, content, target_playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            added = result[1]

            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added, True, target_playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)
        
    @copy_playlist_tracks.error
    async def handle_copy_playlist_tracks_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-move-tracks", description="Merges tracks from a playlist with another one. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The name of the playlist to move tracks from.",
        target_playlist_name="The name of the playlist to move tracks to.",
        track_names="A semicolon separated list of track names (or indices, if <by_index> is True) to move.",
        by_index="Whether or not to move tracks by their indices."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_MOVE_TRACKS_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def move_playlist_tracks(self, interaction: Interaction, playlist_name: str, target_playlist_name: str, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)
        target_playlist_name = await sanitize_name(target_playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)
        await lock_playlist(content, locked, target_playlist_name, True)

        result = await self.playlist.move_items(interaction, content, split(track_names), playlist_name, target_playlist_name, by_index)

        await unlock_playlist(locked, content, playlist_name)
        await unlock_playlist(locked, content, target_playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            moved = result[1]

            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(moved, True, target_playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

    @move_playlist_tracks.error
    async def handle_move_playlist_tracks_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-fetch-tracks", description="Adds tracks from a playlist to the queue. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to fetch tracks from's name.",
        track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to fetch.",
        by_index="Fetch tracks by their index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_FETCH_TRACKS_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def fetch_playlist_track(self, interaction: Interaction, playlist_name: str, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        queries_split = await check_input_length(interaction, MAX_QUERY_LIMIT, split(track_names))
        is_queue_length_ok = await check_queue_length(interaction, MAX_QUEUE_TRACK_LIMIT, queue)
        if not is_queue_length_ok:
            return

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)
        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))        

        result = await self.playlist.fetch(self.guild_states, MAX_QUEUE_TRACK_LIMIT, interaction, content, playlist_name, queries_split, by_index=by_index)

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, list):
            if not voice_client.is_playing() and\
                not voice_client.is_paused():
                await self.player.play_next(interaction)

            embed = generate_added_track_embed(result)
            await interaction.followup.send(embed=embed)

        await check_users_in_channel(self.guild_states, interaction)

    @fetch_playlist_track.error
    async def handle_fetch_playlist_track_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(
            interaction, 
            error, 
            True,
            lambda: update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting")),
            lambda: update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        )

    @app_commands.command(name="playlist-fetch-random-tracks", description="Fetches random tracks from a specified playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to get tracks from's name.",
        amount="The amount of random tracks to fetch. (default 1)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_FETCH_RANDOM_TRACKS_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def choose_random_playlist_tracks(self, interaction: Interaction, playlist_name: str, amount: int=1):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_modifying", True, "The queue is currently being modified, please wait.") or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it.") or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", True, "Voice state currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        is_queue_length_ok = await check_queue_length(interaction, MAX_QUEUE_TRACK_LIMIT, queue) 
        if not is_queue_length_ok:
            return

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)

        playlist = await self.playlist.get_playlist(content, playlist_name)
        if isinstance(playlist, Error):
            await unlock_playlist(locked, content, playlist_name)

            await interaction.followup.send(playlist.msg)
            return
        
        random_tracks = await get_random_tracks_from_queue(playlist, amount)
        if isinstance(random_tracks, Error):
            await unlock_playlist(locked, content, playlist_name)

            await interaction.followup.send(random_tracks.msg)
            return
        
        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        result = await self.playlist.fetch(self.guild_states, MAX_QUEUE_TRACK_LIMIT, interaction, content, playlist_name, random_tracks, True)

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, list):
            if not voice_client.is_playing() and\
                not voice_client.is_paused():
                await self.player.play_next(interaction)

            embed = generate_added_track_embed(result)
            await interaction.followup.send(embed=embed)

        await check_users_in_channel(self.guild_states, interaction)

    @choose_random_playlist_tracks.error
    async def handle_choose_random_playlist_tracks(self, interaction: Interaction, error: Exception):
        await self.handle_error(
            interaction, 
            error, 
            True,
            lambda: update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting")),
            lambda: update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        )

    @app_commands.command(name="playlist-import", description="Imports a playlist from a supported website. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to add the tracks to's name.",
        query="A supported playlist URL."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_IMPORT_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def add_playlist(self, interaction: Interaction, playlist_name: str, query: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", True, "Please wait for the current extraction process to finish. Use `/extraction-progress` to see the status or `/stop-extraction` to stop it."):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name, True)
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        allowed_query_types = (
            SourceWebsite.YOUTUBE_PLAYLIST.value,
            SourceWebsite.SOUNDCLOUD_PLAYLIST.value,
            SourceWebsite.BANDCAMP_PLAYLIST.value
        )
        result = await self.playlist.add(self.guild_states, interaction, content, playlist_name, [query], allowed_query_types=allowed_query_types)

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            added_tracks = result[1]
            
            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added_tracks, True, playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @add_playlist.error
    async def handle_add_playlist_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(
            interaction, 
            error, 
            True,
            lambda: update_guild_state(self.guild_states, interaction, False, "is_extracting"),
            lambda: update_query_extraction_state(self.guild_states, interaction, 0, 0, None, None)
        )

    @app_commands.command(name="playlist-rename-tracks", description="Renames tracks to new names. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        old_track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to rename.",
        new_track_names="A semicolon separated list of new names to assign to each old name.",
        by_index="Rename tracks by their index. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_RENAME_TRACKS_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def rename_playlist_track(self, interaction: Interaction, playlist_name: str, old_track_names: str, new_track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        playlist_name = await sanitize_name(playlist_name)

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        await lock_playlist(content, locked, playlist_name)

        old_track_names_split = split(old_track_names)
        new_track_names_split = split(new_track_names)
        result = await self.playlist.rename_item(interaction, content, playlist_name, old_track_names_split, new_track_names_split, by_index)
        
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
        elif isinstance(result, tuple):
            write_result = result[0]
            modified_tracks = result[1]

            if not isinstance(write_result, Error):
                embed = generate_renamed_tracks_embed(modified_tracks, playlist_name)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)
        
        await check_users_in_channel(self.guild_states, interaction)

    @rename_playlist_track.error
    async def handle_rename_playlist_track_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error)

    @app_commands.command(name="playlist-get-saved", description="Shows saved playlists for this guild.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PLAYLIST_GET_SAVED_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_saved_playlists(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return

        content = await self.playlist.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        result = await self.playlist.get_available(content)
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return

        remaining_slots = MAX_PLAYLIST_LIMIT - len(result)

        embed = generate_playlists_embed(result, remaining_slots)

        await interaction.followup.send(embed=embed)

        await check_users_in_channel(self.guild_states, interaction)

    @show_saved_playlists.error
    async def handle_show_saved_playlists_error(self, interaction: Interaction, error: Exception):
        await self.handle_error(interaction, error, False)