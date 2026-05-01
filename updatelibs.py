""" Package updater for discord.py bot """

from init.logutils import log

from os.path import join, dirname, isfile, isdir
from sys import exit as sysexit, prefix, base_prefix
from os import name
from subprocess import Popen, SubprocessError, PIPE

PATH = dirname(__file__)

REQUIREMENTS_TXT_PATH = join(PATH, "requirements.txt")

VENV_PATH = join(PATH, ".venv")
VENV_PIP = join(VENV_PATH, "bin", "pip") if name == "posix" else join(VENV_PATH, "Scripts", "pip.exe")
VENV_PYTHON = join(VENV_PATH, "bin", "python3") if name == "posix" else join(VENV_PATH, "Scripts", "python.exe")

UPDATE_COMMAND_VENV = ["pip", "install", "--upgrade", "-r", REQUIREMENTS_TXT_PATH]
UPDATE_COMMAND_NO_VENV = [VENV_PIP,] + UPDATE_COMMAND_VENV[1:]

class CompletedProcess:
    def __init__(self, stdout: str, stderr: str, code: int, pid: int):
        self.pid = pid
        self.stdout = stdout
        self.stderr = stderr
        self.code = code

def check_requirements() -> bool:
    """ Check requirements.txt file """
    
    if not isfile(REQUIREMENTS_TXT_PATH):
        log(f"Unable to update libs: No requirements.txt file present in {PATH}", "libupdater")
        return False
    
    return True

def check_venv() -> bool:
    """ Check if venv and pip exist """
    
    if not isdir(VENV_PATH):
        log(f"Unable to update libs: No venv found at expected path {VENV_PATH}", "libupdater")
        return False
    elif not isfile(VENV_PIP):
        log("Unable to update libs: No pip executable in venv", "libupdater")
        return False
    elif not isfile(VENV_PYTHON):
        log("Unable to update libs: No python3 executable in venv", "libupdater")
        return False

    return True

def is_in_venv() -> bool:
    return prefix != base_prefix

def run(cmd: list[str]) -> CompletedProcess | None:
    """ Run a process. 
    
    Return a `CompletedProcess` instance. """
    
    try:
        process = Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()

        return CompletedProcess(stdout.decode(), stderr.decode(), process.returncode, process.pid)
    except SubprocessError as e:
        log(f"An error occurred while calling Popen().\nErr: {e}", "libupdater")
        return None

def _do_checks() -> bool:
    checks = [check_requirements, check_venv]
    for check in checks:
        if not check():
            log("Failure exit", "libupdater")
            return False
        
    return True

def _do_update() -> bool:
    process = None
    if is_in_venv():
        log(f"Running '{" ".join(UPDATE_COMMAND_VENV)}'", "libupdater")
        process = run(UPDATE_COMMAND_VENV)
    else:
        log(f"Running '{" ".join(UPDATE_COMMAND_NO_VENV)}'", "libupdater")
        process = run(UPDATE_COMMAND_NO_VENV)

    if process is not None:
        if process.code == 0:
            print("Process stdout:\n", process.stdout)
            log(f"Process {process.pid} successfully exited with 0", "libupdater")
        else:
            print("Process stderr:\n", process.stderr)
            log(f"Process {process.pid} failed with code {process.code}", "libupdater")

        return True
    else:
        log("Running subprocess failed.", "libupdater")
    
    return False

def main() -> None:
    if not _do_checks():
        sysexit(1)

    _do_update()
        
    log("done", "libupdater")

if __name__ == "__main__":
    main()