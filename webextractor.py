""" Extractor module for discord.py bot.

Supported websites

- YouTube (Both video and playlists)
- Newgrounds
- SoundCloud (Songs and sets)
- Bandcamp (Songs and albums) """

from settings import YDL_OPTIONS, CAN_LOG, LOGGER, EXTRACTOR_CACHE, MAX_ITEM_NAME_LENGTH
from init.logutils import log_to_discord_log
from helpers.timehelpers import format_to_minutes
from helpers.cachehelpers import get_cache, store_cache
from error import Error

import re
from enum import Enum
from datetime import datetime, date
from yt_dlp import YoutubeDL
from typing import Any, Literal

SourceWebsiteValue = Literal[
    "YouTube Playlist",
    "YouTube",
    "Newgrounds",
    "SoundCloud Playlist",
    "SoundCloud",
    "Bandcamp Album",
    "Bandcamp",
    "YouTube search",
    "SoundCloud search"
]

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

class SearchWebsiteID(Enum):
    SOUNDCLOUD_SEARCH = "soundcloud"
    YOUTUBE_SEARCH = "youtube"

class SearchString(Enum):
    SOUNDCLOUD_SEARCH = "scsearch:"
    YOUTUBE_SEARCH = "ytsearch:"

class QueryType:
    """ QueryType class.
    
    dataclass-like object to simplify query handling.
    
    `query`: User-given query. Must always exist. 
    
    `source_website`: Source website tied to `query`. Must be a `SourceWebsite` value and must always exist. 
    
    `is_url`: Whether `query` is a URL or not. Must always exist. 
    
    `regex`: Regex pattern used to match `query`. Must only be filled if `is_url`=`True`. Otherwise, ValueError will be raised. 
    
    `search_string`: Search string passed to yt-dlp. Must only be filled if `is_url`=`False`. Otherwise, ValueError will be raised. """

    def __init__(self, query: str, source_website: SourceWebsiteValue | None, is_url: bool, regex: re.Pattern | None=None, search_string: str | None=None):
        self.query = query
        self.source_website = source_website
        self.is_url = is_url

        if (regex is not None and not self.is_url) or (search_string is not None and self.is_url):
            raise ValueError("Unsupported argument supplied in current condition")

        self.regex = regex
        self.search_string = search_string

# List of regex pattern to match website URLs
# Second item is the 'source_website' string
# Remember to update parse_info() after any changes made here.
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
    SearchWebsiteID.SOUNDCLOUD_SEARCH.value: (SearchString.SOUNDCLOUD_SEARCH.value, SourceWebsite.SOUNDCLOUD_SEARCH.value),
    SearchWebsiteID.YOUTUBE_SEARCH.value: (SearchString.YOUTUBE_SEARCH.value, SourceWebsite.YOUTUBE_SEARCH.value)
}

PLAYLIST_WEBSITES = (SourceWebsite.YOUTUBE_PLAYLIST.value, SourceWebsite.SOUNDCLOUD_PLAYLIST.value, SourceWebsite.BANDCAMP_PLAYLIST.value)
SEARCH_WEBSITES = (SourceWebsite.YOUTUBE_SEARCH.value, SourceWebsite.SOUNDCLOUD_SEARCH.value)

BANDCAMP_DOMAINS = (SourceWebsite.BANDCAMP.value, SourceWebsite.BANDCAMP_PLAYLIST.value)
SOUNDCLOUD_DOMAINS = (SourceWebsite.SOUNDCLOUD.value, SourceWebsite.SOUNDCLOUD_PLAYLIST.value, SourceWebsite.SOUNDCLOUD_SEARCH.value)
YOUTUBE_DOMAINS = (SourceWebsite.YOUTUBE.value, SourceWebsite.YOUTUBE_PLAYLIST.value, SourceWebsite.YOUTUBE_SEARCH.value)

# To speed up seeking in large tracks (30+ minutes) we must put -ss before the -i flag in the ffmpeg command.
# However, some CDNs (especially ones that primarily serve HLS streams) do not like this and must be excluded from this list
# Currently, SoundCloud is the only source that crashes ffmpeg if -ss is before the -i flag
FAST_SEEK_SUPPORT_DOMAINS = (
    SourceWebsite.BANDCAMP.value,
    SourceWebsite.BANDCAMP_PLAYLIST.value,
    SourceWebsite.YOUTUBE.value,
    SourceWebsite.YOUTUBE_PLAYLIST.value,
    SourceWebsite.YOUTUBE_SEARCH.value,
    SourceWebsite.NEWGROUNDS.value
)

def get_query_type(query: str, provider: SourceWebsiteValue | None) -> QueryType:
    """ Match a regex pattern to a user-given query, so we know what kind of query we're working with. 

    `provider` is the optional search provider to use when queries don't match the supported regex patterns.
    
    Returns a QueryType object. """

    # Match URLs first.
    for regex, source_website in URL_PATTERNS:
        if regex.match(query):
            return QueryType(query, source_website, True, regex)

    # If no matches are found, match a search query. If not found, default to youtube.
    provider_info = SEARCH_PROVIDERS.get(provider, SEARCH_PROVIDERS[SearchWebsiteID.YOUTUBE_SEARCH.value])
    provider_search_string = provider_info[0]
    provider_source_website = provider_info[1]

    return QueryType(query, provider_source_website, False, None, provider_search_string)

def prettify_date(date: str) -> date | str:
    """ Parse given `date` into a date object when possible. Non-string `date` is assumed as a date object. """
    
    # Since different websites distribute content differently, we have to adapt to different date/duration formats
    if isinstance(date, str):
        try:
            pretty_date = datetime.strptime(date, "%Y%m%d").date()
        except ValueError:
            pretty_date = date
    else:
        pretty_date = date # Is already a datetime-like object

    return pretty_date

def prettify_duration(duration: str | float | int) -> str:
    """ Return an HH:MM:SS version of `duration` if it is a float or int. Otherwise return the same string. """

    if isinstance(duration, (int, float)):
        return format_to_minutes(int(duration)) or "00:00:00" # prefer 0 rather than None
    else:
        return duration

def prettify_info(info: dict[str, Any], source_website: SourceWebsiteValue | None=None) -> dict[str, Any]:
    """ Prettify the extracted info with cleaner values. """
    
    upload_date = info.get("upload_date", "19700101") # Default to UNIX epoch because why not
    duration = info.get("duration", 0)

    info["upload_date"] = prettify_date(upload_date)
    info["duration"] = prettify_duration(duration)
    info["uploader"] = info.get("uploader") or "Unknown" # Some newgrounds tracks fail to get uploader, better to display as 'unknown' than 'None'
    info["source_website"] = source_website or "Unknown"

    return info

def parse_info(info: dict[str, Any], query: str, query_type: QueryType) -> dict[str, Any] | list[dict[str, Any]] | Error:
    """ Parse extracted query in a readable/playable format for the VoiceClient. """

    # If it's a playlist, prettify each entry and return
    if query_type.source_website in PLAYLIST_WEBSITES and "entries" in info:
        if len(info["entries"]) == 0:
            return Error(f"No results found for query `{query[:MAX_ITEM_NAME_LENGTH]}`.")
        
        return [prettify_info(entry, query_type.source_website) for entry in info["entries"] if entry is not None]

    # If it's a search, prettify the first entry and return
    if query_type.source_website in SEARCH_WEBSITES and "entries" in info:
        if len(info["entries"]) == 0:
            return Error(f"No results found for query `{query[:MAX_ITEM_NAME_LENGTH]}`.")
        
        first_entry = info["entries"][0]
        
        return prettify_info(first_entry, query_type.source_website)
    
    # URLs are directly prettified.
    return prettify_info(info, query_type.source_website)

def fetch(query: str, query_type: QueryType, allow_cache: bool=True) -> dict[str, Any] | list[dict[str, Any]] | Error:
    """ Search a webpage and find info about the query.

    Must be sent to a thread if working with an asyncio loop, as the web requests block the main thread. 
    
    Return a single hashmap containing a media URL readable by FFmpeg and optional metadata or a list of the same type if `query` is a playlist URL. """
    
    if allow_cache:
        cache = get_cache(EXTRACTOR_CACHE, query + f"::{query_type.source_website}")
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

        return Error(f"An internal error occurred while extracting `{query[:MAX_ITEM_NAME_LENGTH]}`. Please try another source website.")

    if info is not None:
        prettified_info = parse_info(info, query, query_type)
        if not isinstance(prettified_info, Error):
            store_cache(prettified_info, query + f"::{query_type.source_website}", EXTRACTOR_CACHE)
        
        return prettified_info
    
    return Error(f"An error occurred while extracting `{query[:MAX_ITEM_NAME_LENGTH]}`.")