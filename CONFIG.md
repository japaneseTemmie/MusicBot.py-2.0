Here's the documentation for each key and its function in the `config.json` file.

# General settings
- yt_dlp_options: Options passed to the `YouTubeDL` object in extractor.py/fetch().
- command_prefix: Command prefix used for classic commands.
- enable_activity: Display custom activity.
- activity_name: The name of the activity. Appears after the type.
- activity_type: The activity type. Can be `playing`, `watching` or `listening`.
- default_status: The bot status. Can be `online`, `idle`, `do_not_disturb`, `invisible` or `null` for a random status.
- enable_file_backups: Enables in-RAM backup of guild files `playlists.json` and `roles.json`
  in case of a bad write. Requires double the memory needed to open the file for each call.
- enable_logging: Enables logging of `discord`.py errors/debug messages/warnings depending on the selected `log_level`.
- log_level: Level of log verbosity. Can be:
    - `normal`: Info about some bot actions.
    - `verbose`: Log everything.
    - `warning`: Logs warnings.
    - `errors`: Logs errors.
    - `critical`: Logs critical errors.
- use_sharding: Enables sharding. Required by Discord for bots that are in >= 2500 guilds.

# Module settings
These settings allow to control which module gets enabled, useful to limit features
and reduce memory usage if unused.

- enable_ModerationCog: Enables users to run commands from the `moderation` module.
- enable_RoleManagerCog: Enables users to run commands from the `rolemanager` module.
- enable_UtilsCog: Enables users to run commands from the `utils` module. Contains important UX commands like **/help**. It is highly discouraged to disable this.
- enable_MusicCog: Enables users to run commands from the `music` module.