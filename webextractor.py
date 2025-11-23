""" Extractor module for discord.py bot.

Supported websites

- YouTube (Both video and playlists)
- Newgrounds
- SoundCloud (Songs and sets)
- Bandcamp (Songs and albums) """

from settings import YDL_OPTIONS, CAN_LOG, LOGGER, EXTRACTOR_CACHE
from init.logutils import log_to_discord_log
from helpers.timehelpers import format_to_minutes
from helpers.cachehelpers import get_cache, store_cache
from error import Error

import re
from enum import Enum
from datetime import datetime
from yt_dlp import YoutubeDL
from typing import Any

class SourceWebsite(Enum):
    YOUTUBE_PLAYLIST = "YouTube Playlist"
    YOUTUBE = "YouTube"
    NEWGROUNDS = "Newgrounds"
    SOUNDCLOUD_PLAYLIST = "SoundCloud Playlist"
    SOUNDCLOUD = "SoundCloud"
    BANDCAMP_PLAYLIST = "Bandcamp Album"
    BANDCAMP = "Bandcamp"
    YOUTUBE_SEARCH = "YouTube search"
    SOUNDCLOUD_SEARCH = "SoundCloud search"

class QueryType:
    def __init__(self, query: str, source_website: str, is_url: bool, regex: re.Pattern | None=None, search_string: str | None=None):
        self.query = query
        self.source_website = source_website
        self.is_url = is_url
        self.regex = regex
        self.search_string = search_string

# List of regex pattern to match website URLs
# Second item is the 'source_website' string
# Remember to update parse_info() after any changes made here.
INVALID_URL_PATTERN = re.compile(r"^(((http|https|ftp):\/\/)?(www\.)?[a-zA-Z0-9-_\.]+\.[a-zA-Z]{2,}(\/?[^\s]+)?)$")
URL_PATTERNS = [
    (re.compile(r"(https:\/\/)?(www\.)?youtube\.com\/playlist\?list=[a-zA-Z0-9_-]+(\/)?"), SourceWebsite.YOUTUBE_PLAYLIST.value),
    (re.compile(r"(https:\/\/)?(www\.)?youtube\.com\/watch\?v=[a-zA-Z0-9_-]{11}(&list=[a-zA-Z0-9_-]+)?(&index=[0-9])?(\/)?"), SourceWebsite.YOUTUBE.value),
    (re.compile(r"(https:\/\/)?(www\.)?newgrounds\.com/audio/listen/[0-9]+(\/)?"), SourceWebsite.NEWGROUNDS.value),
    (re.compile(r"(https:\/\/)?(www\.)?soundcloud\.com\/[a-zA-Z0-9_-]+\/sets\/[a-zA-Z0-9_-]+(\/)?"), SourceWebsite.SOUNDCLOUD_PLAYLIST.value),
    (re.compile(r"(https:\/\/)?(www\.)?soundcloud\.com/[^\/]+\/[^\/]+(\/)?"), SourceWebsite.SOUNDCLOUD.value),
    (re.compile(r"(https:\/\/)?(www\.)?([a-z0-9\-]+)\.bandcamp\.com\/album\/[a-z0-9\-]+(\/)?"), SourceWebsite.BANDCAMP_PLAYLIST.value),
    (re.compile(r"(https:\/\/)?(www\.)?([a-z0-9\-]+)\.bandcamp\.com\/track\/[a-z0-9\-]+(\/)?"), SourceWebsite.BANDCAMP.value)
]
# Hashmap of search providers
# Key is the provider and the value is a tuple with yt-dlp search string [0] and 'source_website' string [1]
SEARCH_PROVIDERS = {
    "soundcloud": ("scsearch:", SourceWebsite.SOUNDCLOUD_SEARCH.value),
    "youtube": ("ytsearch:", SourceWebsite.YOUTUBE_SEARCH.value)
}

PLAYLIST_WEBSITES = (SourceWebsite.YOUTUBE_PLAYLIST.value, SourceWebsite.SOUNDCLOUD_PLAYLIST.value, SourceWebsite.BANDCAMP_PLAYLIST.value)
SEARCH_WEBSITES = (SourceWebsite.YOUTUBE_SEARCH.value, SourceWebsite.SOUNDCLOUD_SEARCH.value)

BANDCAMP_DOMAINS = (SourceWebsite.BANDCAMP.value, SourceWebsite.BANDCAMP_PLAYLIST.value)
SOUNDCLOUD_DOMAINS = (SourceWebsite.SOUNDCLOUD.value, SourceWebsite.SOUNDCLOUD_PLAYLIST.value, SourceWebsite.SOUNDCLOUD_SEARCH.value)
YOUTUBE_DOMAINS = (SourceWebsite.YOUTUBE.value, SourceWebsite.YOUTUBE_PLAYLIST.value, SourceWebsite.YOUTUBE_SEARCH.value)

def get_query_type(query: str, provider: str | None) -> QueryType:
    """ Match a regex pattern to a user-given query, so we know what kind of query we're working with. 
    
    Returns a QueryType object. """

    # Match URLs first.
    for regex, source_website in URL_PATTERNS:
        if regex.match(query):
            return QueryType(query, source_website, True, regex)

    # If no matches are found, match a search query. If not found, default to youtube.
    provider_info = SEARCH_PROVIDERS.get(provider, SEARCH_PROVIDERS["youtube"])
    provider_search_string = provider_info[0]
    provider_source_website = provider_info[1]

    return QueryType(query, provider_source_website, False, None, provider_search_string)

def prettify_info(info: dict[str, Any], source_website: str | None=None) -> dict[str, Any]:
    """ Prettify the extracted info with cleaner values. """
    
    upload_date = info.get("upload_date", "19700101") # Default to UNIX epoch because why not
    duration = info.get("duration", 0)

    # Since different websites distribute content differently, we have to adapt to different date/duration formats
    if isinstance(upload_date, str):
        pretty_date = datetime.strptime(upload_date, "%Y%m%d").date()
    else:
        pretty_date = upload_date # Is already a datetime object
    if isinstance(duration, (int, float)):
        formatted_duration = format_to_minutes(int(duration))
    else:
        formatted_duration = duration # Is already a HH:MM:SS string

    info["upload_date"] = pretty_date
    info["duration"] = formatted_duration
    info["source_website"] = source_website or "Unknown"

    return info

def parse_info(info: dict[str, Any], query: str, query_type: QueryType) -> dict[str, Any] | list[dict[str, Any]] | Error:
    """ Parse extracted query in a readable/playable format for the VoiceClient. """

    # If it's a playlist, prettify each entry and return
    if query_type.source_website in PLAYLIST_WEBSITES and "entries" in info:
        return [prettify_info(entry, query_type.source_website) for entry in info["entries"]]

    # If it's a search, prettify the first entry and return
    if query_type.source_website in SEARCH_WEBSITES and "entries" in info:
        if len(info["entries"]) == 0:
            return Error(f"No results found for query `{query[:50]}`.")
        
        first_entry = info["entries"][0]
        
        return prettify_info(first_entry, query_type.source_website)
    
    # URLs are directly prettified.
    return prettify_info(info, query_type.source_website)

def fetch(query: str, query_type: QueryType) -> dict[str, Any] | list[dict[str, Any]] | Error:
    """ Search a webpage and find info about the query.

    Must be sent to a thread if working with an asyncio loop, as the web requests block the main thread. """

    if not query_type.is_url and INVALID_URL_PATTERN.match(query):
        return Error(f"Invalid URL-like query supplied: `{query[:50]}`.")
    
    cache = get_cache(EXTRACTOR_CACHE, query+f"::{query_type.source_website}")
    if cache is not None:
        return cache

    try:
        with YoutubeDL(YDL_OPTIONS) as ydl:
            if not query_type.is_url:
                info = ydl.extract_info(query_type.search_string + query, download=False)
            else:
                info = ydl.extract_info(query, download=False)
    except Exception as e:
        log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)

        return Error(f"An internal error occured while extracting `{query[:50]}`. Please try another source website.")

    if info is not None:
        pretty_info = parse_info(info, query, query_type)
        
        if not isinstance(pretty_info, Error):
            store_cache(pretty_info, query+f"::{query_type.source_website}", EXTRACTOR_CACHE)
        
        return pretty_info
    
    return Error(f"An error occured while extracting `{query[:50]}`.")