# MusicBot.py 2.0
An improved version of **MusicBot.py**, a multipurpose Discord bot, now with **Application commands**, **multi-guild**, **multi-website** support and
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

## Key features
- Full application commands support for a more user-friendly interface.
- Multi-guild support.
- Improved playlist capabilities, now with multi-playlist support.
- Improved help command.
- Enhanced role-based command access system.
- Enhanced command functionality.
- Multi-website support, with **YouTube** (video or playlist*), **Newgrounds**, **SoundCloud** and **Bandcamp**.
- 40+ music commands and 15+ moderation commands.
- Guild and voice channel auto-cleanup logic.
- Sharding support.
- Extendable with custom modules.
- Easily self-hostable.

_*Playlist support may depend on command._

# Quick start guide
- Go through the [full guide](#full-bot-setup-guide) if you're inexperienced with setting up Discord bots.
  
  Otherwise, here are the core commands for basic setup on UNIX-like systems with git:

```bash
git clone https://github.com/japaneseTemmie/MusicBot.py-2.0
cd MusicBot.py-2.0
echo "TOKEN=your_bot_token" > .env
python3 run.py
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
  | Server Management   | Manage Server, Manage Roles, Manage Channels |
  | Moderation          | Kick, Ban and Moderate Members |
  | Messaging           | View, Send, Manage Messages & Threads |
  | Voice               | Connect, Speak, Move and Mute Members, Set Voice Channel Status |
  | Other               | Embed Links, Mention Everyone |

- Save the changes. Copy the link provided in the `Install link` box.
  Open it in a browser window and add your bot to your server.

# Code setup

## Requirements
- UNIX-like/Windows OS. Code should work cross-platform, but works best on Linux (BSD/macOS not tested, but likely to work).
- Make sure `Python 3.10+` and `FFmpeg` are installed on your system.
  
  If you're on a GNU/Linux distribution, they may already be installed.
  
  If not, make sure to install them from your distribution's repositories or compile them from source.

  `sudo apt install python3 ffmpeg` (Debian, Debian-based distro (Ubuntu, Mint, ZorinOS))
  
  `sudo dnf install python3 ffmpeg` (Fedora, Fedora-based distro (Bazzite, Nobara))
  
  `sudo pacman -S python3 ffmpeg` (Arch, Arch-based distro (CachyOS, Manjaro))

  On Windows/macOS, you can find guides on how to install them:

  [FFmpeg for macOS/Windows](https://ffmpeg.org/download.html)

  [Python for Windows](https://www.python.org/downloads/windows/) | [Python for macOS](https://www.python.org/downloads/macos/)

  Test Python and FFmpeg:

  `python3 -V` (UNIX-like)
  
  `python -V` (Windows)

  Expected output: `Python {VERSION}`

  `ffmpeg -version` (UNIX-like/Windows)

  Expected output: `ffmpeg version {VERSION}...`

- Optional, but preferred if hosting on many guilds:

  - An internet connection with **high download/upload speeds**.
  
    (Minimum `100mbps DL`/`10mbps UL` for personal use, `1Gbps+ DL`/`~500mbps+ UL` for a moderate amount of guilds)

  - A system with lots of RAM (>= 32GB) for many guilds.

    The bot caches roles and playlists extensively for faster lookup and lower disk activity at the expense of using more RAM.

  - A system with a powerful CPU (8+ Cores) for many guilds.

    A powerful CPU is required for tasks like `yt-dlp` extraction, `FFmpeg` post-processing and `Discord` audio processing.

Project was tested on the following software: `Python 3.12.3`, `FFmpeg 6.1` and `Linux Mint 22.1`

More up to date versions should be able to work fine.

## Preparing the project directory
- Unpack the source code to a directory of your choice. (Or, `git clone` it.)
- Open a terminal in that directory.

  On Windows:

  `CMD` is necessary. `PowerShell` will break almost every command in this guide.

  On UNIX-like:

  `Bash`/`Zsh` is preferred. `Fish` might break some commands.

- Create a `.env` file with the following contents by running:

  `echo "TOKEN={your_discord_bot_token}" > .env` (UNIX-like)

  `echo TOKEN={your_discord_bot_token} > .env` (Windows)

- Replace `{your_discord_bot_token}` with your bot's token.

  Example file output:
  
  ```dotenv
  TOKEN=token_here
  ```

# Automatic setup
- Prepare and run automatically using the helper script:

  `python3 run.py` (UNIX-like)
  
  `python run.py` (Windows)

  What it does:
  Automatically determines if a Python _venv_ is installed, creates one if not, installs dependencies and runs the main script.

# Manual setup
If the automatic setup doesn't work, try manually setting it up:

- Create a Python virtual environment (venv):

  `python3 -m venv ./` (UNIX-like)

  `python -m venv .\` (Windows)

  What it does:
  Invokes the Python interpreter with the _venv_ module, passing the current path as the installation directory.

- If successful, activate the venv:

  `source ./bin/activate` (UNIX-like)

  `.\Scripts\activate.bat` (Windows)

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

- Once it outputs `Ready`, it will start listening for events and commands.

# Usage
To start listening to your favourite music:
- Join a voice channel.
- Use the **/join** command to invite the bot to join your voice channel.
- Use **/add** or **/playnow** to add your tracks!

Help for every command can be found using the **/help** command.

# Extra Configuration (For hosts)
The bot allows configuring a custom activity.

During the first run, the bot will create a `config.json` file in its own directory. It contains configuration data, including activity.

You can modify the `enable_activity`, `activity_name`, `activity_type` and `default_status` values to set your own custom activity.

Documentation for every key can be found at the top of the `settings.py` file. Modify values at your own risk.

Note: Changing any value will require a restart to take effect. See [Troubleshooting](#troubleshooting) to see how to properly restart.

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

In that file, import everything from the `settings.py` module, which contains useful variables and other modules to help writing your custom module.

Write your class as a `commands.Cog` subclass, which takes _only_ a `client` parameter of type `Bot` (from module `bot`) in its
constructor, this allows custom classes to interact with the Bot subclass of `commands.Bot` or `commands.AutoShardedBot`.

Best practices:
- Check out the [example module](./modules/custom_example.py) and follow the [discord.py documentation](https://discordpy.readthedocs.io/en/stable/api.html) for help with the Discord API.
- Check locks before running I/O or VoiceClient operations. These locks are `FILE_OPERATIONS_LOCKED_PERMANENTLY` and `VOICE_OPERATIONS_LOCKED_PERMANENTLY` (from settings, docs included).
- Do _not_ do I/O directly, instead, send the `write_file()` or `open_file()` function (from `iohelpers`) to an asyncio thread and await its result. Or, write your own _async_ I/O functions.
- Do _not_ call `sleep()` or anything that blocks the event loop. Use `asyncio.sleep()` instead.
- Keep helper functions in `helpers.py`. If it grows too big, move your custom functions to a new module.
- Avoid interacting with core modules, they were not written with an API-like system in mind.
- Check the `CAN_LOG` constant before logging exceptions with `LOGGER`.
- Do _not_ use the `TOKEN` constant anywhere unless explicitly required (like running the bot).
- If custom Cogs need other non-default permissions, make sure to enable them in [your application's Installation section](https://discord.com/applications)
- Imports should ideally be kept in the `settings.py` file.

Then, add a new key in `config.json` named `enable_{class_name}` to allow quick enable/disable of the module, and set its value to `true`, or else the bot won't load your Cog.

Start the bot. It will attempt to auto-discover your module and load the appropriate class(es).

Note: the bot will load any class that inherits from `commands.Cog`, independently of the name, adding 'Cog' at the end of your class name keeps it consistent with the default modules.

# Troubleshooting
- If the bot state ends up broken, restarting might help.

  To restart the bot:
  - **Gracefully** terminate the process with **CTRL + C**, this is the preferred way and allows the bot to properly clean up before exiting.
  - Then, run:
  
    `python3 run.py` (UNIX-like)
  
    `python run.py` (Windows)
  
    if the current terminal is **_not_** in the _venv_. Otherwise:
  
    `source ./bin/activate`
    
    `python3 main.py` (UNIX-like)
    
    `.\Scripts\activate.bat`

    `python main.py` (Windows) 
  
    Note: The script `run.py` can be used to launch the bot even after first time configuration.

- If the bot fails to play tracks, ensure the libraries (specifically, `yt_dlp`) are up to date.

  Open a terminal in the project directory and run:
  
  `./bin/pip install --upgrade -r requirements.txt` (UNIX-like)
  
  `.\Scripts\pip.exe install --upgrade -r requirements.txt` (Windows)

  if the current terminal is **_not_** in the _venv_. Otherwise:

  `pip install --upgrade -r requirements.txt` (UNIX-like/Windows)
  
  Then, try again.

- If you have an existing bot that's in over 2500 guilds, ensure the `use_sharding` key is set to `true` in `config.json`

  'Sharding' allows multiple instances of this bot to manage multiple guilds and is required by Discord after a bot reaches 2500 guilds.

# Licensing
This project is licensed under MIT. See [LICENSE](./LICENSE) for more information.