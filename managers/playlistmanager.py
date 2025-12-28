""" Playlist manager module for discord.py bot.

Includes a few methods for managing playlists
and fetching tracks from them. """

from settings import ENABLE_FILE_BACKUPS, PLAYLIST_FILE_CACHE, PLAYLIST_LOCKS
from helpers.playlisthelpers import (
    has_playlists, playlist_exists, is_playlist_empty, is_content_full,
    is_playlist_full, cleanup_locked_playlists
)
from helpers.queuehelpers import (
    remove_track_from_queue, reposition_track_in_queue, replace_track_in_queue, rename_tracks_in_queue, replace_data_with_playlist_data,
    update_loop_queue_add, get_tracks_from_queue, place_track_in_playlist, name_exceeds_length
)
from helpers.extractorhelpers import fetch_queries, add_results_to_queue
from helpers.guildhelpers import read_guild_json, write_guild_json
from error import Error
from bot import Bot, ShardedBot

from discord import app_commands
from discord.interactions import Interaction
from typing import Any
from copy import deepcopy
from random import shuffle

class PlaylistManager:
    def __init__(self, client: Bot | ShardedBot):
        self.client = client

        self.max_limit = self.client.max_playlist_limit
        self.max_item_limit = self.client.max_playlist_item_limit
        self.max_name_length = self.client.max_playlist_name_length

    async def read(self, interaction: Interaction) -> dict[str, list] | Error:
        """ Safely read the content of a guild's playlist file.

        Cache the content of a successful read.

        If successful, returns the playlist structure. Error otherwise. """
        
        return await read_guild_json(
            interaction, 
            "playlists.json", 
            PLAYLIST_LOCKS, 
            PLAYLIST_FILE_CACHE, 
            "Playlist reading temporarily disabled.", 
            "Failed to read playlist contents."
        )

    async def write(self, interaction: Interaction, content: dict[str, list], backup: dict[str, list]=None) -> bool | Error:
        """ Safely write the modified content of a playlist function to the guild's `playlists.json` file.

        Cache new content if written successfully.
        
        Returns a boolean [True] or Error. """
        
        return await write_guild_json(
            interaction, 
            content, 
            "playlists.json", 
            PLAYLIST_LOCKS, 
            PLAYLIST_FILE_CACHE, 
            "Playlist writing temporarily disabled.", 
            "Failed to apply changes to playlist.",
            backup
        )

    async def get_playlist(self, content: dict[str, list], playlist_name: str) -> list[dict[str, Any]] | Error:
        """ Reads the given playlist.

        If successful, returns a list of tracks, otherwise, Error. """
        
        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist.")
        
        playlist = content[playlist_name]

        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty.")

        return playlist

    async def get_available(self, content: dict[str, list]) -> list[str] | Error:
        """ Get all available playlists' names.

        If successful, returns a list of strings, otherwise Error. """

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        return [key for key in content.keys()]

    async def create(self, interaction: Interaction, content: dict[str, list], playlist_name: str) -> bool | Error:
        """ Creates a playlist.

        If successful, returns a boolean, otherwise, Error. """
        
        if await name_exceeds_length(self.max_name_length, playlist_name):
            return Error(f"Playlist name is too long! Must be <= **{self.max_name_length}** characters.")

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** already exists!")

        if await is_content_full(self.max_limit, content):
            return Error(f"Maximum playlist limit of **{self.max_limit}** reached! Please delete a playlist to free a slot.")

        content[playlist_name] = []

        success = await self.write(interaction, content, backup)
        
        return success

    async def delete(
            self, 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            contents_only: bool
        ) -> bool | Error | tuple[bool | Error, list[dict[str, Any]]]:
        """ Deletes a playlist.

        If successful, returns a boolean or Error if `contents_only` is True, otherwise
        a tuple with a boolean or Error indicating write success and removed tracks. """

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        if contents_only:
            playlist = content[playlist_name]

            if await is_playlist_empty(playlist):
                return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot delete contents.")
            
            previous_contents = deepcopy(playlist)
            playlist.clear()

            success = await self.write(interaction, content, backup)
            return success, previous_contents
        else:
            del content[playlist_name]

            success = await self.write(interaction, content, backup)
            return success

    async def remove(
            self,
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            tracks_to_remove: list[str], 
            by_index: bool=False
        ) -> tuple[bool | Error, list[dict[str, Any]], list[dict[str, Any]]] | Error:
        """ Removes given tracks from a playlist.

        If successful, returns a tuple with a boolean or Error indicating
        write success [0], the list of removed tracks [1], and the playlist queue itself before track removal. Error otherwise. """
        
        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")
    
        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        playlist = content[playlist_name]
        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot remove tracks.")
        
        playlist_copy = deepcopy(playlist)

        found = await remove_track_from_queue(tracks_to_remove, playlist, by_index)
        if isinstance(found, Error):
            return found
        
        success = await self.write(interaction, content, backup)
        
        return success, found, playlist_copy

    async def replace(
            self,
            guild_states: dict[str, Any],
            interaction: Interaction,
            content: dict[str, list],
            playlist_name: str,
            old: str,
            new: str,
            provider: app_commands.Choice | None=None,
            by_index: bool=False
        ) -> tuple[bool | Error, dict[str, Any], dict[str, Any]] | Error:
        """ Replaces a playlist track with an extracted track from a given query.

        If successful, returns a tuple with a boolean or Error indicating
        write success [0], the old track [1] and the new track [2]. Error otherwise."""

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        playlist = content[playlist_name]

        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot replace track.")

        result = await replace_track_in_queue(guild_states, interaction, playlist, old, new, provider, True, by_index)
        if isinstance(result, Error):
            return result

        success = await self.write(interaction, content, backup)

        return success, result[1], result[0]

    async def reposition(
            self, 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            track: str, 
            index: int, 
            by_index: bool=False
        ) -> tuple[bool | Error, dict[str, Any], int, int] | Error:
        """ Repositions a playlist track from its current index to the given index.

        If successful, returns a tuple with a boolean or Error indicating
        write success [0], the repositioned track [1], old index [2], and new index [3]. Error otherwise. """
        
        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")
        
        playlist = content[playlist_name]

        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot reposition track.")
        
        result = await reposition_track_in_queue(track, index, playlist, by_index)
        if isinstance(result, Error):
            return result

        success = await self.write(interaction, content, backup)

        return success, result[0], result[1], result[2]

    async def select(
            self, 
            guild_states: dict[str, Any], 
            max_track_limit: int, 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            range_start: int=1, 
            range_end: int | None=None,
            random_order: bool=False
        ) -> list[dict[str, Any]] | Error:
        """ Adds all playlist tracks from `range_start` to `range_end` to the queue.

        If successful, returns a list of added tracks. Error otherwise. """
        
        playlist = await self.get_playlist(content, playlist_name)
        if isinstance(playlist, Error):
            return playlist
        
        playlist_length = len(playlist)

        if range_end is None:
            range_end = playlist_length
        
        if (range_start > playlist_length or range_start < 1) or (range_end > playlist_length or range_end < 1):
            return Error("Range start or end must be > **0** and < **playlist length**.")
        elif range_start > range_end:
            return Error("Invalid start or end range.\n`range_start` must be <= `range_end`.")

        range_start -= 1

        tracks_to_fetch = playlist[range_start:range_end]
        if random_order:
            shuffle(tracks_to_fetch)
        
        query_names = [track["title"] for track in tracks_to_fetch]

        found = await fetch_queries(guild_states, interaction, tracks_to_fetch, query_names)

        if isinstance(found, list):
            queue = guild_states[interaction.guild.id]["queue"]
            is_looping_queue = guild_states[interaction.guild.id]["is_looping_queue"]

            await replace_data_with_playlist_data(found, tracks_to_fetch)
            added = await add_results_to_queue(interaction, found, queue, max_track_limit)

            if is_looping_queue:
                await update_loop_queue_add(guild_states, interaction)

            return added
        elif isinstance(found, Error):
            return found

    async def fetch(
            self, 
            guild_states: dict[str, Any], 
            max_track_limit: int, 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            tracks: list[dict[str, Any]] | list[str], 
            treat_tracks_as_dicts: bool=False, 
            by_index: bool=False
        ) -> list[dict[str, Any]] | Error:
        """ Adds requested queries from a given playlist to the queue.

        If successful, returns a list of added tracks. Error otherwise. """
        
        playlist = await self.get_playlist(content, playlist_name)
        if isinstance(playlist, Error):
            return playlist

        if not treat_tracks_as_dicts:
            tracks_to_fetch = await get_tracks_from_queue(tracks, playlist, by_index)

            if isinstance(tracks_to_fetch, Error):
                return tracks_to_fetch
        else:
            tracks_to_fetch = tracks
        
        query_names = [track["title"] for track in tracks_to_fetch]
        found = await fetch_queries(guild_states, interaction, tracks_to_fetch, query_names)

        if isinstance(found, list):
            queue = guild_states[interaction.guild.id]["queue"]
            is_looping_queue = guild_states[interaction.guild.id]["is_looping_queue"]

            await replace_data_with_playlist_data(found, tracks_to_fetch)
            added = await add_results_to_queue(interaction, found, queue, max_track_limit)

            if is_looping_queue:
                await update_loop_queue_add(guild_states, interaction)

            return added
        elif isinstance(found, Error):
            return found

    async def add_queue(
            self, 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            queue: list[dict[str, Any]]
        ) -> tuple[bool | Error, list[dict[str, Any]]] | Error:
        """ Adds a list of extracted queries to a playlist.

        If successful, returns a tuple with a boolean or Error indicating
        write success [0], and a list containing the added tracks [1]. Error otherwise. """

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await playlist_exists(content, playlist_name):
            if await is_content_full(self.max_limit, content):
                return Error(f"Maximum playlist limit of **{self.max_limit}** reached! Please delete a playlist to free a slot.")

            if await name_exceeds_length(self.max_name_length, playlist_name):
                return Error(f"Name **{playlist_name[:self.max_name_length]}**.. is too long! Must be <= **{self.max_name_length}** characters.")

            content[playlist_name] = []
        elif await is_playlist_full(self.max_item_limit, content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** has reached the **{self.max_item_limit}** track limit!\nCannot add more tracks.")

        playlist = content[playlist_name]
        to_add = [{
                'title': track['title'],
                'uploader': track["uploader"],
                'duration': track['duration'],
                'webpage_url': track["webpage_url"],
                'source_website': track["source_website"]
            } for track in queue]

        added = await add_results_to_queue(interaction, to_add, playlist, self.max_item_limit)

        success = await self.write(interaction, content, backup)
        
        return success, added

    async def add(
            self, 
            guild_states: dict[str, Any], 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            queries: list[str], 
            allowed_query_types: tuple[str], 
            provider: app_commands.Choice | None=None
        ) -> tuple[bool | Error, list[dict[str, Any]]] | Error:
        """ Adds a list of queries to the given playlist.

        If successful, returns same types as `add_queue()`. With the addition of extraction Errors. """

        # Avoid returning these errors when using add_queue() to not waste bandwidth
        if await is_playlist_full(self.max_item_limit, content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** has reached the maximum track limit of **{self.max_item_limit}**!\nCannot add more tracks.")
        
        if await is_content_full(self.max_limit, content) and not await playlist_exists(content, playlist_name):
            return Error(f"Maximum playlist limit of **{self.max_limit}** reached! Please delete a playlist to free a slot.")

        provider = provider.value if provider else None
        found = await fetch_queries(guild_states, interaction, queries, allowed_query_types=allowed_query_types, provider=provider)

        if isinstance(found, list):
            success = await self.add_queue(interaction, content, playlist_name, found)

            return success
        else:
            return found

    async def delete_all(self, interaction: Interaction, locked: dict[str, bool]) -> bool | Error:
        """ Deletes every playlist saved in the current guild.

        Returns a boolean or Error. """
        
        success = await self.write(interaction, {})
        await cleanup_locked_playlists({}, locked)

        return success

    async def rename(
            self, 
            interaction: Interaction, 
            content: dict[str, list], 
            orig_playlist_name: str, 
            new_playlist_name: str
        ) -> tuple[bool | Error, str, str] | Error:
        """ Renames a playlist to a new given name.

        If successful, returns a tuple with a boolean or Error indicating
        write success [0], old name [1], and new name [2]. Error otherwise. """
        
        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        if not await playlist_exists(content, orig_playlist_name):
            return Error(f"Playlist **{orig_playlist_name[:self.max_name_length]}** does not exist!")

        if await name_exceeds_length(self.max_name_length, new_playlist_name):
            return Error(f"New name **{new_playlist_name[:self.max_name_length]}**.. is too long! Must be < **{self.max_name_length}** characters.")

        if new_playlist_name.lower().replace(" ", "") == orig_playlist_name.lower().replace(" ", ""):
            return Error(f"Cannot rename a playlist (**{orig_playlist_name[:self.max_name_length]}**) to the same name (**{new_playlist_name[:self.max_name_length]}**).")

        playlists = content.items()
        content = {new_playlist_name if key == orig_playlist_name else key: value for key, value in playlists}

        success = await self.write(interaction, content, backup)

        return success, orig_playlist_name, new_playlist_name
        
    async def rename_item(
            self, 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            tracks_to_rename: list[str], 
            new_track_names: list[str], 
            by_index: bool
        ) -> tuple[bool | Error, list[tuple[dict, str]], list[dict[str, Any]]] | Error:
        """ Bulk edits track names to new given ones.

        if successful, returns a tuple with a boolean or Error indicating write success, a list of tuples with
        old track [0] and the new name [1], and a copy of the old playlist queue [2]. Error otherwise. """
        
        if not await has_playlists(content):
            return Error("This guild does not have any saved playlists.")

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)
        playlist = content[playlist_name]

        if await is_playlist_empty(playlist):
            return Error(f"Playlist {playlist_name[:self.max_name_length]} is empty. Cannot rename tracks.")
        
        playlist_copy = deepcopy(playlist)

        found = await rename_tracks_in_queue(self.max_name_length, playlist, tracks_to_rename, new_track_names, by_index)
        if isinstance(found, Error):
            return found

        success = await self.write(interaction, content, backup)
        
        return success, found, playlist_copy
    
    async def place(
            self, 
            interaction: Interaction, 
            content: dict[str, list], 
            playlist_name: str, 
            track: dict[str, Any], 
            index: int | None
        ) -> tuple[bool | Error, dict[str, Any], int] | Error:
        """ Place a track at a specific index or append it (index=None).

        if successful, returns a tuple with a boolean or Error indicating
        write success [0], added track [1], and its new index [2]. Error otherwise. """
        
        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)
        
        if not await playlist_exists(content, playlist_name):
            if await is_content_full(self.max_limit, content):
                return Error(f"Maximum playlist limit of **{self.max_limit}** reached! Please delete a playlist to free a slot.")
            
            if await name_exceeds_length(self.max_name_length, playlist_name):
                return Error(f"Name **{playlist_name[:self.max_name_length]}**.. is too long! Must be <= **{self.max_name_length}** characters.")

            content[playlist_name] = []
            
        playlist = content[playlist_name]

        result = await place_track_in_playlist(playlist, index, track)
        if isinstance(result, Error):
            return result

        success = await self.write(interaction, content, backup)

        return success, result[0], result[1]
    
    async def copy(self, interaction: Interaction, content: dict[str, list], source_playlist_name: str, target_playlist_name: str) -> tuple[bool | Error, list[dict[str, Any]]] | Error:
        """ Copy a playlist into another one. 
        
        If successful, return a tuple with write status [0] and added tracks [1]. Error object otherwise. """
        
        if target_playlist_name.lower().replace(" ", "") == source_playlist_name.lower().replace(" ", ""):
            return Error("Destination playlist name cannot be the same as the source one!")
        
        playlist = await self.get_playlist(content, source_playlist_name)
        if isinstance(playlist, Error):
            return playlist
        
        return await self.add_queue(interaction, content, target_playlist_name, playlist)
    
    async def copy_items(
            self, 
            interaction: Interaction, 
            content: dict[str, list], 
            track_names: list[str], 
            source_playlist_name: str, 
            target_playlist_name: str,
            by_index: bool=False
        ) -> tuple[bool | Error, list[dict[str, Any]]] | Error:
        """ Copy a playlist's tracks into another one. 
        
        If successful, return a tuple with write status [0] and added tracks [1]. Error object otherwise. """

        if target_playlist_name.lower().replace(" ", "") == source_playlist_name.lower().replace(" ", ""):
            return Error("Destination playlist name cannot be the same as the source one!")
        
        playlist = await self.get_playlist(content, source_playlist_name)
        if isinstance(playlist, Error):
            return playlist
        
        to_add = await get_tracks_from_queue(track_names, playlist, by_index)
        if isinstance(to_add, Error):
            return to_add
        
        return await self.add_queue(interaction, content, target_playlist_name, to_add)