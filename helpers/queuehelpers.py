""" Queue helper functions for discord.py bot """

from error import Error
from webextractor import SourceWebsite, YOUTUBE_DOMAINS, SOUNDCLOUD_DOMAINS, BANDCAMP_DOMAINS
from helpers.timehelpers import format_to_seconds, format_to_minutes
from helpers.extractorhelpers import fetch_query
from init.constants import RAW_FILTER_TO_VISUAL_TEXT, NEED_FORMATTING_FILTERS

import re
from discord.interactions import Interaction
from discord import app_commands
from typing import Any
from copy import deepcopy
from random import randint, sample

# Function to get a hashmap of queue pages to display
def get_pages(queue: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """ Create a hashmap of queue pages. Each page is 25 elements log.
    Must be sent to a thread, as it contains blocking code. """
    
    queue_copy = deepcopy(queue)
    pages = {}
    tracks = []
    max_page = 0

    while queue_copy:
        for _ in range(min(25, len(queue_copy))):
            tracks.append(queue_copy.pop(0))
        
        pages[max_page] = tracks
        tracks = []
        max_page += 1

    return pages

# Functions to update the copied queue when /queueloop is enabled.
async def update_loop_queue_replace(guild_states: dict[str, Any], interaction: Interaction, old_track: dict[str, Any], track: dict[str, Any]) -> None:
    """ Update the `queue_to_loop` state with the `old` and `new` output of a replace track function.

    This function must be called after replacing an item from the `queue` state and `is_looping_queue` state is active. """
    
    if interaction.guild.id in guild_states:
        queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]

        if old_track in queue_to_loop:
            for i, obj in enumerate(queue_to_loop):
                if obj == old_track:
                    loop_index = i
                    break
            
            queue_to_loop.remove(old_track)
            queue_to_loop.insert(loop_index, track)

async def update_loop_queue_remove(guild_states: dict[str, Any], interaction: Interaction, tracks_to_remove: list[dict[str, Any]]) -> None:
    """ Update the `queue_to_loop` state by removing items that are not in the `queue` state.

    This function must be called after removing items from the `queue` state and `is_looping_queue` state is active. """
    
    if interaction.guild.id in guild_states:
        queue = guild_states[interaction.guild.id]["queue"]
        queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]

        for track_to_remove in tracks_to_remove:
            if track_to_remove not in queue and track_to_remove in queue_to_loop:
                queue_to_loop.remove(track_to_remove)

async def update_loop_queue_add(guild_states: dict[str, Any], interaction: Interaction) -> None:
    """ Update the `queue_to_loop` state with the latest extracted items from `queue`.

    This function must be called after new tracks have been added to the queue and the `is_looping_queue` state is True. """
    
    if interaction.guild.id in guild_states:
        queue = guild_states[interaction.guild.id]["queue"]
        queue_to_loop = guild_states[interaction.guild.id]["queue_to_loop"]

        for track in queue:
            if track not in queue_to_loop:
                queue_to_loop.append(track)

# Functions for checking input and queue, these functions also 'reply' to interactions
async def check_input_length(interaction: Interaction, max_limit: int, input_split: list[Any], msg_on_fail: str | None=None) -> list[Any]:
    """ Check a split input's length and compare it to a given maximum limit.

    If it exceeds the limit, reply to the interaction with `msg_on_fail` or a default message and slice the input up to the `max_limit`. 
    Otherwise, return the given `input_split`. """
    
    default_msg = msg_on_fail or f"You can only add a maximum of **{max_limit}** tracks per command.\nOnly the first **{max_limit}** of your command will be added."
    input_length = len(input_split)
    
    if input_length > max_limit:
        await interaction.channel.send(default_msg)
        return input_split[:max_limit]

    return input_split

async def check_queue_length(interaction: Interaction | None, max_limit: int, queue: list, msg_on_fail: str | None=None, return_error: bool=False) -> bool | Error:
    """ Check a queue's length and compare it to a given maximum limit.

    If it exceeds the limit and `return_error` is False and `interaction` is not None, reply to the interaction with `msg_on_fail` or a default message and return False. 
    Otherwise, return an Error object with `msg`=`msg_on_fail` or a default message. """
    
    default_msg = msg_on_fail or f"Maximum queue track limit of **{max_limit}** reached.\nCannot add other track(s)."
    queue_length = len(queue)

    if queue_length >= max_limit:
        if interaction is not None and not return_error:
            await interaction.followup.send(default_msg) if interaction.response.is_done() else\
            await interaction.response.send_message(default_msg)
            
            return False
        else:
            return Error(default_msg)
    
    return True

# Input sanitation & validation
async def sanitize_name(name: str) -> str:
    """ Sanitize a playlist name by removing unwanted chars and additionally, return a fixed name if the sanitized one is empty. """
    
    return name.replace("\\", "").strip() or "Untitled"

async def name_exceeds_length(limit: int, name: str) -> bool:
    """ Check if a name exceeds length `limit`.

    Returns a boolean. """
    
    return len(name) > limit

# Functions for finding items
async def find_track(track: str, iterable: list[dict[str, Any]], by_index: bool=False) -> tuple[dict[str, Any], int] | Error:
    """ Find a track given its name or index in an iterable.

    Returns a tuple with the track hashmap [0] and its index [1] or an Error object. """
    
    if by_index:
        track = track.strip()

        if not track.isdigit():
            return Error(f"**{track[:50]}** is not an integer number!")
        
        track_index = int(track)

        if track_index < 1 or track_index > len(iterable):
            return Error(f"Given index (**{track_index}**) is out of bounds!")

        return iterable[track_index - 1], track_index - 1

    for i, track_info in enumerate(iterable):
        if track.lower().replace(" ", "") == track_info["title"].lower().replace(" ", ""):
            return track_info, i
        
    return Error(f"Could not find track **{track[:50]}**.")

async def get_previous_visual_track(current: dict[str, Any] | None, history: list[dict[str, Any]] | list) -> dict[str, Any] | Error:
    """ Return the previous track in an iterable `history` based on the current track.

    Does not remove the returned track. """
    
    if not history:
        return Error("Track history is empty. Nothing to show.")
    
    length = len(history)
    amount_to_check = 2 if current is not None else 1

    if length < amount_to_check:
        return Error("There's no previous track to show.")
    
    return history[length - 2] if current is not None else history[length - 1] # len - 1 = current, len - 2 = actual previous track

async def get_next_visual_track(
        is_random: bool, 
        is_looping: bool, 
        track_to_loop: dict[str, Any] | None, 
        filters: dict[str, Any] | None, 
        queue: list[dict[str, Any]], 
        queue_to_loop: list[dict[str, Any]]
    ) -> dict[str, Any] | Error:
    """ Get the next track in an iterable `queue` (and `queue_to_loop`) based on different states.

    Does not remove the returned track from the queue. """
    
    if is_looping and track_to_loop:
        next_track = track_to_loop
    elif is_random:
        return Error("Next track will be random.")
    elif filters:
        return Error(
            f"Next track will be chosen according to these filters.\n"+
            await get_active_filter_string(filters)
        )
    elif queue:
        next_track = queue[0]
    elif queue_to_loop:
        next_track = queue_to_loop[0]
    else:
        return Error("Queue is empty. Nothing to preview.")
    
    return next_track

async def get_next_track(
        is_random: bool, 
        is_looping: bool, 
        track_to_loop: dict[str, Any] | None, 
        filters: dict[str, Any] | None, 
        queue: list[dict[str, Any]]
    ) -> dict[str, Any]:
    """ Get the next track based on different states.

    Removes the returned track from the queue. """
    
    if is_looping and track_to_loop:
        next_track = track_to_loop
    elif filters:
        next_track = await find_next_filtered_track(queue, filters)
    elif is_random:
        next_track = queue.pop(randint(0, len(queue) - 1))
    else:
        next_track = queue.pop(0)
    
    return next_track

async def try_index(iterable: list[Any], index: int, expected: Any) -> bool:
    """ Test an index and see if it contains anything.

    Return True if it matches `expected`, False otherwise or on IndexError """
    
    try:
        return iterable[index] == expected
    except IndexError:
        return False

async def get_queue_indices(queue: list[dict[str, Any]], tracks: list[dict[str, Any]]) -> list[int]:
    """ Return the queue 1-based indices matching each item in `tracks`. """

    indices = []
    seen = set()

    for usr_track in tracks:
        for i, queue_track in enumerate(queue):
            if queue_track == usr_track and i not in seen:
                indices.append(i + 1)
                seen.add(i)

                break

    return indices

# Playback filters
async def get_added_filter_string(filters: dict[str, Any], added: dict[str, bool]) -> str:
    """ Return a string with added filters ready to be sent to the text channel. """
    
    string = str()

    for filter_name, added_status in added.items():
        if added_status:
            string += f"**{RAW_FILTER_TO_VISUAL_TEXT[filter_name]}**: [ `{filters.get(filter_name) if filter_name not in NEED_FORMATTING_FILTERS else format_to_minutes(filters.get(filter_name))}` ]\n"
    
    return string

async def get_removed_filter_string(removed: dict[str, bool]) -> str:
    """ Return a string with removed filters ready to be sent to the text channel. """
    
    string = str()

    for filter_name, removed_status in removed.items():
        if removed_status:
            string += f"**{RAW_FILTER_TO_VISUAL_TEXT[filter_name]}**: [ `Removed` ]\n"

    return string

async def get_active_filter_string(filters: dict[str, Any]) -> str:
    """ Return a string with active filters ready to be sent to the text channel. """
    
    string = str()

    for filter, value in filters.items():
        string += f"**{RAW_FILTER_TO_VISUAL_TEXT[filter]}**: [ `{value if filter not in NEED_FORMATTING_FILTERS else format_to_minutes(value)}` ]\n"

    return string

async def add_filters(filters: dict[str, Any], to_add: dict[str, Any]) -> dict[str, bool]:
    """ Get a filter hashmap based on given input. 
    
    Return a hashmap with k-v pairs where key is added filter and value is whether or not it's enabled. """

    added = {}
        
    for key, filter in to_add.items():
        if filter is not None:
            filters[key] = filter
            added[key] = True

    return added

async def clear_filters(filters: dict[str, Any], to_remove: dict[str, bool]) -> dict[str, bool]:
    """ Remove given filters from `filters`. 
    
    Return a hashmap with k-v pairs where key is removed filter and value is whether or not it's disabled. """
    
    removed = {}

    for key, filter in to_remove.items():
        if filter and key in filters:
            del filters[key]
            removed[key] = True

    return removed

async def match_website_filter(filter_website: str, track_website: str) -> bool:
    """ Return a match result between a website filter and a track website. 
    
    Match all query types that are part of a website. (e.g. `filter_website` SoundCloud can match SoundCloud Playlist and Search)"""
    
    match filter_website:
        case SourceWebsite.SOUNDCLOUD.value:
            return track_website in SOUNDCLOUD_DOMAINS
        case SourceWebsite.YOUTUBE.value:
            return track_website in YOUTUBE_DOMAINS
        case SourceWebsite.BANDCAMP.value:
            return track_website in BANDCAMP_DOMAINS
        case _:
            return filter_website == track_website

async def match_filters(track: dict[str, Any], filters: dict[str, Any]) -> bool:
    """ Match given `filters` to `track`. 
    
    Possible matches are: Uploader, Duration and Website"""
    
    matches = []
    track_uploader, track_duration, track_website = track.get("uploader"), format_to_seconds(track.get("duration")), track.get("source_website")
    
    filter_uploader = filters.get("uploader")
    filter_min_duration, filter_max_duration = filters.get("min_duration") or float("-inf"), filters.get("max_duration") or float("inf")
    filter_website = filters.get("source_website")
    
    if filter_uploader:
        matches.append(filter_uploader.lower().replace(" ", "") == track_uploader.lower().replace(" ", ""))
    if filter_min_duration or filter_max_duration:
        matches.append(filter_min_duration <= track_duration <= filter_max_duration)
    if filter_website:
        matches.append(await match_website_filter(filter_website, track_website))

    return all(matches)

async def find_next_filtered_track(queue: list[dict[str, Any]], filters: dict[str, Any]) -> dict[str, Any]:
    """ Find the next track with the given filters. 
    
    Returns the matching track or the next one. """
    
    for i, track in enumerate(queue.copy()):
        if await match_filters(track, filters):
            return queue.pop(i)
        
    return queue.pop(0)

# Functions to get stuff from playlists.
async def get_tracks_from_queue(track_names: list[str], queue: list[dict[str, Any]], by_index: bool=False) -> list[dict[str, Any]] | Error:
    """ Get track objects from an interable `queue` based on their names (or indices). 
    
    Returns a list of tracks or Error. """
    
    found = []
    for name in track_names:
        track_info = await find_track(name, queue, by_index)
        
        if isinstance(track_info, Error):
            return track_info
        
        found.append(track_info[0])

    return found if found else Error("Could not find given tracks.")

async def get_random_tracks_from_queue(queue: list[dict[str, Any]], amount: int, max_limit: int=25) -> list[dict[str, Any]] | Error:
    """ Return random amount of tracks from an interable `queue`. """
    
    if amount < 0:
        return Error(f"Amount cannot be less than 0.")
    elif len(queue) < amount:
        return Error(f"Given amount (**{amount}**) is higher than the queue's length!")
    elif amount > max_limit:
        return Error(f"Given amount is higher than the maximum allowed limit. (**{max_limit}**)")

    return sample(queue, amount)

# Apply playlist tracks' title and source website to tracks
# Has no effect on titles if users did not modify them.
async def replace_data_with_playlist_data(tracks: list[dict[str, Any]], playlist: list[dict[str, Any]]) -> None:
    """ Replaces a track's 'title' and 'source_website' keys' values with values from the playlist. """
    
    for track, playlist_track in zip(tracks, playlist):
        track["title"] = playlist_track["title"]
        track["source_website"] = playlist_track["source_website"]

# Functions to modify a queue
async def remove_track_from_queue(tracks: list[str], queue: list[dict[str, Any]], by_index: bool=False) -> list[dict[str, Any]] | Error:
    """ Remove given `tracks` from iterable `queue`.
     
    Returns removed tracks or Error. """
    
    removed = []
    to_remove = set()
    
    for track in tracks:
        found_track = await find_track(track, queue, by_index)

        if isinstance(found_track, Error):
            return found_track
        
        to_remove.add(found_track[1])
        removed.append(found_track[0])

    for index in sorted(to_remove, reverse=True):
        queue.pop(index)

    return removed if removed else Error("Could not find given tracks.")

async def reposition_track_in_queue(track: str, index: int, queue: list[dict[str, Any]], by_index: bool=False) -> tuple[dict[str, Any], int, int] | Error:
    """ Repositions a track to a new index in an iterable `queue`.
    
    Returns a tuple with found track [0], old 1-based index [1], and new 1-based index [2] or Error. """
    
    if index < 1 or index > len(queue):
        return Error(f"Given new index (**{index}**) is out of bounds!")

    found_track = await find_track(track, queue, by_index)
    if isinstance(found_track, Error):
        return found_track

    if found_track[1] == index - 1:
        return Error(f"Track **{found_track[0]['title'][:50]}** is already at index **{index}**!")
    
    track_dict = queue.pop(found_track[1])
    queue.insert(index - 1, track_dict)

    return track_dict, found_track[1] + 1, index

async def replace_track_in_queue(
        guild_states: dict[str, Any],
        interaction: Interaction,
        queue: list[dict[str, Any]],
        track: str, 
        new_track: str,
        provider: app_commands.Choice | None=None,
        is_playlist: bool=False,
        by_index: bool=False
    ) -> tuple[dict[str, Any], dict[str, Any]] | Error:
    """ Replace a track in an iterable `queue` by extracting a new one.
    
    Returns a tuple with old track [0] and new one [1] or Error. """
    
    found_track = await find_track(track, queue, by_index)
    if isinstance(found_track, Error):
        return found_track

    allowed_query_types = (
        SourceWebsite.YOUTUBE.value, 
        SourceWebsite.YOUTUBE_SEARCH.value, 
        SourceWebsite.SOUNDCLOUD.value, 
        SourceWebsite.SOUNDCLOUD_SEARCH.value, 
        SourceWebsite.BANDCAMP.value,
        SourceWebsite.NEWGROUNDS.value
    )
    provider = provider.value if provider else None

    extracted_track = await fetch_query(guild_states, interaction, new_track, allowed_query_types=allowed_query_types, provider=provider)
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

    if extracted_track["webpage_url"] == found_track[0]["webpage_url"]:
        return Error(f"Cannot replace a track (**{found_track[0]['title']}**) with the same one.")
    
    removed_track = queue.pop(found_track[1])
    queue.insert(found_track[1], extracted_track)

    return extracted_track, removed_track

async def rename_tracks_in_queue(max_name_length: int, queue: list[dict[str, Any]], names: list[str], new_names: list[str], by_index: bool=False) -> list[tuple[dict[str, Any], str]] | Error:
    """ Bulk renames tracks in an iterable `queue`.
     
    Returns a list with a tuple with track object [0] and new name [1] or Error. """

    renamed, seen = [], set()

    old_names_length = len(names)
    new_names_length = len(new_names)

    if old_names_length != new_names_length:
        return Error(f"Old names (**{old_names_length}**) don't correspond to new names! (**{new_names_length}**)")

    for track, new_name in zip(names, new_names):
        new_name = new_name.strip()
        
        if not new_name:
            return Error("New name cannot be empty.")
        elif len(new_name) > max_name_length:
            return Error(f"Name **{new_name[:max_name_length]}** is too long! Must be <= **{max_name_length}** characters.")

        found_track = await find_track(track, queue, by_index)

        if isinstance(found_track, Error):
            return found_track
        elif new_name.replace(" ", "") == found_track[0]["title"].replace(" ", ""):
            return Error(f"Cannot rename a track (**{found_track[0]['title'][:max_name_length]}**) to the same name (**{new_name[:max_name_length]}**).")
        elif found_track[1] in seen:
            return Error(f"Track **{found_track[0]['title'][:50]}** was already renamed during this operation!")
        
        old_track = deepcopy(found_track[0])
        old_track_index = found_track[1]
        
        queue[old_track_index]["title"] = new_name

        renamed.append((old_track, new_name))
        seen.add(old_track_index)

    return renamed if renamed else Error(f"Could not find given tracks.")

async def place_track_in_playlist(queue: list, index: int | None, track: dict[str, Any]) -> tuple[dict[str, Any], int] | Error:
    """ Place a track at a specified or last index in an iterable `queue`.
    
    Returns a tuple with placed track [0] and its index [1]. """
    
    if index is None:
        index = len(queue) + 1
    elif index < 1 or index > len(queue):
        return Error(f"Given index (**{index}**) is out of bounds!")
    
    playlist_track = {
        'title': track['title'],
        'uploader': track['uploader'],
        'duration': track['duration'],
        'webpage_url': track['webpage_url'],
        'source_website': track['source_website']
    }

    if playlist_track in queue and await try_index(queue, index - 1, playlist_track):
        return Error(f"Cannot place track (**{track['title'][:50]}**) because it already exists at the specified index.")
    
    queue.insert(index - 1, playlist_track)

    return playlist_track, index

async def skip_tracks_in_queue(queue: list[dict[str, Any]], current_track: dict[str, Any], is_random: bool, is_looping: bool, amount: int=1) -> list[dict[str, Any]] | Error:
    """ Skip a specified amount of tracks in a queue. """
    
    if amount < 0:
        return Error("Amount cannot be less than 0.")
    elif amount > len(queue):
        return Error(f"Given amount (**{amount}**) is higher than the queue's length!")
    elif amount > 25:
        return Error("Amount can only be less than 25.")

    skipped = []
    if amount > 1 and not is_random and not is_looping:
        for _ in range(amount):
            if len(queue) > 0:
                skipped.append(queue.pop(0))
            else:
                break

        skipped.insert(0, current_track)

    return skipped

# Custom split
def split(s: str) -> list[str]:
    """ Custom split. Use `re.split` to split an item on each semicolon with the exception when it's prefixed with a backslash ('\\\\'). """
    
    parts = re.split(r'(?<!\\);', s)
    return [part.replace(r'\;', ';') for part in parts]
