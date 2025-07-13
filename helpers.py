""" General helper functions for discord.py bot """

from settings import *
from extractor import fetch, get_query_type

""" Utilities """

def add_zeroes(parts: list[str], length_limit: int):
    missing = length_limit - len(parts)
    
    for _ in range(missing):
        parts.insert(0, "00")

def format_seconds(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

def format_minutes(minutes_str: str) -> int | None:
    try:
        parts = minutes_str.split(":")
        
        if len(parts) < 3:
            add_zeroes(parts, 3)
        
        for i, part in enumerate(parts):
            if int(part) > 59 and i > 0:
                return None
        
        hours, minutes, seconds = map(int, parts)
        return int(hours * 3600 + minutes * 60 + seconds)
    except Exception as e:

        if CAN_LOG and LOGGER is not None and not isinstance(e, ValueError):
            LOGGER.exception(e)

        return None

def format_minutes_extended(minutes_str: str) -> int | None:
    try:
        parts = minutes_str.split(":")
        
        if len(parts) < 4:
            add_zeroes(parts, 4)

        for i, part in enumerate(parts):
            if (i < 1 and int(part) > 28) or\
                (i == 1 and int(part) > 23) or\
                (i > 1 and int(part) > 59):
                
                return None

        days, hours, minutes, seconds = map(int, parts)
        return int(days * 86400 + hours * 3600 + minutes * 60 + seconds)
    except Exception as e:
        if CAN_LOG and LOGGER is not None and not isinstance(e, ValueError):
            LOGGER.exception(e)
        return None

# Caching tools
def store_cache(content: Any, id: int, cache: dict) -> None:
    if content:
        cache[id] = content
    else:
        invalidate_cache(id, cache) # Don't cache empty hashmaps

def get_cache(cache: dict, id: int) -> Any | None:
    if id in cache:
        return cache.get(id)
    
def invalidate_cache(id: int, cache: dict) -> None:
    cache.pop(id, None)

# Functions to update the playlist/queue/history pages
def update_queue_pages(guild_states: dict, interaction: Interaction) -> None:
    queue_copy = deepcopy(guild_states[interaction.guild.id]["queue"])
    pages = guild_states[interaction.guild.id]["queue_pages"]
    max_page = len(pages)
    tracks = []

    while queue_copy:
        for _ in range(min(25, len(queue_copy))):
            tracks.append(queue_copy.pop(0))
        
        pages[max_page] = tracks
        tracks = []
        max_page += 1

def update_history_pages(guild_states: dict, interaction: Interaction):
    history_copy = deepcopy(guild_states[interaction.guild.id]["queue_history"])
    history_pages = guild_states[interaction.guild.id]["history_pages"]
    max_history_page = len(history_pages)
    history_tracks = []

    while history_copy:
        for _ in range(min(25, len(history_copy))):
            history_tracks.append(history_copy.pop(0))
        
        history_pages[max_history_page] = history_tracks
        history_tracks = []
        max_history_page += 1

def update_playlist_pages(guild_states: dict, interaction: Interaction, queue: list[dict], playlist_name: str) -> None:
    queue_copy = deepcopy(queue)
    guild_states[interaction.guild.id]["playlist_pages"][playlist_name] = {}
    pages = guild_states[interaction.guild.id]["playlist_pages"][playlist_name]
    max_page = len(pages)
    tracks = []

    while queue_copy:
        for _ in range(min(25, len(queue_copy))):
            tracks.append(queue_copy.pop(0))
        
        pages[max_page] = tracks
        tracks = []
        max_page += 1

# Function to reset states
async def get_default_settings(voice_client: discord.VoiceClient, curr_channel: discord.TextChannel) -> dict:
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
        "query_amount": 0,
        "max_queries": 0,
        "current_query": None,
        "current_track": None,
        "track_to_loop": None,
        "general_start_date": 0,
        "general_start_time": 0,
        "elapsed_time": 0,
        "start_time": 0,
        "queue": [],
        "queue_history": [],
        "queue_pages": {},
        "queue_to_loop": [],
        "history_pages": {},
        "playlist_pages": {},
        "locked_playlists": {},
        "pending_cleanup": False,
        "handling_disconnect_action": False,
        "interaction_channel": curr_channel,
        "greet_timeouts": {}
    }

# Functions for checking guild states and replying to interactions
async def check_channel(guild_states: dict, interaction: Interaction) -> bool:
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

async def check_current_track(guild_states: dict, interaction: Interaction) -> bool:
    if guild_states.get(interaction.guild.id):
        current_track = guild_states[interaction.guild.id]["current_track"]

        if current_track is None:
            await interaction.response.send_message("No track is currently playing!") if not interaction.is_expired() else\
            await interaction.channel.send("No track is currently playing!")
            return False
        
        return True

async def check_queue(guild_states: dict, interaction: Interaction, msg: str="Queue is empty.") -> bool:
    if guild_states.get(interaction.guild.id):
        queue = guild_states[interaction.guild.id]["queue"]

        if not queue:
            await interaction.response.send_message(msg) if not interaction.is_expired() else\
            await interaction.channel.send(msg)
            return False
        
        return True

async def check_history(guild_states: dict, interaction: Interaction, msg: str="Track history is empty.") -> bool:
    if guild_states.get(interaction.guild.id):
        history = guild_states[interaction.guild.id]["queue_history"]

        if not history:
            await interaction.response.send_message(msg) if not interaction.is_expired() else\
            await interaction.channel.send(msg)
            return False
        
        return True

async def check_guild_state(guild_states: dict, interaction: Interaction, state="is_modifying", condition: bool=True, msg: str="The queue is currently being modified, please wait."):
    if guild_states.get(interaction.guild.id):
        value = guild_states[interaction.guild.id][state]
        if value == condition:
            await interaction.response.send_message(msg) if not interaction.response.is_done() else\
            await interaction.followup.send(msg)
            return False
        
        return True

# Functions to update the copied queue when loopqueue is enabled.
async def update_loop_queue_replace(guild_states: dict, interaction: Interaction, old_track: dict, track: dict) -> None:
    if guild_states.get(interaction.guild.id):
        loop_queue = guild_states[interaction.guild.id]["queue_to_loop"]

        if old_track in loop_queue:
            for i, obj in enumerate(loop_queue):
                if obj == old_track:
                    loop_index = i
                    break
            
            loop_queue.remove(old_track)
            loop_queue.insert(loop_index, track)

async def update_loop_queue_remove(guild_states: dict, interaction: Interaction, tracks_to_remove) -> None:
    if guild_states.get(interaction.guild.id):
        queue = guild_states[interaction.guild.id]["queue"]
        loop_queue = guild_states[interaction.guild.id]["queue_to_loop"]

        for track_to_remove in tracks_to_remove:
            if track_to_remove not in queue and track_to_remove in loop_queue:
                loop_queue.remove(track_to_remove)

async def update_loop_queue_add(guild_states: dict, interaction: Interaction) -> None:
    if guild_states.get(interaction.guild.id):
        queue = guild_states[interaction.guild.id]["queue"]
        queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]

        for track in queue:
            if track not in queue_to_loop:
                queue_to_loop.append(track)

# Functions for updating guild states
async def update_query_extraction_state(guild_states: dict, interaction: Interaction, amount: int, max_amount: int, current: str | None):
    if guild_states.get(interaction.guild.id):
        guild_states[interaction.guild.id]["query_amount"] = amount
        guild_states[interaction.guild.id]["max_queries"] = max_amount
        guild_states[interaction.guild.id]["current_query"] = current

async def update_guild_state(guild_states: dict, interaction: Interaction, value: Any, state: str="is_modifying"):
    if guild_states.get(interaction.guild.id):
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
        ) -> dict | list[dict] | int:
        """ Extract a query from its website, catch any errors and return the result. """
        
        query = query.strip()

        if query == "":
            return RETURN_CODES["QUERY_IS_EMPTY"]

        await update_query_extraction_state(guild_states, interaction, extraction_state_amount, extraction_state_max_length, query_name.strip() if query_name is not None else query)

        query_type = get_query_type(query)
        if (forbid_type or only_allow_type) and query_type[1] == forbid_type if forbid_type is not None else\
                            query_type[1] != only_allow_type if only_allow_type is not None else None:
            return RETURN_CODES["QUERY_NOT_SUPPORTED"]

        extracted_track = await asyncio.to_thread(fetch, query, query_type)
        if extracted_track is None or (isinstance(extracted_track, list) and not extracted_track):
            return RETURN_CODES["BAD_EXTRACTION"]

        return extracted_track

async def fetch_queries(guild_states: dict,
        interaction: Interaction,
        queries: list[str | dict],
        query_names: list[str]=None,
        forbid_type: str=None,
        only_allow_type: str=None
    ) -> list[dict | list[dict]] | tuple[int, str]:
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

        if isinstance(extracted_query, int): # Error
            return (extracted_query, query)
        elif isinstance(extracted_query, list): # Found playlist
            for track in extracted_query:
                found.append(track)
        else: # Found single track
            found.append(extracted_query)
    
    return found

async def add_results_to_queue(interaction: Interaction, results: list[dict], queue: list, max_limit: int) -> None:
    """ Append found results to a queue in place and return None. Reply to the interaction if it exceeds max_limit. """

    for i, track_info in enumerate(results.copy()):
        if len(queue) >= max_limit:
            del results[i:] # This way the 'added tracks' embed only shows the actual added tracks instead of all of them.

            await interaction.channel.send(f"Maximum queue track limit of **{max_limit}** reached.\nCannot add other track(s).")
            break

        queue.append(track_info)

# Functions for checking input and queue, these functions also 'reply' to interactions
async def check_input_length(interaction: Interaction, max_limit: int, input_split: list) -> list:
    input_length = len(input_split)
    
    if input_length > max_limit:
        input_split = input_split[:max_limit]
        await interaction.channel.send(f"You can only add a maximum of **{max_limit}** tracks per command.\nYou were trying to add **{input_length}** tracks.\nOnly the first {max_limit} of those will be added.")

    return input_split

async def check_queue_length(interaction: Interaction, max_limit: int, queue: list) -> bool | int:
    queue_length = len(queue)
    if queue_length >= max_limit:
        await interaction.followup.send(f"Maximum queue track limit of **{max_limit}** reached.\nCannot add other track(s).") if interaction.response.is_done() else\
        await interaction.response.send_message(f"Maximum queue track limit of **{max_limit}** reached.\nCannot add other track(s).")
        return RETURN_CODES["QUEUE_TOO_LONG"]
    
    return True

# Functions for finding items
async def find_track(track: str, iterable: list[dict], by_index: bool=False) -> tuple[dict, int] | int:
    """ Find a track given its name or index in an iterable.\n
    returns a tuple with the track dictionary [0] and its index [1] or NOT_FOUND/NOT_A_NUMBER returncode\n
    if not found or `track` is not an index number and `by_index` is True. """
    
    if by_index:
        track = track.strip()
        if track.isdigit():
            index = max(1, min(int(track), len(iterable)))
            index -= 1

            return (iterable[index], index)
        
        return RETURN_CODES["NOT_A_NUMBER"]

    for i, track_info in enumerate(iterable):
        if track.lower().replace(" ", "") == track_info.get("title", "").lower().replace(" ", ""):
            return (track_info, i)
        
    return RETURN_CODES["NOT_FOUND"]

async def get_previous(current: dict | None, history: list[dict] | list) -> dict | int:
    if not history:
        return RETURN_CODES["HISTORY_IS_EMPTY"]
    
    length = len(history)
    amount_to_check = 2 if current is not None else 1

    if length < amount_to_check:
        return RETURN_CODES["NOT_ENOUGH_TRACKS"]
    
    return history[length - 2] if current is not None else history[length - 1] # len - 1 = current, len - 2 = actual previous track

async def try_index(iterable: list[Any], index: int, expected: Any) -> bool:
    """ Test an index and see if it contains anything.
    Return True if it matches `expected`, False otherwise or on IndexError """
    
    try:
        return iterable[index] == expected
    except (IndexError, Exception):
        return False

# Functions to get stuff from playlists.
async def get_tracks_from_playlist(usr_tracks: list[str], playlist: list[dict], by_index: bool=False) -> list[dict] | int:
    found = []
    for track in usr_tracks:
        track_info = await find_track(track, playlist, by_index)
        
        if track_info != RETURN_CODES["NOT_FOUND"] and\
            track_info != RETURN_CODES["NOT_A_NUMBER"]:
            found.append(track_info[0])

    return found if found else RETURN_CODES["NOT_FOUND"]

async def get_random_tracks_from_playlist(playlist: list[dict] | int, amount: int) -> list[dict] | int:
    found = []

    for _ in range(amount):
        chosen = choice(playlist)
        found.append(chosen)

    return found if found else RETURN_CODES["NOT_FOUND"]

# Apply playlist tracks' title and source website to tracks
# Has no effect on titles if users did not modify them.
async def replace_data_with_playlist_data(tracks: list[dict], data: list[dict]) -> None:
    """ Replaces a track's 'title' and 'source_website' keys' values with values from the playlist (data). """
    
    for track, playlist_track in zip(tracks, data):
        track["title"] = playlist_track["title"]
        track["source_website"] = playlist_track["source_website"]

# Remove/Reposition/etc. functions
async def remove_track_from_queue(tracks: list[str], queue: list[dict], by_index: bool=False) -> list[dict] | int:
    found = []
    
    for track in tracks:
        found_track = await find_track(track, queue, by_index)

        if found_track not in (RETURN_CODES["NOT_FOUND"], RETURN_CODES["NOT_A_NUMBER"]):
            removed_track = queue[found_track[1]] # Add and remove later to fix an issue where if by_index is used, wrong items at selected indices are removed.
            found.append(removed_track)
    
    for item in found:
        queue.remove(item)

    return found if found else RETURN_CODES["NOT_FOUND"]

async def reposition_track_in_queue(track: str, index: int, queue: list[dict], by_index: bool=False) -> tuple[dict, tuple[dict, int]] | int:
    found_track = await find_track(track, queue, by_index)
    if found_track in (RETURN_CODES["NOT_FOUND"], RETURN_CODES["NOT_A_NUMBER"]):
        return found_track

    if found_track[1] == index:
        return RETURN_CODES["SAME_INDEX_REPOSITION"]
    
    track_dict = queue.pop(found_track[1])
    queue.insert(index, track_dict)

    return track_dict, found_track

async def replace_track_in_queue(guild_states: dict,
        interaction: Interaction,
        track: str, 
        new_track: str,
        is_playlist: bool=False,
        playlist: list | None=None,
        by_index: bool=False
    ) -> tuple[dict, dict] | int:
    
    queue = guild_states[interaction.guild.id]["queue"] if not is_playlist and playlist is None else playlist
    queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]
    is_looping_queue = guild_states[interaction.guild.id]["is_looping_queue"]

    found_track = await find_track(track, queue, by_index)
    if found_track in (RETURN_CODES["NOT_FOUND"], RETURN_CODES["NOT_A_NUMBER"]):
        return found_track

    extracted_track = await fetch_query(guild_states, interaction, new_track, 1, 1, None, "YouTube Playlist")
    if isinstance(extracted_track, int):
        return extracted_track
    
    if playlist:
        extracted_track = {
            "title": extracted_track.get("title"),
            "uploader": extracted_track.get("uploader"),
            "duration": extracted_track.get("duration"),
            "webpage_url": extracted_track.get("webpage_url"),
            "source_website": extracted_track.get("source_website")
        }
    
    removed_track = queue.pop(found_track[1])
    queue.insert(found_track[1], extracted_track)

    if is_looping_queue and queue_to_loop and not playlist:
        await update_loop_queue_replace(guild_states, interaction, removed_track, extracted_track)

    return extracted_track, removed_track

async def edit_tracks_in_queue(max_name_length: int, queue: list[dict], tracks: str, new_names: str, by_index: bool=False) -> list[tuple[dict, str]] | list:
    tracks = split(tracks)
    new_names = split(new_names)
    found = []
    
    for track, new_name in zip(tracks, new_names):
        if len(new_name) > max_name_length:
            continue

        new_name = new_name.strip()

        found_track = await find_track(track, queue, by_index)
        if found_track not in (RETURN_CODES["NOT_FOUND"], RETURN_CODES["NOT_A_NUMBER"]):
            old_track = deepcopy(found_track[0])
            old_track_index = found_track[1]
            
            queue[old_track_index]["title"] = new_name
            found.append((old_track, new_name))

    return found

# Custom split
def split(s: str) -> list[str]:
    """ Allows to escape semicolons to search for stuff with them. """
    
    parts = re.split(r'(?<!\\);', s)
    return [part.replace(r'\;', ';') for part in parts]

# File lock function
async def ensure_lock(interaction: Interaction, locks: dict) -> None:
    if interaction.guild.id not in locks:
        locks[interaction.guild.id] = asyncio.Lock()

# Connect behaviour
async def greet_new_user_in_vc(guild_states: dict, voice_channel: discord.VoiceChannel, user: discord.Member) -> None:
    txt_channel = guild_states[user.guild.id]["interaction_channel"]
    timeout = guild_states[user.guild.id]["greet_timeouts"].get(user.id, False)

    if timeout:
        return

    await txt_channel.send(f"Welcome to **{voice_channel.name}**, {user.mention}!\nTotal users in **{voice_channel.name}**: `{len(voice_channel.members)}`")
    guild_states[user.guild.id]["greet_timeouts"][user.id] = True
    
    await asyncio.sleep(10) # prevents spam or 429s
    guild_states[user.guild.id]["greet_timeouts"][user.id] = False

# Disconnect behaviour
async def cleanup_guilds(guild_states: dict, clients: list[discord.VoiceClient]):
    guild_ids = [client.guild.id for client in clients]

    for guild_id in guild_states.copy().keys():
        if guild_id not in guild_ids:
            del guild_states[guild_id]
            del ROLE_LOCKS[guild_id]
            del PLAYLIST_LOCKS[guild_id]
            invalidate_cache(guild_id, PLAYLIST_FILE_CACHE)
            invalidate_cache(guild_id, ROLE_FILE_CACHE)

            log(f"[GUILDSTATE] Cleaned up guild ID {guild_id} from guild states, cache and locks.")

async def check_users_in_channel(guild_states: dict, playlist, member: discord.Member | Interaction) -> bool:
    """ Check if there are any users in a voice channel.
    Returns True if none are left and the bot is disconnected. """
    
    if VOICE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
        return True # bot is disconnected

    voice_client = guild_states[member.guild.id]["voice_client"]
    locked = guild_states[member.guild.id]["locked_playlists"]

    if guild_states[member.guild.id]["handling_disconnect_action"]:
        return False
    
    if len(voice_client.channel.members) > 1:
        return False

    if voice_client.is_connected() and\
        not voice_client.is_playing() and\
        not guild_states[member.guild.id]["is_extracting"] and\
        not guild_states[member.guild.id]["voice_client_locked"] and\
        not await playlist.is_locked(locked):

        log(f"[DISCONNECT] Disconnecting from channel ID {voice_client.channel.id} because no users are left in it and all conditions are met.")

        if voice_client.is_paused():
            await update_guild_state(guild_states, member, True, "stop_flag")

        await voice_client.disconnect() # rest is handled by disconnect_routine() (hopefully)
        return True

    return False

async def disconnect_routine(client: commands.Bot, guild_states: dict, member: discord.Member):
    if guild_states[member.guild.id]["pending_cleanup"] or\
        guild_states[member.guild.id]["handling_disconnect_action"]:
        log(f"[GUILDSTATE] Already handling a disconnect action for guild ID {member.guild.id}, ignoring.")
        return
            
    await update_guild_state(guild_states, member, True, "pending_cleanup")
    await update_guild_state(guild_states, member, True, "handling_disconnect_action")
    voice_client = guild_states[member.guild.id]["voice_client"]

    log(f"[GUILDSTATE] Waiting 10 seconds before cleaning up guild ID {member.guild.id}...")
    await asyncio.sleep(10) # Sleepy time :3 maybe it's a network issue

    if any(client.guild.id == member.guild.id for client in client.voice_clients): # Reconnected, all good
        log(f"[RECONNECT] Cleanup operation cancelled for guild ID {member.guild.id}")

        await update_guild_state(guild_states, member, False, "pending_cleanup")
        await update_guild_state(guild_states, member, False, "handling_disconnect_action")
        return
    
    """ Assumes the bot is disconnected before calling this function, which should be the case since disconnect_routine() gets triggered when there's a voice state update
    and the bot is no longer in a channel (after.channel is None) """
    voice_client.cleanup()

    """ Use this function instead of a simple 'del guild_states[member.guild.id]' so we catch
    any leftover guilds that were not properly cleaned up. """
    await cleanup_guilds(guild_states, client.voice_clients)

# FFmpeg options
async def get_ffmpeg_options(position: int) -> dict:
    FFMPEG_OPTIONS_COPY = FFMPEG_OPTIONS.copy()

    FFMPEG_OPTIONS_COPY["before_options"] = f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -ss {position}"
    FFMPEG_OPTIONS_COPY["options"] = f"-vn -ss 0 -loglevel quiet" # -ss 0 here seems to sync the position more accurately

    return FFMPEG_OPTIONS_COPY

# Moderation utilities
async def get_channel(channels: list, value: str | int, ch_type: discord.ChannelType=discord.ChannelType.text) -> discord.TextChannel | None:
    """ Return a channel based on the given name/ID and the type.\n
    Return None if not found. """
    
    channel = None

    funcs = [
        lambda: discord.utils.get(channels, name=value, type=ch_type),
        lambda: discord.utils.get(channels, id=int(value) if value.isdigit() else None, type=ch_type)
    ]
    
    for func in funcs:
        channel = func()

        if channel is not None:
            break

    return channel

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
