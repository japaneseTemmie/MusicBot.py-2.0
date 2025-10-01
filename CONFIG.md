Here's the documentation for each key and its function in the `config.json` file.

# General settings
- yt_dlp_options: Options passed to the `YouTubeDL` object in `extractor.py/fetch()`. Expects a hashmap.
- command_prefix: Command prefix used for classic commands (there are none at the moment). Expects a string.
- enable_activity: Allow displaying configured custom activity. Expects a boolean.
- activity_name: The name of the activity. Appears after the type. Expects a string.
- activity_type: The activity type. Can be `playing`, `watching` or `listening`. Expects a string.
- default_status: The bot status. Can be `online`, `idle`, `do_not_disturb`, `invisible` or `null` for a random status. Expects a string or null.
- enable_file_backups: Enables in-RAM backup of guild files `playlists.json` and `roles.json`
  in case of a bad write. Requires double the memory needed to open the file for each call. Expects a boolean.
- enable_logging: Enables logging of `discord.py` errors/debug messages/warnings depending on the selected `log_level`. Expects a boolean.
- log_level: Level of log verbosity. Expects a string.
  - `normal`: Log basic info.
  - `verbose`: Log everything.
  - `warning`: Log warnings.
  - `errors`: Log errors.
  - `critical`: Log critical errors.
- use_sharding: Enables sharding. Required by Discord for bots that are in >= 2500 guilds. Expects a boolean.

# Module settings
These settings allow to control which module gets enabled, useful to limit features
and reduce memory usage if unused.

- enable_ModerationCog: Enables users to run commands from the `moderation` module. Expects a boolean.
- enable_RoleManagerCog: Enables users to run commands from the `rolemanager` module. Expects a boolean.
- enable_UtilsCog: Enables users to run commands from the `utils` module. Contains important UX commands like **/help**. It is highly discouraged to disable this. Expects a boolean.
- enable_MusicCog: Enables users to run commands from the `music` module. Expects a boolean.
- enable_VoiceCog: Enables users to run commands from the `voice` module. Expects a boolean.
- enable_PlaylistCog: Enables users to run commands from the `playlist` module. Expects a boolean.