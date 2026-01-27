Here's the documentation for each key and its function in the `config.json` file.

# General settings
These settings allow for configuration of general bot behaviour.

- `yt_dlp_options`: Options passed to the `YouTubeDL` object in `webextractor.py/fetch()`. Expects a hashmap.
- `command_prefix`: Prefix used for **classic** prefix-based commands. Expects a string.
- `enable_activity`: Allow displaying configured **custom activity**. Expects a boolean.
- `activity_name`: The **name** of the activity. Appears after the type. Expects a string.
- `activity_type`: The activity type. Can be `playing`, `watching` or `listening`. Expects a string.
- `activity_state`: The activity state. For `playing` and `listening` activity types only. Appears under the name.
- `status_type`: The bot status. Can be `online`, `idle`, `do_not_disturb`, `invisible` or `null` for a random status. Expects a string or null.
- `enable_file_backups`: Allows for in-RAM backup of `playlists.json` and `roles.json` guild files in case of a bad write. 
  Requires double the memory needed to open the file for each call. Expects a boolean.
- `enable_logging`: Enables logging of `discord.py` errors/debug messages/warnings depending on the selected `log_level`. Expects a boolean.
- `log_level`: Level of log verbosity. Expects a string.
  - `normal`: Log basic info.
  - `verbose`: Log everything.
  - `warning`: Log warnings.
  - `errors`: Log errors.
  - `critical`: Log critical errors.
- `use_sharding`: Enables sharding. _Required_ by Discord for bots that are in >= 2500 guilds. Expects a boolean.
- `auto_delete_unused_guild_data`: Allows the bot to auto-delete guild data from the `guild_data` folder in the root directory of the project that is no longer associated with a guild. Expects a boolean.
- `max_queue_track_limit`: The maximum **queue** track limit allowed. Expects an integer.
- `max_history_track_limit`: The maximum **history** track limit allowed. Expects an integer.
- `max_query_limit`: The maximum amount of queries for some command arguments. Expects an integer.
- `max_playlist_limit`: The maximum amount of playlists allowed in a guild. Expects an integer.
- `max_playlist_track_limit`: The maximum amount of tracks in a playlist allowed. This should preferably be the same as `max_queue_track_limit`. Expects an integer.
- `max_playlist_name_length`: The maximum amount of characters allowed for each playlist/playlist track. Expects an integer.

# Module settings
These settings allow to control which module gets enabled, useful to limit features
and reduce memory usage if unused.

- `enable_ModerationCog`: Enables users to run commands from the `moderation` module. Expects a boolean.
- `enable_RolesCog`: Enables users to run commands from the `roles` module. Expects a boolean.
- `enable_UtilsCog`: Enables users to run commands from the `utils` module. Contains important UX commands like **/help**. It is highly discouraged to disable this. Expects a boolean.
- `enable_MusicCog`: Enables users to run commands from the `music` module. Expects a boolean.
- `enable_VoiceCog`: Enables users to run commands from the `voice` module. Expects a boolean.
- `enable_PlaylistCog`: Enables users to run commands from the `playlist` module. Expects a boolean.
- `enable_CatgirlDownloader`: Enables users to run commands from the `catgirl` module. Expects a boolean.
- `enable_MyCog`: Enables users to run commands from the `example` module. Expects a boolean. (NOTE: This is never supposed to be enabled at all. Only used for module creation demonstration purposes)