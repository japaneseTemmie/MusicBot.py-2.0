""" Loader module\n
Helper module to dynamically load all modules found in a specified directory. """

from settings import *

class Loader:
    """ Loader class\n
    Dynamically load all modules found in modules_dir. """
    def __init__(self, modules_dir: str):
        self.path = modules_dir

    def _check_dir(self, path: str) -> bool:
        if not isdir(path):
            log(f"Invalid module path '{path}'")
            return False
        
        return True
    
    def _check_contents(self, path: str) -> tuple[bool, list]:
        if self._check_dir(path):
            tree = listdir(path)
        else:
            tree = []
        
        if not tree:
            log(f"Nothing found in '{path}'")
            return (False, tree)
        
        return (True, tree)

    def get_module_file_paths(self) -> list[str]:
        """ Return a list of module names from file paths """
        
        modules = []
        contents_exist, directory = self._check_contents(self.path)
        
        if not contents_exist:
            return modules

        for file in directory:
            if file.endswith(".py") and not file.startswith("__"):
                modules.append(f"{self.path}.{file[:-3]}")

        return modules

    def get_module_contents(self, all_modules: list[str]) -> list[ModuleType]:
        """ Import the modules and return a list. """
        
        imported_modules = []
        for module_file in all_modules:
            try:
                module = import_module(module_file)
                imported_modules.append(module)
            except Exception as e:
                log(f"An error occured while importing module '{module_file}'")

                if CAN_LOG and LOGGER is not None:
                    LOGGER.exception(e)

        return imported_modules
    
    def get_enable_values_from_config(self, class_names: list[str]) -> list[tuple[str, bool]]:
        return [
            (key, CONFIG[key])
            for name in class_names
            if (key := f"enable_{name}") in CONFIG
        ]

    def get_classes(self) -> list[commands.Cog]:
        classes = []
        all_modules = self.get_module_contents(self.get_module_file_paths())

        for module in all_modules:
            
            for _, obj in getmembers(module, isclass):
                if issubclass(obj, commands.Cog) and obj.__module__ == module.__name__:
                    classes.append(obj)
        
        return classes