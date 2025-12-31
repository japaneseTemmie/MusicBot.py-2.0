""" Setup script for discord.py bot. """

from os.path import dirname, exists, join
from os import name
from subprocess import Popen, SubprocessError, PIPE
from sys import exit as sysexit, version_info, prefix, base_prefix, executable
from time import sleep
from init.logutils import log, separator

PATH = dirname(__file__)
VENV_PATH = join(PATH, ".venv")
VENV_PYTHON = join(VENV_PATH, "bin", "python3") if name == "posix" else join(VENV_PATH, "Scripts", "python.exe")
VENV_PIP = join(VENV_PATH, "bin", "pip") if name == "posix" else join(VENV_PATH, "Scripts", "pip.exe")

cmd_install_venv = [executable, "-m", "venv", VENV_PATH]
cmd_install_deps = [VENV_PIP, "install", "-r", "requirements.txt"]
cmd_run_main = [VENV_PYTHON, "main.py"]

def check_python_ver() -> None:
    if version_info < (3, 10):
        log(f"Python 3.10+ is required for this project.", "runner")
        sleep(2)

        sysexit(1)

def is_in_venv() -> None:
    if prefix != base_prefix:
        log("This script cannot be executed inside a venv.", "runner")
        sysexit(1)

def run(command: list[str], sep_process: bool=False) -> int:
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
        sysexit(1)
    
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

def handle_return_code(code: int, command: str) -> None:
    if code != 0:
        log(f"Running command '{command}' failed. Exiting...", "runner")
        sysexit(1)

def venv_exists() -> bool:
    return exists(VENV_PATH) and exists(VENV_PYTHON) and exists(VENV_PIP)

def check_requirements() -> None:
    if not exists(join(PATH, "requirements.txt")):
        log("requirements.txt file not found.", "runner")
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
    check_requirements()

    log(f"Verifying venv installation in {VENV_PATH}", "runner")
    sleep(0.5)
    if not venv_exists():
        log(f"venv not found! Creating a new venv in {VENV_PATH}", "runner")
        sleep(2)

        install_venv()

        if venv_exists():
            log("Checking requirements.txt", "runner")
            sleep(0.5)

            log("Installing dependencies through requirements.txt", "runner")
            sleep(0.5)

            install_dependencies()
        else:
            log("Failed to create venv", "runner")
            sysexit(1)
    else:
        log(f"venv found at {VENV_PATH}", "runner")
        sleep(0.5)

    try:
        log("Running main.py", "runner")
        separator()
        run(cmd_run_main)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
