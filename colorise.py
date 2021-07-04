from colorama import Fore, Back, Style
from colorama import init as colorama_init


colorama_init()

class Colorise(object):
    @staticmethod
    def red(string):
        return Fore.RED + string + Style.RESET_ALL

    @staticmethod
    def blue(string):
        return Fore.BLUE + string + Style.RESET_ALL

    @staticmethod
    def green(string):
        return Fore.GREEN + string + Style.RESET_ALL

    @staticmethod
    def white(string):
        return Fore.WHITE + string + Style.RESET_ALL

    @staticmethod
    def yellow(string):
        return Fore.YELLOW + string + Style.RESET_ALL

    @staticmethod
    def bg_white(string):
        return Back.WHITE + string + Style.RESET_ALL

    @staticmethod
    def bg_yellow(string):
        return Back.YELLOW + string + Style.RESET_ALL
