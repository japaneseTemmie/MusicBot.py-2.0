""" Playlist module for discord.py bot.
Includes a few methods for managing playlists\n
and fetching tracks from them. """

from settings import *
from modules.utils import *
from bot import Bot

class PlaylistManager:
    def __init__(self, client: Bot):
        self.client = client
        self.file_path = join(PATH, "guild_data")
        self.max_limit = 5
        self.max_item_limit = 100
        self.max_name_length = 50

    async def exists(self, content: dict, playlist_name: str) -> bool:
        """ Checks if a playlist exists in a JSON structure.\n
        Returns a boolean. """
        
        return playlist_name in content

    async def is_full(self, content: dict, playlist_name: str) -> bool:
        """ Checks if the given playlist is full.\n
        Returns a boolean. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return False # go to error handler
        
        playlist = content.get(playlist_name, [])

        if not playlist:
            return False
        
        return len(playlist) >= self.max_item_limit

    async def has_playlists(self, content: dict) -> bool:
        """ Checks if a JSON structure has any playlists saved.\n
         Returns a boolean. """
        
        return len(content) > 0

    async def lock(self, interaction: Interaction, content: dict, locked: dict, playlist_name: str) -> None:
        """ Locks a playlist. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return

        # Ensure the target playlist exists or a command that creates one is used.
        if  (await self.exists(content, playlist_name) or\
                interaction.command.name in ("playlist-save", "playlist-add-yt-playlist", "playlist-add", "playlist-create")):
            locked[playlist_name] = True

    async def unlock(self, locked: dict, content: dict | None, playlist_name: str) -> None:
        """ Unlocks a playlist. """
        
        if playlist_name in locked:
            locked[playlist_name] = False
        
        await self.cleanup_locked(content, locked)

    async def unlock_all(self, guild_states: dict, interaction: Interaction, locked: dict) -> None:
        """ Unlocks every playlist.\n
        Used only in case of errors. """
        
        locked = guild_states[interaction.guild.id]["locked_playlists"]
        locked.clear()

    async def is_locked(self, locked: dict) -> bool:
        """ Checks if any playlist is locked in 'locked' parameter.\n
        Returns a boolean. """
        
        return any(locked.values())

    async def cleanup_locked(self, content: dict, locked: dict) -> None:
        """ Cleans up leftover playlists. """
        
        if content is not None and content != RETURN_CODES["READ_FAIL"]:
            to_remove = [key for key in locked if key not in content]
                
            for key in to_remove:
                del locked[key]

    async def get_content(self, interaction: Interaction) -> dict | int:
        """ Safely read the content of a guild's playlist file.\n
        If successful, returns the JSON structure. """
        if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
            return RETURN_CODES["READ_FAIL"]
        
        content = get_cache(PLAYLIST_FILE_CACHE, interaction.guild.id)
        if content:
            return content

        await ensure_lock(interaction, PLAYLIST_LOCKS)
        file_lock = PLAYLIST_LOCKS[interaction.guild.id]

        async with file_lock:
            path = join(PATH, "guild_data", str(interaction.guild.id))
            file = join(path, "playlists.json")

            success = await asyncio.to_thread(ensure_paths, path, file)
            if success == RETURN_CODES["WRITE_FAIL"]:
                return RETURN_CODES["READ_FAIL"]

            content = await asyncio.to_thread(open_file, file, True)

            if content != RETURN_CODES["READ_FAIL"]:
                store_cache(content, interaction.guild.id, PLAYLIST_FILE_CACHE)

            return content

    async def read(self, content: dict, playlist_name: str) -> list[dict] | int:
        """ Reads the given playlist.\n
        If successful, returns a list of tracks. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
        
        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]
        
        playlist = content[playlist_name]

        if not playlist:
            return RETURN_CODES["PLAYLIST_IS_EMPTY"]

        return playlist

    async def write(self, interaction: Interaction, content: dict, backup: dict=None) -> int:
        """ Safely write the modified content of a playlist function to
        file.\n
        Returns a write success status. """
        if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
            return RETURN_CODES["WRITE_FAIL"]
        
        await ensure_lock(interaction, PLAYLIST_LOCKS)
        file_lock = PLAYLIST_LOCKS[interaction.guild.id]

        async with file_lock:
            path = join(PATH, "guild_data", str(interaction.guild.id))
            file = join(path, "playlists.json")
                
            success = await asyncio.to_thread(ensure_paths, path, file)
            if success == RETURN_CODES["WRITE_FAIL"]:
                return RETURN_CODES["WRITE_FAIL"]

            result = await asyncio.to_thread(write_file, file, content, True)

            if result == RETURN_CODES["WRITE_FAIL"]:
                if backup is not None:
                    await asyncio.to_thread(write_file, file, backup, True)

                return RETURN_CODES["WRITE_FAIL"]
            
            store_cache(content, interaction.guild.id, PLAYLIST_FILE_CACHE)
            
            return RETURN_CODES["WRITE_SUCCESS"]

    async def get_available(self, content: dict) -> list[str] | int:
        """ Returns the available playlists' names in a list. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        return [key for key in content.keys()]

    async def create(self, interaction: Interaction, content: dict, playlist_name: str) -> int:
        """ Creates a playlist.\n
        If successful, returns a successful write status. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
        
        if len(playlist_name) > self.max_name_length:
            return RETURN_CODES["NAME_TOO_LONG"]

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content):
            content = {}

        if await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_EXISTS"]

        if len(content) >= self.max_limit:
            return RETURN_CODES["MAX_PLAYLIST_LIMIT_REACHED"]

        content[playlist_name.strip()] = []

        success = await self.write(interaction, content, backup)
        
        return success

    async def delete(self, interaction: Interaction, content: dict, playlist_name: str, contents_only: bool) -> int | tuple[int, list[dict]]:
        """ Deletes a playlist.\n
        If successful, returns a successful write status. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]

        if contents_only:

            if not content[playlist_name]:
                return RETURN_CODES["PLAYLIST_IS_EMPTY"]
            
            previous_contents = deepcopy(content[playlist_name])
            content[playlist_name].clear()
        else:
            del content[playlist_name]

        success = await self.write(interaction, content, backup)

        return success if not contents_only else (success, previous_contents)

    async def remove(self, interaction: Interaction, content: dict, playlist_name: str, tracks: str, by_index: bool=False) -> list[dict] | int:
        """ Removes given tracks from a playlist.\n
        If successful, returns the list of removed tracks. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]
    
        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]

        playlist = content[playlist_name]
        if not playlist:
            return RETURN_CODES["PLAYLIST_IS_EMPTY"]

        found = await remove_track_from_queue(split(tracks), playlist, by_index)

        if found:
            success = await self.write(interaction, content, backup)
            
            if success == RETURN_CODES["WRITE_SUCCESS"]:
                return found
            else:
                return success
        else:
            return RETURN_CODES["NOT_FOUND"]

    async def replace(self, guild_states: dict, interaction: Interaction, content: dict, playlist_name: str, old: str, new: str, by_index: bool=False) -> tuple[int, dict, dict] | int:
        """ Replaces a playlist track with a given query.\n
        If successful, returns a tuple with the write success status [0], the old track [1] and the new track [2]."""
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]
        
        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]

        playlist = content[playlist_name]
        if not playlist:
            return RETURN_CODES["PLAYLIST_IS_EMPTY"]

        result = await replace_track_in_queue(guild_states, interaction, old, new, True, playlist, by_index)
        if isinstance(result, int):
            return result

        success = await self.write(interaction, content, backup)

        return (success, result[1], result[0])

    async def reposition(self, interaction: Interaction, content: dict, playlist_name: str, track: str, index: int, by_index: bool=False) -> tuple[int, dict, int, int] | int:
        """ Repositions a playlist track from its current index to the given index.\n
        If successful, returns a tuple with the write success status [0], the repositioned track in a hashmap [1], old index [2], and new index [3]."""
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
        
        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]
        
        playlist = content[playlist_name]
        if not playlist:
            return RETURN_CODES["PLAYLIST_IS_EMPTY"]

        index -= 1
        index = max(0, min(index, len(playlist) - 1))
        
        result = await reposition_track_in_queue(track, index, playlist, by_index)
        if isinstance(result, int):
            return result

        success = await self.write(interaction, content, backup)

        return (success, result[0], result[1][1]+1, index+1)

    async def select(self, guild_states: dict, max_track_limit: int, interaction: Interaction, content: dict, playlist_name: str, range_start: int=0, range_end: int=0) -> list[dict] | tuple[int, str] | int:
        """ Adds all playlist tracks from range_start to range_end to the queue.\n
        If successful, returns a list of added tracks. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]

        playlist = content[playlist_name]

        if not playlist:
            return RETURN_CODES["PLAYLIST_IS_EMPTY"]

        range_start -= 1 # decrement from 1-index to 0-index
        range_end -= 1
        
        # Both variables are -1, nothing user-specified, so set them to 0 and content length.
        if range_start == -1:
            range_start = 0
        if range_end == -1:
            range_end = len(playlist) - 1
        range_start = max(0, min(range_start, len(playlist) - 1))
        range_end = max(0, min(range_end, len(playlist) - 1))

        if range_start > range_end:
            return RETURN_CODES["INVALID_RANGE"]
        
        query_names = [track["title"] for track in playlist[range_start:range_end+1]]
        found = await fetch_queries(guild_states, interaction, playlist[range_start:range_end+1], query_names)
        
        if isinstance(found, list):
            queue = guild_states[interaction.guild.id]["queue"]
            is_looping_queue = guild_states[interaction.guild.id]["is_looping_queue"]

            await replace_data_with_playlist_data(found, playlist[range_start:range_end+1])
            await add_results_to_queue(interaction, found, queue, max_track_limit)

            if is_looping_queue:
                await update_loop_queue_add(guild_states, interaction)

            return found
        elif isinstance(found, tuple): # fetch_queries() returns a tuple in case of an error with the return code at index 0 and what failed at index 1
            return found

    async def fetch(self, guild_states: dict, max_track_limit: int, interaction: Interaction, content: dict, playlist_name: str, tracks: list[str | dict], use_dict: bool=False, by_index: bool=False) -> list[dict] | tuple[int, str] | int:
        """ Adds requested queries from a given playlist to the queue.\n
        If successful, returns a list of added tracks. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]
        
        playlist = content[playlist_name]
        if not playlist:
            return RETURN_CODES["PLAYLIST_IS_EMPTY"]

        if not use_dict:
            queries = await get_tracks_from_playlist(tracks, playlist, by_index)
        else:
            queries = tracks
        
        if queries == RETURN_CODES["NOT_FOUND"]:
            return queries
        
        query_names = [track["title"] for track in queries]
        found = await fetch_queries(guild_states, interaction, queries, query_names)

        if isinstance(found, list):
            queue = guild_states[interaction.guild.id]["queue"]
            is_looping_queue = guild_states[interaction.guild.id]["is_looping_queue"]

            await replace_data_with_playlist_data(found, queries)
            await add_results_to_queue(interaction, found, queue, max_track_limit)

            if is_looping_queue:
                await update_loop_queue_add(guild_states, interaction)

            return found
        elif isinstance(found, tuple):
            return found

    async def add_queue(self, interaction: Interaction, content: dict, playlist_name: str, queue: list[dict], cancel_if_playlist_exists: bool=False) -> tuple[int, list[dict], bool] | int:
        """ Adds a list of extracted queries to a playlist.
        If successful, returns a tuple with the write success status [0], a list containing the added tracks [1], and a boolean indicating if the track limit has been exceeded [2]."""
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content):
            content = {}

        if not await self.exists(content, playlist_name):
            if len(content) < self.max_limit:
                if len(playlist_name) <= self.max_name_length:
                    content[playlist_name.strip()] = []
                else:
                    return RETURN_CODES["NAME_TOO_LONG"]
            else:
                return RETURN_CODES["MAX_PLAYLIST_LIMIT_REACHED"]
        elif cancel_if_playlist_exists and len(content[playlist_name]) > 0:
            return RETURN_CODES["PLAYLIST_EXISTS"]

        found = []
        exceeds_track_limit = False
        playlist_queue = content[playlist_name]
        
        for i, track in enumerate(queue):
            track = {
                "title": track.get("title", "Unknown"),
                "uploader": track.get("uploader", "Unknown"),
                "duration": track.get("duration", "00:00:00"),
                "webpage_url": track.get("webpage_url"),
                "source_website": track.get("source_website", "Unknown")
            }
            if len(playlist_queue) < self.max_item_limit:
                playlist_queue.append(track)
                found.append(track)
            else:
                del found[i:]
                exceeds_track_limit = True

                break

        success = await self.write(interaction, content, backup)
        
        return (success, found, exceeds_track_limit)

    async def add(self, guild_states: dict, interaction: Interaction, content: dict, playlist_name: str, queries: list[str], cancel_if_playlist_exists: bool=False, forbid_type: str=None, only_allow_type: str=None) -> tuple[int, list[dict], bool] | tuple[int, str] | int:
        """ Adds a list of queries to the given playlist.\n
        If successful, returns a tuple with the write success status [0], a list containing the added tracks [1], and a boolean indicating if the track limit has been exceeded [2]."""
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
        
        # Avoid returning these errors when using add_queue() to not waste bandwidth
        if await self.is_full(content, playlist_name):
            return RETURN_CODES["PLAYLIST_IS_FULL"]
        
        if len(content) >= self.max_limit and playlist_name not in content:
            return RETURN_CODES["MAX_PLAYLIST_LIMIT_REACHED"]

        found = await fetch_queries(guild_states, interaction, queries, None, forbid_type, only_allow_type)

        if isinstance(found, list):
            success = await self.add_queue(interaction, content, playlist_name, found, cancel_if_playlist_exists)

            if isinstance(success, tuple):
                return (success[0], success[1], success[2])
            else:
                return success
        else:
            return found

    async def delete_all(self, interaction: Interaction, content: dict, locked: dict, erase: bool) -> int:
        """ Deletes every playlist saved in the current guild.\n
        If successful, returns a successful write status. """
        
        if (content is None or content == RETURN_CODES["READ_FAIL"]) and not erase:
            return RETURN_CODES["READ_FAIL"]

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content) and not erase:
            return RETURN_CODES["NO_PLAYLISTS"]
        
        content = {}

        success = await self.write(interaction, content, backup)
        await self.cleanup_locked(content, locked)

        return success

    async def rename(self, interaction: Interaction, content: dict, orig_playlist_name: str, new_playlist_name: str) -> tuple[int, str, str] | int:
        """ Renames a playlist.\n
        If successful, returns a tuple with write success status [0], old name [1], and new name [2]."""
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
        
        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)

        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        if not await self.exists(content, orig_playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]

        if len(new_playlist_name) > self.max_name_length:
            return RETURN_CODES["NAME_TOO_LONG"]

        playlists = content.items()
        content = {new_playlist_name if key == orig_playlist_name else key: value for key, value in playlists}

        success = await self.write(interaction, content, backup)

        return (success, orig_playlist_name, new_playlist_name)
        
    async def edit(self, interaction: Interaction, content: dict, playlist_name: str, tracks: str, new_names: str, by_index: bool) -> tuple[int, list[tuple[dict, str]]] | int:
        """ Bulk edit track names.\n
        if successful, returns a tuple with write success status [0], a tuple with old track's hashmap [0] and the new name [1]"""
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
        
        if not await self.has_playlists(content):
            return RETURN_CODES["NO_PLAYLISTS"]

        if not await self.exists(content, playlist_name):
            return RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)
        playlist = content[playlist_name]

        if not playlist:
            return RETURN_CODES["PLAYLIST_IS_EMPTY"]

        found = await edit_tracks_in_queue(self.max_name_length, playlist, tracks, new_names, by_index)

        if not found:
            return RETURN_CODES["NOT_FOUND"]

        success = await self.write(interaction, content, backup)
        
        return (success, found)
    
    async def place(self, interaction: Interaction, content: dict, playlist_name: str, track: dict, index: int | None) -> tuple[int, dict, int] | int:
        """ Place a track at a specific index (passing None will point to the last index of the given playlist).\n
        if successful, returns a tuple with write success status [0], added track [1], and its new index [2]. """
        
        if content is None or content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
        
        backup = None if not CONFIG["enable_file_backups"] else deepcopy(content)
        
        if not await self.exists(content, playlist_name):
            if len(content) < self.max_limit:
                if len(playlist_name) <= self.max_name_length:
                    content[playlist_name.strip()] = []
                else:
                    return RETURN_CODES["NAME_TOO_LONG"]
            else:
                return RETURN_CODES["MAX_PLAYLIST_LIMIT_REACHED"]
            
        playlist = content[playlist_name]
            
        index = max(1, min(index, len(playlist) + 1)) if index is not None else len(playlist) + 1
        index -= 1
        
        playlist_track = {
            'title': track['title'],
            'uploader': track['uploader'],
            'duration': track['duration'],
            'webpage_url': track['webpage_url'],
            'source_website': track['source_website']
        }

        if playlist_track in playlist and await try_index(playlist, index, playlist_track):
            return RETURN_CODES["SAME_INDEX_PLACEMENT"]
        
        playlist.insert(index, playlist_track)

        success = await self.write(interaction, content, backup)

        return (success, track, index+1)
    