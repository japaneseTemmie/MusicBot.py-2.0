""" Extractor module for discord.py bot.\n
Supported websites:\n
- YouTube (Both video and playlists)\n
- Newgrounds\n
- SoundCloud\n
- Bandcamp """

from settings import *
from timehelpers import format_to_minutes
from error import Error

# List of regex pattern to match website URLs
# Second item is the 'source_website'
# Remember to update parse_info() after any changes made here.
URL_PATTERNS = [
    (re.compile(r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/(?:playlist\?list=|watch\?.*?&list=)([a-zA-Z0-9_-]+)"), "YouTube Playlist"),
    (re.compile(r"(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|playlist\?list=|embed\/|v\/|shorts\/)?([^&=%\?]{11})"), "YouTube"),
    (re.compile(r"(https:\/\/)?(www\.)?newgrounds\.com/audio/listen/[0-9]+\/?"), "Newgrounds"),
    (re.compile(r"(https:\/\/)?(www\.)?soundcloud\.com/[^\/]+\/[^\/]+"), "SoundCloud"),
    (re.compile(r"(https:\/\/)?(www\.)?([a-z0-9\-]+)\.bandcamp\.com\/track\/[a-z0-9\-]+(\/)?"), "Bandcamp")
]
# Hashmap of search providers
# Key is the provider and the value is a tuple with yt-dlp search string [0] and 'source_website' [1]
SEARCH_PROVIDERS = {
    "soundcloud": ("scsearch:", "SoundCloud search"),
    "youtube": ("ytsearch:", "YouTube search")
}

def get_query_type(query: str, provider: str | None) -> tuple[re.Pattern | str, str]:
    """ Match a regex pattern to a user-given query, so we know what kind of query we're working with. """

    # Match URLs first.
    for pattern in URL_PATTERNS:
        if pattern[0].match(query):
            return pattern

    # If no matches are found, match a search query. If not found, default to youtube.
    return SEARCH_PROVIDERS.get(provider, ("ytsearch:", "YouTube search"))

def prettify_info(info: dict, source_website: str | None=None) -> dict:
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
    info["source_website"] = "Unknown" if source_website is None else source_website

    return info

def parse_info(info: dict, query: str, query_type: tuple[re.Pattern | str, str]) -> dict | list[dict] | Error:
    """ Parse extracted query in a readable/playable format for the VoiceClient. """
    
    source_website = query_type[1]

    # If it's a playlist, prettify each entry and return
    if source_website == "YouTube Playlist" and "entries" in info:
        return [prettify_info(entry, source_website) for entry in info["entries"]]

    # If it's a search, prettify the first entry and return
    if source_website in ("YouTube search", "SoundCloud search") and "entries" in info:
        if len(info["entries"]) == 0:
            return Error(f"No results found for query `{query[:50]}`.")
        
        first_entry = info["entries"][0]
        
        return prettify_info(first_entry, source_website)
    
    # URLs are directly prettified.
    return prettify_info(info, source_website)

def fetch(query: str, query_type: tuple[re.Pattern | str, str]) -> dict | list[dict] | Error:
    """ Search a webpage and find info about the query.\n
    Must be sent to a thread. """
    
    try:
        with YoutubeDL(YDL_OPTIONS) as yt:
            search_string = query_type[0]
            if isinstance(search_string, str):
                info = yt.extract_info(search_string + query, download=False)
            else:
                info = yt.extract_info(query, download=False)
    except Exception as e:
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(e)

        return Error(f"An error occured while extracting `{query[:50]}`.")

    if info is not None:
        return parse_info(info, query, query_type)
    
    return Error(f"An error occured while extracting `{query[:50]}`.")