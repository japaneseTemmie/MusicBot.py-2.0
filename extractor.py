""" Extractor module for discord.py bot.\n
Supported websites:\n
- YouTube (Both video and playlists)\n
- Newgrounds\n
- SoundCloud """

from settings import *

# List of regex pattern to match website URLs
# Second item is the 'source_website'
# Remember to update parse_info() after any changes made here.
PATTERNS = [
    (re.compile(r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/(?:playlist\?list=|watch\?.*?&list=)([a-zA-Z0-9_-]+)"), "YouTube Playlist"),
    (re.compile(r"(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|playlist\?list=|embed\/|v\/|shorts\/)?([^&=%\?]{11})"), "YouTube"),
    (re.compile(r"(https:\/\/)?(www\.)?newgrounds\.com/audio/listen/[0-9]+\/?"), "Newgrounds"),
    (re.compile(r"(https:\/\/)?(www\.)?soundcloud\.com/[^\/]+\/[^\/]+"), "SoundCloud"),
    (re.compile(r"(https:\/\/)?(www\.)?([a-z0-9\-]+)\.bandcamp\.com\/track\/[a-z0-9\-]+(\/)?"), "Bandcamp")
]

def format_seconds(seconds: int) -> str:
    """ This module has its own format_seconds() to fix a circular import issue. """

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

@lru_cache(maxsize=16384)
def get_query_type(query: str) -> tuple[re.Pattern | str, str]:
    """ Match a pattern, so we know what kind of query we're working with. """
    
    for pattern in PATTERNS:
        if pattern[0].match(query):
            return pattern
    return ("std_query", "YouTube")

def prettify_info(info: dict, source_website: str | None=None) -> dict:
    upload_date = info.get("upload_date", "19700101")
    duration = info.get("duration", 0)

    pretty_date = datetime.strptime(upload_date, "%Y%m%d").date()
    formatted_duration = format_seconds(int(duration))

    info["upload_date"] = pretty_date
    info["duration"] = formatted_duration
    info["source_website"] = "Unknown" if source_website is None else source_website

    return info

def parse_info(info: dict, query_type: tuple[re.Pattern | str, str]) -> dict | list[dict]:
    """ Parse extracted query in a readable/playable format for the VoiceClient. """
    
    if query_type[1] in ("Newgrounds", "SoundCloud", "Bandcamp"):
        info = prettify_info(info, query_type[1])

    elif query_type[1] in ("YouTube", "YouTube Playlist"):
        if info and "entries" in info:
            if len(info["entries"]) == 0:
                return None
            
            if query_type[1] == "YouTube Playlist":
                for i, entry in enumerate(info["entries"]):
                    info["entries"][i] = prettify_info(entry, query_type[1])
                
                return info["entries"]

            info = prettify_info(info["entries"][0], query_type[1])
        else:
            info = prettify_info(info, query_type[1])

    return info

@lru_cache(maxsize=16384)
def fetch(query: str, query_type: tuple[re.Pattern | str, str]) -> dict | None:
    """ Search a webpage and find info about the query.\n
    Must be sent to a thread. """
    
    with YoutubeDL(YDL_OPTIONS) as yt:
        try:
            if query_type[0] != "std_query":
                info = yt.extract_info(query, download=False)
            else:
                info = yt.extract_info(f"ytsearch:{query}", download=False)
        except Exception as e:
            if CAN_LOG and LOGGER is not None:
                LOGGER.exception(e)

            return None

        if info is not None:
            info = parse_info(info, query_type)
            return info
        
        return None