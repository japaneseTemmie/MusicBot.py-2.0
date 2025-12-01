""" Package updater for discord.py bot """

from init.logutils import log

from os.path import join, dirname, exists
from os import name
from sys import exit as sysexit, prefix, base_prefix
from subprocess import Popen, PIPE

PATH = dirname(__file__)

REQUIREMENTS_TXT_PATH = join(PATH, "requirements.txt")

VENV_PATH = join(PATH, ".venv")
VENV_PIP = join(VENV_PATH, "bin", "pip") if name == "posix" else join(VENV_PATH, "Scripts", "pip.exe")

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
    
    if not exists(REQUIREMENTS_TXT_PATH):
        log("Unable to update libs: No requirements.txt", "libupdater")
        return False
    
    return True

def check_venv() -> bool:
    """ Check if venv and pip exist """
    
    if not exists(VENV_PATH):
        log("Unable to update libs: No venv path", "libupdater")
        return False
    elif not exists(VENV_PIP):
        log("Unable to update libs: No pip in venv", "libupdater")
        return False

    return True

def is_in_venv() -> bool:
    return prefix != base_prefix

def run(proc: list[str]) -> CompletedProcess:
    """ Run a process. 
    
    Return True if exit code is 0. """
    
    process = Popen(proc, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()

    return CompletedProcess(stdout.decode(), stderr.decode(), process.returncode, process.pid)

def main() -> None:
    process_completion = None
    checks = [check_requirements(), check_venv()]
    if not all(checks):
        log("Failure exit", "libupdater")
        sysexit(1)

    if is_in_venv():
        log(f"Running '{" ".join(UPDATE_COMMAND_VENV)}'", "libupdater")
        process_completion = run(UPDATE_COMMAND_VENV)
    else:
        log(f"Running '{" ".join(UPDATE_COMMAND_NO_VENV)}'", "libupdater")
        process_completion = run(UPDATE_COMMAND_NO_VENV)

    if process_completion is not None:
        if process_completion.code == 0:
            print("Process stdout:\n", process_completion.stdout)
            log(f"Process {process_completion.pid} successfully exited with 0", "libupdater")
        else:
            print("Process stderr:\n", process_completion.stderr)
            log(f"Process {process_completion.pid} failed with code {process_completion.code}", "libupdater")
        
        log("done", "libupdater")

if __name__ == "__main__":
    main()