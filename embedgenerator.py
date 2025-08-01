""" Embed generator module for discord.py bot. """

from settings import *

def generate_epoch_embed(join_time: datetime, elapsed_time: str) -> discord.Embed:
    embed = discord.Embed(
        title="Total elapsed time",
        colour=discord.Colour.random(seed=randint(1, 1000)),
        timestamp=datetime.now()
    )

    embed.add_field(name=f"Since [ `{join_time}` ]", value=elapsed_time, inline=False)

    return embed

def generate_added_track_embed(results: list[dict], is_playlist: bool=False) -> discord.Embed:
    embed = discord.Embed(
        title=f"{'Playlist' if is_playlist else 'Queue'} update: Added tracks",
        colour=discord.Colour.random(seed=randint(1, 1000)),
        timestamp=datetime.now()
    )

    for i, track in enumerate(results):
        if i < 24:
            embed.add_field(name=f"[ `{track.get("title", "Unknown")}` ]",
                            value=f"Author: [ `{track.get('uploader', 'Unknown')}` ], Duration: [ `{track['duration']}` ], Source: [ `{track['source_website']}` ]",
                            inline=False)
        else:
            embed.add_field(name="+ More", value="", inline=False)
            break

    return embed

def generate_skipped_tracks_embed(skipped: list[dict]):
    embed = discord.Embed(
        title=f"Skipped {'tracks' if len(skipped) > 1 else 'track'}",
        colour=discord.Colour.random(seed=randint(1, 1000)),
        timestamp=datetime.now()
    )

    for i, track in enumerate(skipped):
        if i < 24:
            embed.add_field(name=f"[ `{track.get("title", "Unknown")}` ]",
                            value=f"Author: [ `{track.get('uploader', 'Unknown')}` ]; Duration: [ `{track['duration']}` ]; Source: [ `{track['source_website']}` ]",
                            inline=False)

    return embed

def generate_removed_tracks_embed(found: list[dict], is_playlist: bool=False):
    embed = discord.Embed(
        title=f"{'Queue' if not is_playlist else 'Playlist'} update: Removed tracks",
        colour=discord.Colour.random(seed=randint(1, 1000)),
        timestamp=datetime.now()
    )

    for i, track in enumerate(found):
        if i < 24:
            embed.add_field(name=f"[ `{track.get("title", "Unknown")}` ]",
                            value=f"Author: [ `{track.get('uploader', 'Unknown')}` ]; Duration: [ `{track['duration']}` ]; Source: [ `{track['source_website']}` ]",
                            inline=False)
        else:
            embed.add_field(name="+ More",value="",inline=False)
            break

    return embed

def generate_edited_tracks_embed(found: list[dict]):
    embed = discord.Embed(
        title="Playlist update: Renamed tracks",
        colour=discord.Colour.random(seed=randint(1, 1000)),
        timestamp=datetime.now()
    )

    for i, (track, new) in enumerate(found):
        if i < 24:
            embed.add_field(name=f"[ `{track['title']}` ] --> [ `{new}` ]",
                            value=f"Author: [ `{track.get('uploader', 'Unknown')}` ]; Duration: [ `{track['duration']}` ]; Source: [ `{track['source_website']}` ]",
                            inline=False
            )
        else:
            embed.add_field(name="+ More", value="", inline=False)
            break

    return embed

def generate_current_track_embed(
        info: dict,
        queue: list | list[dict],
        queue_to_loop: list | list[dict],
        track_to_loop: dict | None,
        elapsed_time: int,
        looping: bool,
        random: bool,
        queueloop: bool,
        is_modifying_queue: bool
    ) -> discord.Embed:
    embed = discord.Embed(
        title="Now Playing",
        colour=discord.Colour.random(seed=randint(1, 1000)),
        timestamp=datetime.now()
    )

    if is_modifying_queue:
        short_queue_val = "`[ Unable to read queue ]`"
    elif len(queue) > 25:
        short_queue_val = ", ".join([f"`{track["title"]}`" for track in queue[:25]])
    elif len(queue) > 0:
        short_queue_val = ", ".join([f"`{track["title"]}`" for track in queue[:len(queue)]])
    else:
        short_queue_val = "[ `Empty` ]"

    embed.add_field(name="Title", value=f"[ `{info.get('title')}` ]", inline=True)
    embed.add_field(name="Author", value=f"[ `{info.get('uploader')}` ]", inline=True)
    embed.add_field(name="Upload date", value=f"[ `{info.get('upload_date')}` ]", inline=False)
    embed.add_field(name="Duration", value=f"[ `{info.get('duration')}` ]", inline=True)
    embed.add_field(name="Elapsed time", value=f"[ `{elapsed_time}` ]", inline=True)
    if looping:
        embed.add_field(name="Next track", value=f"[ `{track_to_loop.get('title')} (looping)` ]", inline=False)
    elif random:
        embed.add_field(name="Next track", value="[ `Random` ]", inline=False)
    else:
        embed.add_field(
            name="Next track",
            value=f"[ `Unable to read next track` ]" if is_modifying_queue else\
            f"[ `{queue[0]['title']}` ]" if len(queue) > 0 else\
            f"[ `{queue_to_loop[0]['title']}` ]" if queue_to_loop else\
            "[ `None` ]",
            inline=False
        )
    embed.add_field(name="Short queue", value=short_queue_val if len(short_queue_val) <= 1024 else short_queue_val[:1021] + "...", inline=False)
    embed.add_field(name="Extra options:", value="", inline=False)
    embed.add_field(name="Loop", value="[ `Enabled` ]" if looping else "[ `Disabled` ]", inline=True)
    embed.add_field(name="Randomization", value="[ `Enabled` ]" if random else "[ `Disabled` ]", inline=True)
    embed.add_field(name="Queue loop", value="[ `Enabled` ]" if queueloop else "[ `Disabled` ]", inline=True)
    embed.add_field(name="Source", value=f"[ `{info.get('source_website')}` ]", inline=False)
    embed.add_field(name="Thumbnail", value="", inline=False)
    embed.set_image(url=info.get("thumbnail", None))
    embed.set_footer(text=f"Total tracks in queue: {len(queue)}")

    return embed

def generate_yoink_embed(info: dict) -> discord.Embed:
    embed = discord.Embed(
        title="Track info",
        colour=discord.Colour.random(seed=randint(1, 1000)),
        timestamp=datetime.now()
    )

    embed.add_field(name="Title", value=f"[ `{info['title']}` ]", inline=True)
    embed.add_field(name="Author", value=f"[ `{info.get("uploader", "Unknown")}` ]", inline=True)
    embed.add_field(name="Upload date", value=f"[ `{info['upload_date']}` ] ", inline=False)
    embed.add_field(name="Duration", value=f"[ `{info['duration']}` ]", inline=True)
    embed.add_field(name="Webpage", value=f"[ `{info.get("webpage_url", "Unknown")}` ]", inline=False)
    embed.add_field(name="Source", value=f"[ `{info['source_website']}` ]", inline=True)
    embed.add_field(name="Thumbnail", value="", inline=False)
    embed.set_image(url=info.get("thumbnail", None))

    return embed

def generate_extraction_embed(current_query: str, max_queries: int, current_query_amount: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"Extraction progress",
        color=discord.Colour.random(seed=randint(1,1000)),
        timestamp=datetime.now()
    )

    embed.add_field(name="Currently extracting", value=f"`'{current_query}'`", inline=False)
    embed.add_field(name=f"Extracted **{current_query_amount}** out of **{max_queries}** queries.", value="", inline=False)

    return embed

def generate_queue_embed(queue: list[dict], page: int, page_length: int, is_history: bool=False, is_playlist: bool=False) -> discord.Embed:
    embed = discord.Embed(
        title=f"{'Playlist' if is_playlist else 'Queue' if not is_history else 'History'} - Page {page + 1} {'(End)' if page == page_length - 1 else ''}",
        color=discord.Colour.random(seed=randint(1,1000)),
        timestamp=datetime.now()
    )
    
    for track in queue:
        embed.add_field(name=f"[ `{track.get("title", "Unknown")}` ]",
                        value=f"Author: [ `{track.get('uploader', 'Unknown')}` ], Duration: [ `{track['duration']}` ], Source: [ `{track['source_website']}` ]",
                        inline=False
        )
    embed.set_footer(text=f"Total tracks in page: {len(queue)}")

    return embed
