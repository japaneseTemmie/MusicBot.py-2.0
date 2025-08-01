""" Playlist module for discord.py bot.\n
Includes a few methods for managing playlists
and fetching tracks from them. """

from settings import *
from helpers import *
from iohelpers import *
from bot import Bot

class PlaylistManager:
    def __init__(self, client: Bot):
        self.client = client
        self.file_path = join(PATH, "guild_data")
        self.max_limit = 5
        self.max_item_limit = 100
        self.max_name_length = 50

    async def read(self, interaction: Interaction) -> dict | Error:
        """ Safely read the content of a guild's playlist file.\n
        Cache the content of a successful read.\n
        If successful, returns a hashmap, Error otherwise. """
        if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
            return Error("Playlist reading temporarily disabled.")
        
        await ensure_lock(interaction, PLAYLIST_LOCKS)
        file_lock = PLAYLIST_LOCKS[interaction.guild.id]

        async with file_lock:
            content = get_cache(PLAYLIST_FILE_CACHE, interaction.guild.id)
            if content:
                return content

            path = join(PATH, "guild_data", str(interaction.guild.id))
            file = join(path, "playlists.json")

            success = await asyncio.to_thread(ensure_paths, path, file)
            if success == False:
                return Error("Failed to create guild data.")

            content = await asyncio.to_thread(open_file, file, True)

            if content != False:
                store_cache(content, interaction.guild.id, PLAYLIST_FILE_CACHE)
            else:
                return Error("Failed to read playlist contents.")

            return content

    async def write(self, interaction: Interaction, content: dict, backup: dict=None) -> bool | Error:
        """ Safely write the modified content of a playlist function to the guild's `playlists.json` file.\n
        Cache new content if written successfully.\n
        Returns a boolean [True] or Error. """
        if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
            return Error("Playlist writing temporarily disabled.")
        
        await ensure_lock(interaction, PLAYLIST_LOCKS)
        file_lock = PLAYLIST_LOCKS[interaction.guild.id]

        async with file_lock:
            path = join(PATH, "guild_data", str(interaction.guild.id))
            file = join(path, "playlists.json")
                
            success = await asyncio.to_thread(ensure_paths, path, file)
            if success == False:
                return Error("Failed to create guild data.")

            result = await asyncio.to_thread(write_file, file, content, True)

            if result == False:
                if backup is not None:
                    await asyncio.to_thread(write_file, file, backup, True)

                return Error("Failed to apply changes to playlist.")
            
            store_cache(content, interaction.guild.id, PLAYLIST_FILE_CACHE)
            
            return True

    async def get_playlist(self, content: dict | Error, playlist_name: str) -> list[dict] | Error:
        """ Reads the given playlist.\n
        If successful, returns a list of tracks, otherwise, Error. """
        
        if isinstance(content, Error):
            return content
        
        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        playlist_name = await sanitize_name(playlist_name)

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist.")
        
        playlist = content[playlist_name]

        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty.")

        return playlist

    async def get_available(self, content: dict | Error) -> list[str] | Error:
        """ Get all available playlists' names.
        If successful, returns a list of strings, otherwise Error. """
        
        if isinstance(content, Error):
            return content

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        return [key for key in content.keys()]

    async def create(self, interaction: Interaction, content: dict | Error, playlist_name: str) -> bool | Error:
        """ Creates a playlist.\n
        If successful, returns a boolean, otherwise, Error. """
        
        if isinstance(content, Error):
            return content
        
        playlist_name = await sanitize_name(playlist_name)

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

    async def delete(self, interaction: Interaction, content: dict | Error, playlist_name: str, contents_only: bool) -> bool | tuple[bool, list[dict]] | Error:
        """ Deletes a playlist.\n
        If successful, returns a boolean or a tuple with a boolean indicating write success and removed tracks. Error otherwise. """
        
        if isinstance(content, Error):
            return content

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        playlist_name = await sanitize_name(playlist_name)

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        if contents_only:
            playlist = content[playlist_name]

            if await is_playlist_empty(playlist):
                return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot delete contents.")
            
            previous_contents = deepcopy(playlist)
            playlist.clear()
        else:
            del content[playlist_name]

        success = await self.write(interaction, content, backup)

        return success if not contents_only else (success, previous_contents)

    async def remove(self, interaction: Interaction, content: dict | Error, playlist_name: str, tracks: str, by_index: bool=False) -> list[dict] | Error:
        """ Removes given tracks from a playlist.\n
        If successful, returns the list of removed tracks. Error otherwise. """
        
        if isinstance(content, Error):
            return content

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")
    
        playlist_name = await sanitize_name(playlist_name)

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        playlist = content[playlist_name]
        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot remove tracks.")

        found = await remove_track_from_queue(split(tracks), playlist, by_index)
        if isinstance(found, Error):
            return found
        
        success = await self.write(interaction, content, backup)
        
        if success == True:
            return found
        else:
            return success

    async def replace(self, guild_states: dict, interaction: Interaction, content: dict | Error, playlist_name: str, old: str, new: str, by_index: bool=False) -> tuple[bool, dict, dict] | Error:
        """ Replaces a playlist track with an extracted track from a given query.\n
        If successful, returns a tuple with a boolean indicating write success [0], the old track [1] and the new track [2]. Error otherwise."""
        
        if isinstance(content, Error):
            return content

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")
        
        playlist_name = await sanitize_name(playlist_name)

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        playlist = content[playlist_name]
        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot replace track.")

        result = await replace_track_in_queue(guild_states, interaction, playlist, old, new, True, by_index)
        if isinstance(result, Error):
            return result

        success = await self.write(interaction, content, backup)

        return (success, result[1], result[0])

    async def reposition(self, interaction: Interaction, content: dict | Error, playlist_name: str, track: str, index: int, by_index: bool=False) -> tuple[bool, dict, int, int] | Error:
        """ Repositions a playlist track from its current index to the given index.\n
        If successful, returns a tuple with a boolean indicating write success [0], the repositioned track [1], old index [2], and new index [3]. Error otherwise. """
        
        if isinstance(content, Error):
            return content
        
        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        playlist_name = await sanitize_name(playlist_name)

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")
        
        playlist = content[playlist_name]
        if await is_playlist_empty(playlist):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** is empty. Cannot reposition track.")
        
        result = await reposition_track_in_queue(track, index, playlist, by_index)
        if isinstance(result, Error):
            return result

        success = await self.write(interaction, content, backup)

        return (success, result[0], result[1], result[2])

    async def select(self, guild_states: dict, max_track_limit: int, interaction: Interaction, content: dict | Error, playlist_name: str, range_start: int=0, range_end: int=0) -> list[dict] | Error:
        """ Adds all playlist tracks from `range_start` to `range_end` to the queue.\n
        If successful, returns a list of added tracks. Error otherwise. """
        
        playlist = await self.get_playlist(content, playlist_name)
        if isinstance(playlist, Error):
            return playlist
        
        if range_end == 0:
            range_end = len(playlist)
        range_start = max(1, min(range_start, len(playlist)))
        range_end = max(1, min(range_end, len(playlist)))

        range_start -= 1
        range_end -= 1

        if range_start > range_end:
            return Error("Invalid `range_start` or `range_end`.\n`range_start` must be < `range_end`.")
        
        query_names = [track["title"] for track in playlist[range_start:range_end+1]]
        found = await fetch_queries(guild_states, interaction, playlist[range_start:range_end+1], query_names)

        if isinstance(found, list):
            queue = guild_states[interaction.guild.id]["queue"]
            is_looping_queue = guild_states[interaction.guild.id]["is_looping_queue"]

            await replace_data_with_playlist_data(found, playlist[range_start:range_end+1])
            added = await add_results_to_queue(interaction, found, queue, max_track_limit)

            if is_looping_queue:
                await update_loop_queue_add(guild_states, interaction)

            return added
        elif isinstance(found, Error):
            return found

    async def fetch(self, guild_states: dict, max_track_limit: int, interaction: Interaction, content: dict | Error, playlist_name: str, tracks: list[str | dict], use_dict: bool=False, by_index: bool=False) -> list[dict] | Error:
        """ Adds requested queries from a given playlist to the queue.\n
        If successful, returns a list of added tracks. Error otherwise. """
        
        playlist = await self.get_playlist(content, playlist_name)
        if isinstance(playlist, Error):
            return playlist

        if not use_dict:
            queries = await get_tracks_from_playlist(tracks, playlist, by_index)
        else:
            queries = tracks
        
        if isinstance(queries, Error):
            return queries
        
        query_names = [track["title"] for track in queries]
        found = await fetch_queries(guild_states, interaction, queries, query_names)

        if isinstance(found, list):
            queue = guild_states[interaction.guild.id]["queue"]
            is_looping_queue = guild_states[interaction.guild.id]["is_looping_queue"]

            await replace_data_with_playlist_data(found, queries)
            added = await add_results_to_queue(interaction, found, queue, max_track_limit)

            if is_looping_queue:
                await update_loop_queue_add(guild_states, interaction)

            return added
        elif isinstance(found, Error):
            return found

    async def add_queue(self, interaction: Interaction, content: dict | Error, playlist_name: str, queue: list[dict]) -> tuple[bool, list[dict]] | Error:
        """ Adds a list of extracted queries to a playlist.\n
        If successful, returns a tuple with a boolean indicating write success [0], and a list containing the added tracks [1]. Error otherwise. """
        
        if isinstance(content, Error):
            return content

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)
        playlist_name = await sanitize_name(playlist_name)

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
        
        return (success, added)

    async def add(self, guild_states: dict, interaction: Interaction, content: dict | Error, playlist_name: str, queries: list[str], forbid_type: str=None, only_allow_type: str=None) -> tuple[bool, list[dict]] | Error:
        """ Adds a list of queries to the given playlist.\n
        If successful, returns a tuple with a boolean indicating write success [0] and list containing the added tracks [1]. Error otherwise. """
        
        if isinstance(content, Error):
            return content
        
        playlist_name = await sanitize_name(playlist_name)

        # Avoid returning these errors when using add_queue() to not waste bandwidth
        if await is_playlist_full(self.max_item_limit, content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** has reached the maximum track limit of **{self.max_item_limit}**!\nCannot add more tracks.")
        
        if await is_content_full(self.max_limit, content) and not await playlist_exists(content, playlist_name):
            return Error(f"Maximum playlist limit of **{self.max_limit}** reached! Please delete a playlist to free a slot.")

        found = await fetch_queries(guild_states, interaction, queries, None, forbid_type, only_allow_type)

        if isinstance(found, list):
            success = await self.add_queue(interaction, content, playlist_name, found)

            return success
        else:
            return found

    async def delete_all(self, interaction: Interaction, content: dict | Error, locked: dict, erase: bool) -> bool | Error:
        """ Deletes every playlist saved in the current guild.\n
        Returns a boolean or Error. """
        
        if isinstance(content, Error) and not erase:
            return content

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content) and not erase:
            return Error("This guild has no saved playlists.")
        
        content = {}

        success = await self.write(interaction, content, backup)
        await cleanup_locked_playlists(content, locked)

        return success

    async def rename(self, interaction: Interaction, content: dict | Error, orig_playlist_name: str, new_playlist_name: str) -> tuple[bool, str, str] | Error:
        """ Renames a playlist to a new given name.\n
        If successful, returns a tuple with a boolean indicating write success [0], old name [1], and new name [2]. Error otherwise. """
        
        if isinstance(content, Error):
            return content
        
        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)

        if not await has_playlists(content):
            return Error("This guild has no saved playlists.")

        new_playlist_name = await sanitize_name(new_playlist_name)
        orig_playlist_name = await sanitize_name(orig_playlist_name)

        if not await playlist_exists(content, orig_playlist_name):
            return Error(f"Playlist **{orig_playlist_name[:self.max_name_length]}** does not exist!")

        if await name_exceeds_length(self.max_name_length, new_playlist_name):
            return Error(f"New name **{new_playlist_name[:self.max_name_length]}**.. is too long! Must be < **{self.max_name_length}** characters.")

        if new_playlist_name.lower().replace(" ", "") == orig_playlist_name.lower().replace(" ", ""):
            return Error(f"Cannot rename a playlist (**{orig_playlist_name[:self.max_name_length]}**) to the same name (**{new_playlist_name[:self.max_name_length]}**).")

        playlists = content.items()
        content = {new_playlist_name if key == orig_playlist_name else key: value for key, value in playlists}

        success = await self.write(interaction, content, backup)

        return (success, orig_playlist_name, new_playlist_name)
        
    async def edit(self, interaction: Interaction, content: dict | Error, playlist_name: str, names: str, new_names: str, by_index: bool) -> tuple[bool, list[tuple[dict, str]]] | Error:
        """ Bulk edits track names to new given ones.\n
        if successful, returns a tuple with a boolean indicating write success [0], and a list of tuples with old track [0] and the new name [1]. Error otherwise. """
        
        if isinstance(content, Error):
            return content
        
        if not await has_playlists(content):
            return Error("This guild does not have any saved playlists.")

        playlist_name = await sanitize_name(playlist_name)

        if not await playlist_exists(content, playlist_name):
            return Error(f"Playlist **{playlist_name[:self.max_name_length]}** does not exist!")

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)
        playlist = content[playlist_name]

        if await is_playlist_empty(playlist):
            return Error(f"Playlist {playlist_name[:self.max_name_length]} is empty. Cannot rename tracks.")

        found = await edit_tracks_in_queue(self.max_name_length, playlist, names, new_names, by_index)
        if isinstance(found, Error):
            return found

        success = await self.write(interaction, content, backup)
        
        return (success, found)
    
    async def place(self, interaction: Interaction, content: dict | Error, playlist_name: str, track: dict, index: int | None) -> tuple[bool, dict, int] | Error:
        """ Place a track at a specific index. (passing None will point to the last index of the given playlist)\n
        if successful, returns a tuple with a boolean indicating write success [0], added track [1], and its new index [2]. Error otherwise. """
        
        if isinstance(content, Error):
            return content
        
        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(content)
        playlist_name = await sanitize_name(playlist_name)
        
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

        return (success, result[0], result[1])
    