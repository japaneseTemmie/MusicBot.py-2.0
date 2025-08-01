""" Helper functions for discord.py bot """

from settings import *
from cachehelpers import get_cache, store_cache, invalidate_cache
from timehelpers import format_minutes, format_seconds, format_minutes_extended
from extractor import fetch, get_query_type

""" Utilities """

class Error:
    def __init__(self, msg: str):
        self.msg = msg

# Function to get a hashmap of pages to display of a queue
def get_pages(queue: list[dict]) -> dict[int, list[dict]]:
    queue_copy = deepcopy(queue)
    pages = {}
    max_page = len(pages)
    tracks = []

    while queue_copy:
        for _ in range(min(25, len(queue_copy))):
            tracks.append(queue_copy.pop(0))
        
        pages[max_page] = tracks
        tracks = []
        max_page += 1

    return pages # Return result instead of updating a guild state so we can shave off 3 unused states from get_default_state() :33333333

# Function to reset states
async def get_default_state(voice_client: discord.VoiceClient, curr_channel: discord.TextChannel) -> dict[int, Any]:
    return {
        "voice_client": voice_client,
        "voice_client_locked": False,
        "stop_flag": False,
        "is_looping": False,
        "is_random": False,
        "is_looping_queue": False,
        "is_modifying": False,
        "is_reading_queue": False,
        "is_reading_history": False,
        "is_extracting": False,
        "allow_greetings": True,
        "allow_voice_status_edit": True,
        "voice_status": None,
        "query_amount": 0,
        "max_queries": 0,
        "current_query": None,
        "current_track": None,
        "track_to_loop": None,
        "general_start_date": None,
        "general_start_time": 0,
        "elapsed_time": 0,
        "start_time": 0,
        "queue": [],
        "queue_history": [],
        "queue_to_loop": [],
        "locked_playlists": {},
        "pending_cleanup": False,
        "handling_disconnect_action": False,
        "interaction_channel": curr_channel,
        "greet_timeouts": {}
    }

# Functions for checking guild states and replying to interactions
async def check_channel(guild_states: dict, interaction: Interaction) -> bool:
    """ Check different channel state scenarios and handle them. """
    
    if interaction.guild.id not in guild_states or\
        interaction.guild.voice_client is None:
        await interaction.response.send_message("I'm not in any voice channel!")
        return False
    
    if not interaction.user.voice or\
        interaction.user.voice.channel != interaction.guild.voice_client.channel:
        await interaction.response.send_message("Join my voice channel first.")
        return False
    
    text_channel = guild_states.get(interaction.guild.id, {}).get("interaction_channel", None)

    if text_channel and interaction.channel != text_channel:
        await interaction.response.send_message(f"To avoid results in different channels, please run this command in **{text_channel.mention}**.")
        return False
    
    return True

async def check_guild_state(
        guild_states: dict,
        interaction: Interaction,
        state="is_modifying",
        condition: Any=True,
        msg: str="The queue is currently being modified, please wait."
    ) -> bool:

    """ Check a guild state.\n
    If it matches `condition`, reply to `interaction` with `msg` and return False, else return True. """
    
    if interaction.guild.id in guild_states:
        value = guild_states[interaction.guild.id][state]
        if value == condition:
            await interaction.response.send_message(msg) if not interaction.response.is_done() else\
            await interaction.followup.send(msg)
            return False
        
        return True

# Functions to update the copied queue when queueloop is enabled.
async def update_loop_queue_replace(guild_states: dict, interaction: Interaction, old_track: dict, track: dict) -> None:
    if interaction.guild.id in guild_states:
        queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]

        if old_track in queue_to_loop:
            for i, obj in enumerate(queue_to_loop):
                if obj == old_track:
                    loop_index = i
                    break
            
            queue_to_loop.remove(old_track)
            queue_to_loop.insert(loop_index, track)

async def update_loop_queue_remove(guild_states: dict, interaction: Interaction, tracks_to_remove: list[dict]) -> None:
    if interaction.guild.id in guild_states:
        queue = guild_states[interaction.guild.id]["queue"]
        queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]

        for track_to_remove in tracks_to_remove:
            if track_to_remove not in queue and track_to_remove in queue_to_loop:
                queue_to_loop.remove(track_to_remove)

async def update_loop_queue_add(guild_states: dict, interaction: Interaction) -> None:
    if interaction.guild.id in guild_states:
        queue = guild_states[interaction.guild.id]["queue"]
        queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]

        for track in queue:
            if track not in queue_to_loop:
                queue_to_loop.append(track)

# Functions for updating guild states
async def update_query_extraction_state(guild_states: dict, interaction: Interaction, amount: int, max_amount: int, current: str | None):
    if interaction.guild.id in guild_states:
        await update_guild_states(guild_states, interaction, (amount, max_amount, current), ("query_amount", "max_queries", "current_query"))

async def update_guild_state(guild_states: dict, interaction: Interaction, value: Any, state: str="is_modifying"):
    if interaction.guild.id in guild_states:
        guild_states[interaction.guild.id][state] = value

async def update_guild_states(guild_states: dict, interaction: Interaction, values: tuple[Any], states: tuple[str]):
    if interaction.guild.id in guild_states:
        for state, value in zip(states, values):
            guild_states[interaction.guild.id][state] = value

# Functions for fetching stuff and adding it to a list
async def fetch_query(
            guild_states: dict,
            interaction: Interaction,
            query: str,
            extraction_state_amount: int=1,
            extraction_state_max_length: int=1,
            query_name: str=None,
            forbid_type: str=None,
            only_allow_type: str=None
        ) -> dict | list[dict] | Error:
        """ Extract a query from its website, catch any errors and return the result. """
        
        query = query.strip()

        if not query:
            return Error("Query cannot be empty.")

        await update_query_extraction_state(guild_states, interaction, extraction_state_amount, extraction_state_max_length, query_name.strip() if query_name is not None else query)

        query_type = get_query_type(query)
        if (forbid_type or only_allow_type) and query_type[1] == forbid_type if forbid_type is not None else\
                            query_type[1] != only_allow_type if only_allow_type is not None else None:
            return Error(f"Query type **{query_type[1]}** not supported for this command!")

        extracted_track = await asyncio.to_thread(fetch, query, query_type)
        if extracted_track is None or (isinstance(extracted_track, list) and not extracted_track):
            return Error(f"An error occurred while extracting `{query}`.")

        return extracted_track

async def fetch_queries(guild_states: dict,
        interaction: Interaction,
        queries: list[str | dict],
        query_names: list[str]=None,
        forbid_type: str=None,
        only_allow_type: str=None
    ) -> list[dict | list[dict]] | Error:
    """ Extract a list of queries using the fetch_query() function. """
    
    found = []
    for i, query in enumerate(queries):
        extracted_query = await fetch_query(guild_states, interaction,
                query=query if not isinstance(query, dict) else query["webpage_url"],
                extraction_state_amount=i + 1,
                extraction_state_max_length=len(queries),
                query_name=query_names[i] if isinstance(query_names, list) else query_names,
                forbid_type=forbid_type,
                only_allow_type=only_allow_type
            )

        if isinstance(extracted_query, (Error, list)):
            return extracted_query
        else:
            found.append(extracted_query)
    
    return found

async def add_results_to_queue(interaction: Interaction, results: list[dict], queue: list, max_limit: int) -> list[dict]:
    """ Append found results to a queue in place and return None.\n
    Reply to the interaction if it exceeds max_limit. """
    added = []

    for track_info in results:
        if len(queue) >= max_limit:
            await interaction.channel.send(f"Maximum track limit of **{max_limit}** reached.\nCannot add more tracks.")
            break

        queue.append(track_info)
        added.append(track_info)

    return added

# Functions for checking input and queue, these functions also 'reply' to interactions
async def check_input_length(interaction: Interaction, max_limit: int, input_split: list[Any]) -> list[Any]:
    input_length = len(input_split)
    
    if input_length > max_limit:
        input_split = input_split[:max_limit]
        await interaction.channel.send(f"You can only add a maximum of **{max_limit}** tracks per command.\n"
                                       f"You were trying to add **{input_length}** tracks.\n"
                                       f"Only the first **{max_limit}** of those will be added."
                                        )

    return input_split

async def check_queue_length(interaction: Interaction, max_limit: int, queue: list) -> bool:
    queue_length = len(queue)
    if queue_length >= max_limit:
        await interaction.followup.send(f"Maximum queue track limit of **{max_limit}** reached.\nCannot add other track(s).") if interaction.response.is_done() else\
        await interaction.response.send_message(f"Maximum queue track limit of **{max_limit}** reached.\nCannot add other track(s).")
        
        return False
    
    return True

# Input sanitation
async def sanitize_name(name: str) -> str:
    return name.replace("\\", "").strip() or "Untitled"

# Functions for finding items
async def find_track(track: str, iterable: list[dict], by_index: bool=False) -> tuple[dict, int] | Error:
    """ Find a track given its name or index in an iterable.\n
    Returns a tuple with the track hashmap [0] and its index [1] or an Error object. """
    
    if by_index:
        track = track.strip()
        if track.isdigit():
            index = max(1, min(int(track), len(iterable)))
            index -= 1

            return (iterable[index], index)
        
        return Error(f"**{track[:50]}** is not an integer number!")

    for i, track_info in enumerate(iterable):
        if track.lower().replace(" ", "") == track_info["title"].lower().replace(" ", ""):
            return (track_info, i)
        
    return Error(f"Could not find track **{track[:50]}**.")

async def get_previous(current: dict | None, history: list[dict] | list) -> dict | Error:
    if not history:
        return Error("Track history is empty. Nothing to show.")
    
    length = len(history)
    amount_to_check = 2 if current is not None else 1

    if length < amount_to_check:
        return Error("There's no previous track to show.")
    
    return history[length - 2] if current is not None else history[length - 1] # len - 1 = current, len - 2 = actual previous track

async def get_next(is_random: bool, is_looping: bool, track_to_loop: dict | None, queue: list[dict], queue_to_loop: list[dict]) -> dict | Error:
    if is_random:
        return Error("Next track will be random.")

    if is_looping and track_to_loop:
        next_track = track_to_loop
    elif queue:
        next_track = queue[0]
    elif queue_to_loop:
        next_track = queue_to_loop[0]
    else:
        return Error("Queue is empty. Nothing to preview.")
    
    return next_track

async def try_index(iterable: list[Any], index: int, expected: Any) -> bool:
    """ Test an index and see if it contains anything.
    Return True if it matches `expected`, False otherwise or on IndexError """
    
    try:
        return iterable[index] == expected
    except IndexError:
        return False

# Functions to get stuff from playlists.
async def get_tracks_from_playlist(usr_tracks: list[str], playlist: list[dict], by_index: bool=False) -> list[dict] | Error:
    found = []
    for track in usr_tracks:
        track_info = await find_track(track, playlist, by_index)
        
        if isinstance(track_info, Error):
            return track_info
        
        found.append(track_info[0])

    return found if found else Error("Could not find given tracks.")

async def get_random_tracks_from_playlist(playlist: list[dict], amount: int) -> list[dict] | list:
    found = []

    for _ in range(amount):
        chosen = choice(playlist)
        found.append(chosen)

    return found

# Apply playlist tracks' title and source website to tracks
# Has no effect on titles if users did not modify them.
async def replace_data_with_playlist_data(tracks: list[dict], data: list[dict]) -> None:
    """ Replaces a track's 'title' and 'source_website' keys' values with values from the playlist (data). """
    
    for track, playlist_track in zip(tracks, data):
        track["title"] = playlist_track["title"]
        track["source_website"] = playlist_track["source_website"]

# Remove/Reposition/etc. functions
async def remove_track_from_queue(tracks: list[str], queue: list[dict], by_index: bool=False) -> list[dict] | Error:
    found = []
    
    for track in tracks:
        found_track = await find_track(track, queue, by_index)

        if isinstance(found_track, Error):
            return found_track

        index = found_track[1]
        removed = queue.pop(index)

        found.append(removed)

    return found if found else Error("Could not find given tracks.")

async def reposition_track_in_queue(track: str, index: int, queue: list[dict], by_index: bool=False) -> tuple[dict, int, int] | Error:
    index = max(1, min(index, len(queue)))
    index -= 1

    found_track = await find_track(track, queue, by_index)
    if isinstance(found_track, Error):
        return found_track

    if found_track[1] == index:
        return Error("Cannot reposition a track to the same index.")
    
    track_dict = queue.pop(found_track[1])
    queue.insert(index, track_dict)

    return track_dict, found_track[1]+1, index+1

async def replace_track_in_queue(
        guild_states: dict,
        interaction: Interaction,
        queue: list[dict],
        track: str, 
        new_track: str,
        is_playlist: bool=False,
        by_index: bool=False
    ) -> tuple[dict, dict] | Error:
    
    found_track = await find_track(track, queue, by_index)
    if isinstance(found_track, Error):
        return found_track

    extracted_track = await fetch_query(guild_states, interaction, new_track, 1, 1, None, "YouTube Playlist")
    if isinstance(extracted_track, Error):
        return extracted_track

    if is_playlist:
        extracted_track = {
            'title': extracted_track['title'],
            'uploader': extracted_track['uploader'],
            'duration': extracted_track['duration'],
            'webpage_url': extracted_track['webpage_url'],
            'source_website': extracted_track['source_website']
        }

    if extracted_track["title"].lower().replace(" ", "") == found_track[0]["title"].lower().replace(" ", ""):
        return Error(f"Cannot replace a track (**{found_track[0]['title']}**) with the same one.")
    
    removed_track = queue.pop(found_track[1])
    queue.insert(found_track[1], extracted_track)

    return extracted_track, removed_track

async def edit_tracks_in_queue(max_name_length: int, queue: list[dict], names: str, new_names: str, by_index: bool=False) -> list[tuple[dict, str]] | Error:
    names = split(names)
    new_names = split(new_names)
    found = []
    
    for track, new_name in zip(names, new_names):
        new_name = new_name.strip()
        
        if len(new_name) > max_name_length:
            return Error(f"Name **{new_name[:50]}** is too long! Must be < **{max_name_length}** characters.")

        found_track = await find_track(track, queue, by_index)
        if isinstance(found_track, Error):
            return found_track
        elif new_name.lower().replace(" ", "") == found_track[0]["title"].lower().replace(" ", ""):
            return Error(f"Cannot rename a track (**{found_track[0]['title']}**) to the same name.")
        
        old_track = deepcopy(found_track[0])
        old_track_index = found_track[1]
        
        queue[old_track_index]["title"] = new_name
        found.append((old_track, new_name))

    return found if found else Error(f"Could not find given tracks.")

async def place_track_in_playlist(queue: list, index: int | None, track: dict) -> tuple[dict, int] | Error:
    index = max(1, min(index, len(queue))) if index is not None else len(queue)+1
    index -= 1
    
    playlist_track = {
        'title': track['title'],
        'uploader': track['uploader'],
        'duration': track['duration'],
        'webpage_url': track['webpage_url'],
        'source_website': track['source_website']
    }

    if playlist_track in queue and await try_index(queue, index, playlist_track):
        return Error(f"Cannot place track (**{track['title'][:50]}**) because it already exists at the specified index.")
    
    queue.insert(index, playlist_track)

    return (playlist_track, index+1)

# Custom split
def split(s: str) -> list[str]:
    """ Use this lovely regex to split on ; with the exception when it's prefixed with a '\\\\'. """
    
    parts = re.split(r'(?<!\\);', s)
    return [part.replace(r'\;', ';') for part in parts]

# Function to get a file lock for a specific guild id
async def ensure_lock(interaction: Interaction, locks: dict) -> None:
    if interaction.guild.id not in locks:
        locks[interaction.guild.id] = asyncio.Lock()

# Connect behaviour
async def greet_new_user_in_vc(guild_states: dict, user: discord.Member) -> None:
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

# Disconnect behaviour
async def cleanup_guilds(guild_states: dict, clients: list[discord.VoiceClient]):
    active_guild_ids = [client.guild.id for client in clients]

    for guild_id in guild_states.copy():
        if guild_id not in active_guild_ids:
            invalidate_cache(guild_id, guild_states)
            invalidate_cache(guild_id, PLAYLIST_LOCKS)
            invalidate_cache(guild_id, ROLE_LOCKS)
            invalidate_cache(guild_id, PLAYLIST_FILE_CACHE)
            invalidate_cache(guild_id, ROLE_FILE_CACHE)

            log(f"[GUILDSTATE] Cleaned up guild ID {guild_id} from guild states, cache and locks.")

async def check_users_in_channel(guild_states: dict, member: discord.Member | Interaction) -> bool:
    """ Check if there are any users in a voice channel.
    Returns True if none are left and the bot is disconnected, else False. """
    
    if VOICE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
        return True # bot is disconnected

    voice_client = guild_states[member.guild.id]["voice_client"]
    locked = guild_states[member.guild.id]["locked_playlists"]
    is_extracting = guild_states[member.guild.id]["is_extracting"]
    is_vc_locked = guild_states[member.guild.id]["voice_client_locked"]
    handling_disconnect = guild_states[member.guild.id]["handling_disconnect_action"]

    if handling_disconnect:
        return False
    
    if len(voice_client.channel.members) > 1: # Bot counts as a member, therefore we must check if > 1
        return False

    if voice_client.is_connected() and\
        not voice_client.is_playing() and\
        not is_extracting and\
        not is_vc_locked and\
        not await is_playlist_locked(locked):

        log(f"[DISCONNECT][SHARD ID {member.guild.shard_id}] Disconnecting from channel ID {voice_client.channel.id} because no users are left in it and all conditions are met.")

        if voice_client.is_paused():
            await update_guild_state(guild_states, member, True, "stop_flag")

        await voice_client.disconnect() # rest is handled by disconnect_routine() (hopefully)
        return True

    return False

async def disconnect_routine(client: commands.Bot | commands.AutoShardedBot, guild_states: dict, member: discord.Member):
    voice_client = guild_states[member.guild.id]["voice_client"]
    can_update_status = guild_states[member.guild.id]["allow_voice_status_edit"]
    has_pending_cleanup = guild_states[member.guild.id]["pending_cleanup"]
    handling_disconnect = guild_states[member.guild.id]["handling_disconnect_action"]
    
    if has_pending_cleanup or\
        handling_disconnect:
        log(f"[GUILDSTATE] Already handling a disconnect action for guild ID {member.guild.id}, ignoring.")
        return

    await update_guild_states(guild_states, member, (True, True), ("pending_cleanup", "handling_disconnect_action"))

    log(f"[GUILDSTATE] Waiting 10 seconds before cleaning up guild ID {member.guild.id}...")
    await asyncio.sleep(10) # Sleepy time :3 maybe it's a network issue

    if any(client.guild.id == member.guild.id for client in client.voice_clients): # Reconnected, all good
        log(f"[RECONNECT][SHARD ID {member.guild.shard_id}] Cleanup operation cancelled for guild ID {member.guild.id}")

        await update_guild_states(guild_states, member, (False, False), ("pending_cleanup", "handling_disconnect_action"))
        return
    
    if can_update_status:
        await update_guild_state(guild_states, member, None, "voice_status")
        await set_voice_status(guild_states, member)
    
    """ Assumes the bot is disconnected before calling this function, which should be the case since disconnect_routine() gets triggered when there's a voice state update
    and the bot is no longer in a channel (after.channel is None) """
    voice_client.cleanup()

    """ Use this function instead of a simple 'del guild_states[member.guild.id]' so we catch
    any leftover guilds that were not properly cleaned up. """
    await cleanup_guilds(guild_states, client.voice_clients)

# Voice channel status
async def set_voice_status(guild_states: dict, interaction: Interaction) -> None:
    if interaction.guild.id in guild_states:
        voice_client = guild_states[interaction.guild.id]["voice_client"]
        status = guild_states[interaction.guild.id]["voice_status"]

        await voice_client.channel.edit(status=status)

# FFmpeg options
async def get_ffmpeg_options(position: int) -> dict:
    FFMPEG_OPTIONS = {}
    
    FFMPEG_OPTIONS["before_options"] = f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -ss {position}"
    FFMPEG_OPTIONS["options"] = f"-vn -ss 0 -loglevel quiet" # -ss 0 here seems to sync the position more accurately

    return FFMPEG_OPTIONS

# Playlist functions
async def playlist_exists(content: dict, playlist_name: str) -> bool:
    """ Checks if a playlist exists in a JSON structure.\n
    Returns a boolean. """
    
    return playlist_name in content

async def is_playlist_full(item_limit: int, content: dict | Error, playlist_name: str) -> bool:
    """ Checks if the given playlist is full.\n
    Returns a boolean. """
    
    if isinstance(content, Error):
        return False # go to error handler
    
    playlist = content.get(playlist_name, [])

    if not playlist:
        return False
    
    return len(playlist) >= item_limit

async def is_content_full(limit: int, content: dict | Error) -> bool:
    """ Check if the `content` exceeds length `limit`.\n
    Returns a boolean. """
    
    if isinstance(content, Error):
        return False
    
    return len(content) >= limit

async def is_playlist_empty(playlist: list[dict]) -> bool:
    """ Check if a playlist is empty.\n
    Returns a boolean. """
    
    return len(playlist) < 1

async def name_exceeds_length(limit: int, name: str) -> bool:
    """ Check if a name exceeds length `limit`.
    Returns a boolean. """
    
    return len(name) > limit

async def has_playlists(content: dict) -> bool:
    """ Checks if a JSON structure has any playlists saved.\n
    Returns a boolean. """

    return len(content) > 0

async def lock_playlist(interaction: Interaction, content: dict | Error, locked: dict, playlist_name: str) -> None:
    """ Locks a playlist. """
    
    if isinstance(content, Error):
        return
    
    playlist_name = await sanitize_name(playlist_name)

    # Ensure the target playlist exists or a command that creates one is used.
    if  (await playlist_exists(content, playlist_name) or\
            interaction.command.name in ("playlist-save", "playlist-add-yt-playlist", "playlist-add", "playlist-create")):
        locked[playlist_name] = True

async def unlock_playlist(locked: dict, content: dict | Error, playlist_name: str) -> None:
    """ Unlocks a playlist. """
    
    playlist_name = await sanitize_name(playlist_name)
    if playlist_name in locked:
        locked[playlist_name] = False
    
    await cleanup_locked_playlists(content, locked)

async def unlock_all_playlists(guild_states: dict, interaction: Interaction, locked: dict) -> None:
    """ Unlocks every playlist.\n
    Used only in case of errors. """
    
    locked = guild_states[interaction.guild.id]["locked_playlists"]
    locked.clear()

async def is_playlist_locked(locked: dict) -> bool:
    """ Checks if any playlist is locked in 'locked' parameter.\n
    Returns a boolean. """
    
    return any(locked.values())

async def cleanup_locked_playlists(content: dict | Error, locked: dict) -> None:
    """ Cleans up leftover playlists. """
    
    if isinstance(content, Error):
        return

    to_remove = [key for key in locked if key not in content]
        
    for key in to_remove:
        del locked[key]

# Moderation utilities
async def get_ban_entries(guild: discord.Guild) -> list[discord.User] | list:
    members = []
    async for ban_entry in guild.bans():
        members.append(ban_entry.user)

    return members

async def get_user_to_unban(ban_entries: list[discord.User], member: str | int) -> discord.User:
    member_obj = None
    funcs = [
        lambda: discord.utils.get(ban_entries, id=int(member) if member.isdigit() else None),
        lambda: discord.utils.get(ban_entries, name=member.strip()),
        lambda: discord.utils.get(ban_entries, global_name=member.strip())
    ]

    for func in funcs:
        member_obj = func()

        if member_obj is not None:
            break

    return member_obj

async def remove_markdown_or_mentions(text: str, markdown: bool, mentions: bool) -> str:
    clean_text = text

    if mentions:
        clean_text = discord.utils.escape_mentions(clean_text)
    if markdown:
        clean_text = discord.utils.escape_markdown(clean_text)

    return clean_text

async def get_purge_check(user: discord.Member | None, word: str | None) -> Callable:
    """ Return a check for the purge function, allowing to filter
    which messages to delete. """
    
    def check(m: discord.Message) -> bool:
        if user and word:
            return m.author == user and word.lower() in m.content.lower()
        elif user:
            return m.author == user
        elif word:
            return word.lower() in m.content.lower()
        return True
    
    return check
