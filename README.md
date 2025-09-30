# MusicBot.py 2.0
An improved version of **MusicBot.py**, a multipurpose Discord bot. Now with **Application commands**, **multi-guild**, **multi-website** support and
an **extended** moderation module alongside other new features!

## Table of contents
- [Key features](#key-features)
- [Quick start guide](#quick-start-guide)
- [Full Setup Guide](#full-bot-setup-guide)
- [Create a Discord Application](#create-a-discord-application)
- [Set up a Bot](#set-up-a-bot)
- [Code setup](#code-setup)
- [Requirements](#requirements)
- [Preparing the project directory](#preparing-the-project-directory)
- [Automatic setup](#automatic-setup)
- [Manual setup](#manual-setup)
- [Usage](#usage)
- [Extra configuration](#extra-configuration-for-hosts)
- [Extending the Bot](#extending-the-bot-for-devs)
- [Troubleshooting](#troubleshooting)
- [Licensing](#licensing)

# Key features
- Full application commands support for a more user-friendly interface.
- Multi-guild support.
- Improved playlist capabilities, with multi-playlist support and full control over them.
- Improved help command, with command-specific entries.
- Enhanced role-based command access system.
- Enhanced command functionality, with 40+ music commands and 15+ moderation commands.
- Multi-website support, with **YouTube** (search, video or playlist*), **Newgrounds**, **SoundCloud** (URL or search) and **Bandcamp**.
- Guild and voice channel auto-cleanup functionality.
- Sharding support.
- Extendable with custom modules.
- Easily self-hostable.

_*Playlist support may depend on command._

# Quick start guide
- Go through the [full guide](#full-bot-setup-guide) if you're inexperienced with setting up Discord bots.
  
  Otherwise, here are the core commands for basic setup on UNIX-like systems with `git`:

  ```bash
  git clone https://github.com/japaneseTemmie/MusicBot.py-2.0
  cd MusicBot.py-2.0
  echo "TOKEN=your_bot_token" > .env
  python3 start.py
  ```

# Full Bot Setup Guide
- If you already have a bot, this section can be skipped. Ensure the needed permissions and intents are enabled and visit [Troubleshooting](#troubleshooting) section if your bot is in more than 2500 guilds.

## Create a Discord Application
- Visit the [Discord Developer Portal](https://discord.com/developers/applications), log in, and create a new app. You may customize it if you wish.

## Set up a Bot
- Navigate to the `Bot` section.
  
  (Optional) Modify the name, avatar and banner to your liking.
- Scroll down to `Privileged Gateway Intents` and enable everything. Save the changes.
- Scroll up to `Token` and click on `Reset Token` to get your bot a new token, then copy it to your clipboard and paste it in a file for later use.
  
  Make sure to **not share it with _anyone_**. Treat it like a _password_.
- Go to the `Installation` Section, uncheck `User install` in the `Installation Contexts` box.
- In the `Default install settings` box, include `bot` in the `Scopes` entry and add the following permissions in the `Permissions` entry:

  | Permission Category |                Permissions                  |
  |---------------------|---------------------------------------------|
  | Server Management   | Manage Server, Manage Roles, Manage Channels, Manage Threads and Manage Messages |
  | Moderation          | Kick Members, Ban Members and Moderate Members |
  | Messaging           | Send Messages, Send Messages in Threads and Read Message History |
  | Voice               | Connect, Speak, Move Members, Mute Members |
  | Other               | Embed Links, Mention Everyone |

- Save the changes. Copy the link provided in the `Install link` box.
  Open it in a browser window and add your bot to your server.

# Code setup

## Requirements
- UNIX-like/Windows OS. Code should work cross-platform, but works best on Linux (BSD/macOS not tested, but likely to work).
- Make sure `Python 3.10+` and `FFmpeg` are installed on your system.
  
  If you're on a GNU/Linux distribution, they may already be installed.
  
  If not, make sure to install them from your distribution's repositories:

  `sudo apt install python3 ffmpeg` (Debian, Debian-based distro (Ubuntu, Linux Mint, ZorinOS))
  
  `sudo dnf install python3 ffmpeg` (Fedora, Fedora-based distro (Bazzite, Nobara))
  
  `sudo pacman -S python3 ffmpeg` (Arch, Arch-based distro (CachyOS, Manjaro))

  ... or compile them from source.

  For Windows/macOS, you can official download links:

  [FFmpeg for macOS/Windows](https://ffmpeg.org/download.html)

  [Python for Windows](https://www.python.org/downloads/windows/) | [Python for macOS](https://www.python.org/downloads/macos/)

- Test `Python` and `FFmpeg`

  - Python:

    `python3 -V` (UNIX-like)
  
    `python -V` (Windows)

    Expected output: `Python {VERSION}`

  - FFmpeg:

    `ffmpeg -version` (UNIX-like/Windows)

      Expected output: `ffmpeg version {VERSION}...`

  Project was tested on  `Python 3.12.3` and `FFmpeg 6.1`.

  Up to date versions should work fine.

- Optional, but preferred if hosting on many guilds:

  - An internet connection with **high download/upload speeds**.
  
      Minimum `100mbps DL`/`10mbps UL` for personal use, `1Gbps+ DL`/`~500mbps+ UL` for a moderate amount of guilds

  - A system with lots of RAM (>= 32GB).

      The bot caches role and playlist files extensively for faster lookup and lower disk activity at the expense of using more RAM.

  - A system with a powerful CPU (8+ performance cores).

      A powerful CPU is required for tasks like `yt-dlp` extraction and parsing, `FFmpeg` and `Discord` audio processing.

## Preparing the project directory
- Unpack the source code to a directory of your choice. (Or, `git clone` it.)
- Open a terminal in that directory.

  On Windows:

  `CMD` is necessary. `PowerShell` will break almost every command in this guide.

  On UNIX-like OS:

  `Bash`/`Zsh` is preferred. `Fish` might break some commands.

- Create a `.env` file with the following contents by running:

  `echo "TOKEN={your_discord_bot_token}" > .env` (UNIX-like)

  `echo TOKEN={your_discord_bot_token} > .env` (Windows)

- Replace `{your_discord_bot_token}` with your bot's token.

  Example file output:
  
  ```dotenv
  TOKEN=1a2b3c4d5e6f7g
  ```

# Automatic setup
- Prepare and run automatically using the helper script:

  `python3 start.py` (UNIX-like)
  
  `python start.py` (Windows)

  What it does:

  Automatically determines if a Python _venv_ is installed, creates one if not, installs dependencies and runs the main script.

  - Once it outputs '`Ready`', it will start listening for events and commands.

# Manual setup
If the automatic setup doesn't work, it may be worth manually setting it up:

- Create a Python virtual environment (_venv_):

  `python3 -m venv ./.venv/` (UNIX-like)

  `python -m venv .\.venv\` (Windows)

  What it does:

  Invokes the Python interpreter with the _venv_ module, passing the current path as the installation directory.

- If successful, activate the venv:

  `source ./.venv/bin/activate` (UNIX-like)

  `.\.venv\Scripts\activate.bat` (Windows)

  What it does:

  Runs the activation script for the _venv_.

- Install the required dependencies for the project:

  `pip install -r requirements.txt` (UNIX-like/Windows)

  What it does:

  Runs the pip package manager, passing the contents of 'requirements.txt' as the packages to install.

- Finally, if successful, run the main entry point:

  `python3 main.py` (UNIX-like)

  `python main.py` (Windows)

  What it does:

  Invokes the Python interpreter with the main.py file.

  - Once it outputs '`Ready`', it will start listening for events and commands.

# Usage
To start listening to your favourite music:
- Join a voice channel.
- Use the **/join** command to invite the bot to join your voice channel.
- Use **/add** or **/playnow** to add/play your tracks!

Help for every command can be found using the **/help** command.

# Extra Configuration (For experienced hosts)
The bot allows configuring a custom activity.

During the first run, the bot will create a `config.json` file in its own directory. It contains configuration data, including activity.

You can modify the `enable_activity`, `activity_name`, `activity_type` and `default_status` values to set your own custom activity.

Documentation for every key can be found [here](./CONFIG.md). Modify values at your own risk.

Notes
- Changing any value will require a restart to take effect. See [Troubleshooting](#troubleshooting) to see how to properly restart.
- Most config keys are automatically recreated at startup if missing.

Example activity config:

```json
{
  "enable_activity": true,
  "activity_name": "Amazing music",
  "activity_type": "listening",
  "default_status": "online"
}
```

# Extending the bot (For devs)
To add your own modules, simply create a new **.py** file in the `modules` directory.

Write your class as a `commands.Cog` subclass, which takes _only_ a `client` parameter of type `Bot` (from module `bot`) in its
constructor, this allows custom classes to interact with the Bot subclass of `commands.Bot` or `commands.AutoShardedBot`.

Best practices:
- Check out the [example module](./modules/custom_example.py) and follow the [discord.py documentation](https://discordpy.readthedocs.io/en/stable/api.html) for help with the Discord API.
- Check locks before running I/O file or VoiceClient operations (channel.join()/vc.play()/vc.stop()/vc.pause() etc.). These locks are `FILE_OPERATIONS_LOCKED` and `VOICE_OPERATIONS_LOCKED` (from `settings`).
- Do _not_ do file I/O directly, instead, send the `write_file()` or `open_file()` function (from `iohelpers`) to an asyncio thread and await its result. Or, write your own _async_ I/O functions.
- Do _not_ call `sleep()` or anything that blocks the event loop. Use `asyncio.sleep()` instead.
- Keep helper functions in `helpers.py`. If it grows too big, move your custom functions to a new module.
- Avoid interacting with core modules, as they were not written with an API-like system in mind.
- To log errors or messages to stdout, use `log()`. Instead, to log to the `discord.log` file (if logging is explicitly enabled), use `log_to_discord_log()` (from `init.logutils`). 
- Do _not_ use the `TOKEN` constant anywhere unless there's a good reason to. (like running the bot itself)
- If custom Cogs need other non-default permissions, make sure to enable them in [your application's Installation section](https://discord.com/developers/applications)

Then, add a new key in `config.json` named `enable_{class_name}` to allow enabling/disabling the module, and set its value to `true`, or else the bot won't load your Cog.

Start the bot. It will attempt to auto-discover your module and load the appropriate class(es).

Note: The bot will load any class that inherits from `commands.Cog`, independently of the name, adding 'Cog' at the end of your class name keeps it consistent with the default modules.

# Troubleshooting
- If the bot state ends up broken, restarting might help.

  To restart the bot:
  
  - **Gracefully** terminate the process with **CTRL + C**, this is the preferred way and allows the bot to properly clean up before exiting.
  - Then, run:
  
    `python3 start.py` (UNIX-like)
  
    `python start.py` (Windows)
  
    if the current terminal is **_not_** in the _venv_. Otherwise:
    
    `python3 main.py` (UNIX-like)

    `python main.py` (Windows) 
  
    Note: The script `start.py` can be used to launch the bot even after first time configuration.

- If the bot fails to play tracks, ensure the libraries (specifically, `yt_dlp`) are up to date.

  Open a terminal in the project directory and run:
  
  `./.venv/bin/pip install --upgrade -r requirements.txt` (UNIX-like)
  
  `.\.venv\Scripts\pip.exe install --upgrade -r requirements.txt` (Windows)

  if the current terminal is **_not_** in the _venv_. Otherwise:

  `pip install --upgrade -r requirements.txt` (UNIX-like/Windows)
  
  Then, try again.

- If you have an existing bot that's in over 2500 guilds, ensure the `use_sharding` key is set to `true` in `config.json`

  'Sharding' allows multiple instances of this bot to manage multiple guilds and is required by Discord after a bot reaches 2500 guilds.

# Licensing
This project is licensed under MIT. See [LICENSE](./LICENSE) for more information.