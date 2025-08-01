from os.path import dirname, exists, join
from os import name
from subprocess import Popen, SubprocessError, PIPE
from sys import exit as sysexit, version_info, prefix, base_prefix
from typing import NoReturn
from time import sleep
from datetime import datetime

def check_python_ver() -> None | NoReturn:
    if version_info < (3, 10):
        log(f"Python 3.10+ is required for this project.", 2)
        sysexit(1)

def is_in_venv() -> None | NoReturn:
    if prefix != base_prefix:
        log("This script cannot be executed inside a venv.")
        sysexit(1)

PATH = dirname(__file__)
VENV_PYTHON = join(PATH, "bin", "python3") if name == "posix" else join(PATH, "Scripts", "python.exe")
VENV_PIP = join(PATH, "bin", "pip") if name == "posix" else join(PATH, "Scripts", "pip.exe")
DEFAULT_DEPENDENCIES = "discord\nPyNaCl\nyt_dlp\npython-dotenv\ncachetools"

cmd_install_venv = ["python3", "-m", "venv", PATH] if name == "posix" else ["python", "-m", "venv", PATH]
cmd_install_deps = [VENV_PIP, "install", "-r", "requirements.txt"]
cmd_run_main = [VENV_PYTHON, "main.py"]

def log(content: str, sleep_for: float=0) -> None:
    print(f"[runner] | {datetime.now().strftime('%d/%m/%Y @ %H:%M:%S')} | {content}")
    if sleep_for > 0:
        sleep(sleep_for)

def separator() -> None:
    print("------------------------------")

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
        log(f"An error occurred while spawning subprocess with command '{' '.join(command)}'")
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

def handle_return_code(code: int, command: str) -> None | NoReturn:
    if code != 0:
        log(f"Running command '{command}' failed. Exiting...")
        sysexit(1)

def venv_exists() -> bool:
    return exists(VENV_PYTHON)

def requirements_exist() -> None | NoReturn:
    if not exists(join(PATH, "requirements.txt")):
        log("requirements.txt file not found. Creating file..")
        sleep(1)

        success = write(join(PATH, "requirements.txt"), DEFAULT_DEPENDENCIES)

        if not success:
            sysexit(1)

def install_venv() -> None | NoReturn:
    code = run(cmd_install_venv)
    handle_return_code(code, " ".join(cmd_install_venv))

def install_dependencies() -> None | NoReturn:
    code = run(cmd_install_deps)
    handle_return_code(code, " ".join(cmd_install_deps))

def main() -> None | NoReturn:
    check_python_ver()
    is_in_venv()
    
    log(f"Verifying venv installation in {PATH}",0.5)
    if not venv_exists():
        log(f"venv not found! Creating a new venv in {PATH}",1.5)
        install_venv()

        if venv_exists():
            log("Checking requirements.txt",0.5)
            requirements_exist()

            log("Installing dependencies through requirements.txt",0.5)
            install_dependencies()
    else:
        log(f"venv found at {VENV_PYTHON}", 0.5)

    try:
        log("Running main.py")
        separator()
        run(cmd_run_main)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
