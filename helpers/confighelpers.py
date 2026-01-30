""" Config helpers for discord.py bot """

from typing import Any, Type, Literal
from enum import Enum

ConfigCategoryValue = Literal[
    "yt_dlp_options",
    "other",
    "limits",
    "activity",
    "modules"
]

class ConfigCategory(Enum):
    YT_DLP = "yt_dlp_options"
    OTHER = "other"
    LIMITS = "limits"
    ACTIVITY = "activity"
    MODULES = "modules"

def correct_type(value: Any, expected: Type, default: Any) -> Any:
    """ Correct a config value type. 

    Return corrected value. """

    if isinstance(value, expected):
        return value
    
    return default

def correct_value_in(value: Any, allowed: tuple[Any, ...], default: Any) -> Any:
    """ Correct a config value given an 'allowlist' 
    
    Return corrected value. """

    if value in allowed:
        return value
    
    return default

def get_config_value(config: dict[str, Any], name: str, category: ConfigCategoryValue | None=None) -> Any:
    """ Get a config value given name and category. 
    
    If category is not given, return matching category. """

    location = config.get(category, {}) if category is not None else config
    return location.get(name)
     
# Defaults
def get_default_yt_dlp_config_data() -> dict[str, Any]:
    return {
        ConfigCategory.YT_DLP.value: {
            "quiet": True,
            "no_playlist": True,
            "format": "bestaudio[ext=m4a]/bestaudio",
            "no_warnings": True,
            "getcomments": False,
            "writeautomaticsub": False,
            "writesubtitles": False,
            "listsubtitles": False
        }
    }

def get_other_default_config_data() -> dict[str, Any]:
    return {
        ConfigCategory.OTHER.value: {
            "command_prefix": "?",
            "enable_file_backups": True,
            "enable_logging": True,
            "log_level": "normal",
            "use_sharding": False,
            "auto_delete_unused_guild_data": True
        }
    }

def get_default_limits_config_data() -> dict[str, int]:
    return {
        ConfigCategory.LIMITS.value: {
            "max_queue_track_limit": 100,
            "max_track_history_limit": 200,
            "max_query_limit": 25,
            "max_playlist_limit": 10,
            "max_playlist_track_limit": 100,
            "max_name_length": 50
        }
    }

def get_default_activity_config_data() -> dict[str, Any]:
    return {
        ConfigCategory.ACTIVITY.value: {
            "enable_activity": False,
            "activity_name": "with the API",
            "activity_type": "playing",
            "activity_state": "In Discord",
            "status_type": None
        }
    }

def get_default_modules_config_data() -> dict[str, bool]:
    return {
        ConfigCategory.MODULES.value: {
            "enable_ModerationCog": True,
            "enable_RolesCog": True,
            "enable_UtilsCog": True,
            "enable_MusicCog": True,
            "enable_PlaylistCog": True,
            "enable_VoiceCog": True,
            "enable_CatgirlDownloader": False,
            "enable_MyCog": False
        }
    }

def get_default_config_data() -> dict[str, Any]:
    config = {}

    config.update(get_default_yt_dlp_config_data())
    config.update(get_other_default_config_data())
    config.update(get_default_limits_config_data())
    config.update(get_default_activity_config_data())
    config.update(get_default_modules_config_data())

    return config
