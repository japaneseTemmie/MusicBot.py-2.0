""" Setup script for discord.py bot. """

from os.path import dirname, exists, join
from os import name
from subprocess import Popen, SubprocessError, PIPE
from sys import exit as sysexit, version_info, prefix, base_prefix, executable
from time import sleep
from datetime import datetime
from random import choice
from colors import Colors, all_colors

PATH = dirname(__file__)
VENV_PATH = join(PATH, ".venv")
VENV_PYTHON = join(VENV_PATH, "bin", "python3") if name == "posix" else join(VENV_PATH, "Scripts", "python.exe")
VENV_PIP = join(VENV_PATH, "bin", "pip") if name == "posix" else join(VENV_PATH, "Scripts", "pip.exe")
DEFAULT_DEPENDENCIES = "discord.py\nPyNaCl\nyt_dlp\npython-dotenv\ncachetools"

cmd_install_venv = [executable, "-m", "venv", VENV_PATH]
cmd_install_deps = [VENV_PIP, "install", "-r", "requirements.txt"]
cmd_run_main = [VENV_PYTHON, "main.py"]

def log(msg: str, sleep_for: float=0) -> None:
    print(f"{choice(all_colors)}[runner]{Colors.RESET} | {choice(all_colors)}{datetime.now().strftime('%d/%m/%Y @ %H:%M:%S')}{Colors.RESET} | {choice(all_colors)}{msg}{Colors.RESET}")
    if sleep_for > 0:
        sleep(sleep_for)

def separator() -> None:
    print("------------------------------")

def check_python_ver() -> None:
    if version_info < (3, 10):
        log(f"Python 3.10+ is required for this project.", 2)
        sysexit(1)

def is_in_venv() -> None:
    if prefix != base_prefix:
        log("This script cannot be executed inside a venv.")
        sysexit(1)

def run(command: list[str], sep_process: bool=False) -> int:
    """ Spawn the process in a separate group so it's not affected by the runner script. """
    if name == "posix":
        from os import setsid

        creationflags = 0
        preexec_fn = setsid
    else:
        from subprocess import CREATE_NEW_PROCESS_GROUP

        creationflags = CREATE_NEW_PROCESS_GROUP
        preexec_fn = None
    
    try:
        process = Popen(command,
                        stdout=PIPE if sep_process else None,
                        stderr=PIPE if sep_process else None,
                        creationflags=creationflags,
                        preexec_fn=preexec_fn
                        )
    except SubprocessError as e:
        log(f"An error occurred while spawning subprocess with command '{' '.join(command)}'\nErr: {e}")
        sysexit(1) # No point in continuing
    
    try:
        return process.wait()
    except KeyboardInterrupt:
        if name == "posix":
            from os import killpg, getpgid
            from signal import SIGINT

            killpg(getpgid(process.pid), SIGINT)
        else:
            from signal import CTRL_BREAK_EVENT

            try:
                process.send_signal(CTRL_BREAK_EVENT)
            except Exception:
                process.terminate() # Fallback
        return process.wait()

def write(fp: str, content: str) -> bool:
    try:
        with open(fp, "w") as f:
            f.write(content)
        return True
    except OSError as e:
        log(f"An error occurred while writing to {fp}.\nErr: {e}")
        return False

def handle_return_code(code: int, command: str) -> None:
    if code != 0:
        log(f"Running command '{command}' failed. Exiting...")
        sysexit(1)

def venv_exists() -> bool:
    return exists(VENV_PYTHON)

def ensure_requirements() -> None:
    if not exists(join(PATH, "requirements.txt")):
        log("requirements.txt file not found. Creating file..")
        sleep(1)

        success = write(join(PATH, "requirements.txt"), DEFAULT_DEPENDENCIES)

        if not success:
            sysexit(1)

def install_venv() -> None:
    code = run(cmd_install_venv)
    handle_return_code(code, " ".join(cmd_install_venv))

def install_dependencies() -> None:
    code = run(cmd_install_deps)
    handle_return_code(code, " ".join(cmd_install_deps))

def main() -> None:
    check_python_ver()
    is_in_venv()
    
    log(f"Verifying venv installation in {VENV_PATH}",0.5)
    if not venv_exists():
        log(f"venv not found! Creating a new venv in {VENV_PATH}",1.5)
        install_venv()

        if venv_exists():
            log("Checking requirements.txt",0.5)
            ensure_requirements()

            log("Installing dependencies through requirements.txt",0.5)
            install_dependencies()
    else:
        log(f"venv found at {VENV_PATH}", 0.5)

    try:
        log("Running main.py")
        separator()
        run(cmd_run_main)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
