""" Embed helpers module for discord.py bot. """

import discord
from random import randint
from datetime import datetime
from typing import Any

# Helpers
def _add_until_max_reached(embed: discord.Embed, to_add: list[dict[str, str | bool]]) -> None:
    """ Add fields using defined arguments in `to_add` up to 24, after that add a final field with '+ More'.
     
    `to_add` must be a list of dictionaries containing the following keys for each entry:

    `name`: The name of the embed field
    
    `value`: The value of the embed field
    
    `inline`: The inline value of the embed field
     
    """

    for i, entry in enumerate(to_add):
        name = entry.get("name", "None")
        value = entry.get("value", "None")
        inline = entry.get("inline", False)
        
        if i < 24:
            embed.add_field(name=name, value=value, inline=inline)
        else:
            embed.add_field(name="+ More", value="", inline=False)
            break

def _add_all(embed: discord.Embed, to_add: list[dict[str, str | bool]]) -> None:
    """ Similar to `_add_until_max_reached()` but all items (up to 25) in `to_add` are added and no '+ More' final field is added. """
    
    for entry in to_add[:25]:
        name = entry.get('name', 'None')
        value = entry.get('value', 'None')
        inline = entry.get('inline', False)

        embed.add_field(name=name, value=value, inline=inline)

def _get_embed(title: str, colour: discord.Colour | None=None, timestamp: datetime | None=None) -> discord.Embed:
    """ Generate an Embed object given basic arguments. 
    
    if `colour` or `timestamp` are `None`, defaults will be used. """
    
    colour = colour or discord.Colour.random(seed=randint(1, 1000))
    timestamp = timestamp or datetime.now()

    return discord.Embed(
        title=title,
        colour=colour,
        timestamp=timestamp
    )

# Embed creator functions
def generate_epoch_embed(join_time: str, elapsed_time: str) -> discord.Embed:
    """ Generated an embed showing elapsed time since the very first track. """
    
    embed = _get_embed("Total elapsed time")
    embed.add_field(name=f"Since {join_time}", value=f"[ `{elapsed_time}` ]", inline=False)

    return embed

def generate_added_track_embed(added: list[dict[str, Any]], is_playlist: bool=False) -> discord.Embed:
    """ Generate an embed of up to 24 added tracks. """
    
    to_add = [
        {
            "name": f"[ `{result.get('title', 'Unknown')}` ]",
            "value": f"Author: [ `{result.get('uploader', 'Unknown')}` ]; Duration: [ `{result.get('duration', 'Unknown')}` ]; Source: [ `{result.get('source_website', 'Unknown')}` ]",
            "inline": False
        } for result in added
    ]

    embed = _get_embed(f"{'Playlist' if is_playlist else 'Queue'} update: Added tracks")
    _add_until_max_reached(embed, to_add)

    return embed

def generate_skipped_tracks_embed(skipped: list[dict[str, Any]]) -> discord.Embed:
    """ Generate an embed to show the amount of skipped tracks. """
    
    to_add = [
        {
            "name": f"[ `{result.get('title', 'Unknown')}` ]",
            "value": f"Author: [ `{result.get('uploader', 'Unknown')}` ]; Duration: [ `{result.get('duration', 'Unknown')}` ]; Source: [ `{result.get('source_website', 'Unknown')}` ]",
            "inline": False
        } for result in skipped
    ]

    embed = _get_embed(f"Skipped {'tracks' if len(skipped) > 1 else 'track'}")
    _add_until_max_reached(embed, to_add)

    return embed

def generate_removed_tracks_embed(removed: list[dict[str, Any]], is_playlist: bool=False) -> discord.Embed:
    """ Generate an embed showing the removed tracks from a queue. """

    to_add = [
        {
            "name": f"[ `{result.get('title', 'Unknown')}` ]",
            "value": f"Author: [ `{result.get('uploader', 'Unknown')}` ]; Duration: [ `{result.get('duration', 'Unknown')}` ]; Source: [ `{result.get('source_website', 'Unknown')}` ]",
            "inline": False
        } for result in removed
    ]
    
    embed = _get_embed(f"{'Queue' if not is_playlist else 'Playlist'} update: Removed tracks")
    _add_until_max_reached(embed, to_add)

    return embed

def generate_renamed_tracks_embed(renamed: list[tuple[dict, str]]) -> discord.Embed:
    """ Generate an embed to show renamed tracks in a queue.
    
    `renamed` is a list of tuples with old track (`dict`) and new name (`str`). """
    
    to_add = [
        {
            "name": f"[ `{result.get('title', 'Unknown')}` ] --> [ `{new_name}` ]",
            "value": f"Author: [ `{result.get('uploader', 'Unknown')}` ]; Duration: [ `{result.get('duration', 'Unknown')}` ]; Source: [ `{result.get('source_website', 'Unknown')}` ]",
            "inline": False
        } for result, new_name in renamed
    ]

    embed = _get_embed("Playlist update: Renamed tracks")
    _add_until_max_reached(embed, to_add)

    return embed

def generate_playlists_embed(names: list[str], remaining: int) -> discord.Embed:
    to_add = [
        {
            "name": f"{i+1}. [ `{name}` ]",
            "value": "",
            "inline": False
        } for i, name in enumerate(names)
    ]
    
    embed = _get_embed("Saved playlists")
    _add_until_max_reached(embed, to_add)
    
    embed.set_footer(text=f"Remaining slots: {remaining}")

    return embed

def generate_current_track_embed(
        info: dict[str, Any],
        queue: list | list[dict[str, Any]],
        queue_to_loop: list | list[dict[str, Any]],
        track_to_loop: dict[str, Any] | None,
        elapsed_time: int,
        looping: bool,
        random: bool,
        is_looping_queue: bool,
        is_modifying_queue: bool,
        filters: dict[str, Any]
    ) -> discord.Embed:
    """ Generate an embed to show detailed info about the current track. """

    embed = _get_embed("Now Playing")

    embed.add_field(name="Title", value=f"[ `{info.get('title')}` ]", inline=True)
    embed.add_field(name="Author", value=f"[ `{info.get('uploader')}` ]", inline=True)
    embed.add_field(name="Upload date", value=f"[ `{info.get('upload_date')}` ]", inline=False)
    embed.add_field(name="Duration", value=f"[ `{info.get('duration')}` ]", inline=True)
    embed.add_field(name="Elapsed time", value=f"[ `{elapsed_time}` ]", inline=True)
    embed.add_field(
        name="Next track",
        value=f"[ `{track_to_loop.get('title')} (looping)` ]" if looping else\
        "[ `Filtered` ]" if filters else\
        "[ `Random` ]" if random else\
        f"[ `Unable to read next track` ]" if is_modifying_queue else\
        f"[ `{queue[0].get('title', 'Unknown')}` ]" if len(queue) > 0 else\
        f"[ `{queue_to_loop[0].get('title', 'Unknown')}` ]" if queue_to_loop else\
        "[ `None` ]",
        inline=False
    )
    embed.add_field(name="Extra options:", value="", inline=False)
    embed.add_field(name="Loop", value="[ `Enabled` ]" if looping else "[ `Disabled` ]", inline=True)
    embed.add_field(name="Randomization", value="[ `Enabled` ]" if random else "[ `Disabled` ]", inline=True)
    embed.add_field(name="Queue loop", value="[ `Enabled` ]" if is_looping_queue else "[ `Disabled` ]", inline=True)
    embed.add_field(name="Filters", value="[ `Enabled` ]" if filters else "[ `Disabled` ]", inline=True)
    embed.add_field(name="Source", value=f"[ `{info.get('source_website', 'Unknown')}` ]", inline=False)
    embed.set_image(url=info.get("thumbnail", None))
    embed.set_footer(text=f"Total tracks in queue: {len(queue) if not is_modifying_queue else 'Unknown'}")

    return embed

def generate_generic_track_embed(info: dict[str, Any], embed_title: str="Track info") -> discord.Embed:
    """ Generate an embed to show some info about an `info` track object. """
    
    embed = _get_embed(embed_title)

    embed.add_field(name="Title", value=f"[ `{info.get('title', 'Unknown')}` ]", inline=True)
    embed.add_field(name="Author", value=f"[ `{info.get('uploader', 'Unknown')}` ]", inline=True)
    embed.add_field(name="Upload date", value=f"[ `{info.get('upload_date', 'Unknown')}` ] ", inline=False)
    embed.add_field(name="Duration", value=f"[ `{info.get('duration', 'Unknown')}` ]", inline=True)
    embed.add_field(name="Webpage", value=f"[ `{info.get('webpage_url', 'Unknown')}` ]", inline=False)
    embed.add_field(name="Source", value=f"[ `{info.get('source_website', 'Unknown')}` ]", inline=True)
    embed.add_field(name="Thumbnail", value="", inline=False)
    embed.set_image(url=info.get("thumbnail", None))

    return embed

def generate_extraction_progress_embed(current_item_name: str, total: int, current: int, website: str) -> discord.Embed:
    """ Generate an embed to show current extraction progress. """
    
    embed = _get_embed("Extraction progress")

    embed.add_field(name=f"Currently extracting from {website}", value=f"`'{current_item_name}'`", inline=False)
    embed.add_field(name=f"Extracted **{current}** out of **{total}** queries.", value="", inline=False)

    return embed

def generate_queue_page_embed(queue_page: list[dict[str, Any]], page: int, page_length: int, is_history: bool=False, is_playlist: bool=False) -> discord.Embed:
    """ Generate an embed to show tracks in a queue page.
    
    `queue` is a list of 25 tracks. """
    
    to_add = [
        {
            "name": f"[ `{result.get('title', 'Unknown')}` ]",
            "value": f"Author: [ `{result.get('uploader', 'Unknown')}` ]; Duration: [ `{result.get('duration', 'Unknown')}` ]; Source: [ `{result.get('source_website', 'Unknown')}` ]",
            "inline": False
        } for result in queue_page
    ]

    embed = _get_embed(f"{'Playlist' if is_playlist else 'Queue' if not is_history else 'History'} - Page {page + 1} {'(End)' if page == page_length - 1 else ''}")
    _add_all(embed, to_add)
    
    embed.set_footer(text=f"Total tracks in page: {len(queue_page)}")

    return embed

def generate_ping_embed(websocket: float, response: float) -> discord.Embed:
    """ Generate an embed for websocket and response latency """

    websocket = round(websocket * 1000, 1)
    response = round(response * 1000, 1)
    
    embed = _get_embed("Pong!", discord.Colour.blurple() if websocket <= 300 else discord.Colour.red())

    embed.add_field(name="Websocket latency", value=f"[ `{websocket}ms` ]", inline=True)
    embed.add_field(name="Response latency", value=f"[ `{response}ms` ]", inline=True)

    return embed