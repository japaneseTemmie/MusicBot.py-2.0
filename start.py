""" Setup and runner script for discord.py bot. """

from os import name
from subprocess import Popen, SubprocessError, PIPE
from sys import exit as sysexit, version_info, prefix, base_prefix, executable
from os.path import dirname, isfile, isdir, join
from init.logutils import log, separator
from time import sleep

PATH = dirname(__file__)
VENV_PATH = join(PATH, ".venv")
VENV_PYTHON = join(VENV_PATH, "bin", "python3") if name == "posix" else join(VENV_PATH, "Scripts", "python.exe")
VENV_PIP = join(VENV_PATH, "bin", "pip") if name == "posix" else join(VENV_PATH, "Scripts", "pip.exe")
REQUIREMENTS_PATH = join(PATH, "requirements.txt")

cmd_install_venv = [executable, "-m", "venv", VENV_PATH]
cmd_install_deps = [VENV_PIP, "install", "-r", REQUIREMENTS_PATH]
cmd_run_main = [VENV_PYTHON, "main.py"]

# Checks
def check_python_ver() -> bool:
    if version_info < (3, 10):
        log(f"Python 3.10+ is required for this project.", "runner")
        return False
    
    return True

def is_in_venv() -> bool:
    if prefix != base_prefix:
        log("This script cannot be executed inside a venv.", "runner")
        return False
    
    return True

def check_requirements() -> bool:
    if not isfile(REQUIREMENTS_PATH):
        log("requirements.txt file not found.", "runner")
        return False
    
    return True

def venv_exists() -> bool:
    return isdir(VENV_PATH) and isfile(VENV_PYTHON) and isfile(VENV_PIP)

# Wrapper for Popen
def run(command: list[str], sep_process: bool=False) -> int | None:
    """ Run a command. """

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
        log(f"An error occurred while spawning subprocess with command '{' '.join(command)}'\nErr: {e}", "runner")
        return None
    
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

def handle_return_code(code: int | None, command: str) -> bool:
    if code is None or code != 0:
        log(f"Running command '{command}' failed. Exiting...", "runner")
        return False
    
    return True

# Installer functions
def install_venv() -> bool:
    code = run(cmd_install_venv)
    return handle_return_code(code, " ".join(cmd_install_venv))

def install_dependencies() -> bool:
    code = run(cmd_install_deps)
    return handle_return_code(code, " ".join(cmd_install_deps))

# Main
def _do_checks() -> bool:
    """ Run checks before running venv installation or main script. """
    
    checks = [check_python_ver, is_in_venv, check_requirements]
    for check in checks:
        if not check():
            log("Failure exit.", "runner")
            return False
        
    return True

def _ensure_venv() -> bool:
    """ Install/verify venv. """

    log(f"Verifying venv installation in {VENV_PATH}", "runner")
    sleep(0.5)
    if not venv_exists():
        log(f"venv not found! Creating a new venv in {VENV_PATH}", "runner")
        sleep(1)

        if not install_venv():
            return False

        if venv_exists():
            log("Installing dependencies through requirements.txt", "runner")
            sleep(0.5)

            if not install_dependencies():
                return False
        else:
            log("Failed to create venv", "runner")
            return False
    else:
        log(f"venv found at {VENV_PATH}", "runner")
        sleep(0.5)

    return True

def main() -> None:
    if not _do_checks() or not _ensure_venv():
        sysexit(1)

    try:
        log("Running main.py", "runner")
        separator()
        run(cmd_run_main)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
