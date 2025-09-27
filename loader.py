""" Loader module for discord.py bot.

Helper module to dynamically load all modules found in a specified directory. """

from settings import CONFIG, CAN_LOG, LOGGER
from init.logutils import log, log_to_discord_log

from discord.ext import commands
from os.path import isdir
from os import listdir
from inspect import getmembers, isclass
from importlib import import_module
from types import ModuleType

class ModuleLoader:
    """ Loader class

    Dynamically loads all modules found in `modules_directory`. """
    
    def __init__(self, modules_directory: str):
        self.path = modules_directory
        
    def _get_paths(self) -> list[str] | None:
        """ Return a list of module names found in `modules_directory`. """
        
        if not isdir(self.path):
            log(f"Invalid modules path '{self.path}'")
            return None

        try:
            tree = listdir(self.path)

            return tree
        except OSError as e:
            log(f"An error occured while opening directory '{self.path}'\nErr: {e}")
            log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)
            
            return None

    def get_module_names(self) -> list[str] | list:
        """ Return a list of module directory + names. """
        
        module_names = []
        module_list = self._get_paths()
        
        if module_list is None:
            return module_names

        for name in module_list:
            if name.endswith(".py") and not name.startswith("__"):
                module_names.append(f"{self.path}.{name[:-3]}")

        return module_names

    def get_module_contents(self, module_names: list[str]) -> list[ModuleType]:
        """ Import the modules and return a list. """
        
        imported_modules = []
        for name in module_names:
            try:
                module = import_module(name)
                imported_modules.append(module)
            except Exception as e:
                log(f"An error occured while importing module '{name}'")

                log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)

        return imported_modules
    
    def get_enable_values_from_config(self, class_names: list[str]) -> list[tuple[str, bool]]:
        """ Returns the corresponding enable value for each Cog in config.json """
        
        return [
            (name, CONFIG.get(f"enable_{name}", False))
            for name in class_names
        ]

    def get_classes(self) -> list[type[commands.Cog]]:
        """ Returns all classes that inherit from `commands.Cog` in the found modules. """

        classes = []
        modules = self.get_module_contents(self.get_module_names())

        for module in modules:
            
            for _, obj in getmembers(module, isclass):
                if issubclass(obj, commands.Cog) and obj.__module__ == module.__name__:
                    classes.append(obj)
        
        return classes