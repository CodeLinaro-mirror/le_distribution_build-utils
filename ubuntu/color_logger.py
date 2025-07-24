"""
color_logger.py

This module provides a color logger class, allowing users to log messages with colored text.
The class includes methods for logging messages at different levels, the same as the standard
python 'logging' mdule : debug, info, warning, error, and critical.

Usage:
    from color_logger import logger

    logger.debug('This is a debug message')
    logger.info('This is an info message')
    logger.warning('This is a warning message')
    logger.error('This is an error message')
    logger.critical('This is a critical message')
"""

import logging
import datetime
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

class ColorLogger:
    LEVEL_STRING = {
        logging.DEBUG:    'DEBG',
        logging.INFO:     'INFO',
        logging.WARNING:  'WARN',
        logging.ERROR:    'ERR ',
        logging.CRITICAL: 'CRIT'
    }

    LEVEL_COLORS = {
        logging.DEBUG:    Fore.CYAN,
        logging.INFO:     Fore.GREEN,
        logging.WARNING:  Fore.YELLOW,
        logging.ERROR:    Fore.RED,
        logging.CRITICAL: Fore.MAGENTA
    }

    def __init__(self, name: str, level=logging.DEBUG):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

    def log(self, level, message):
        color = self.LEVEL_COLORS.get(level, Fore.WHITE)
        level_str = self.LEVEL_STRING.get(level, '    ')
        colored_message = f"{color}{message}{Style.RESET_ALL}"
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        self.logger.log(level, f"[{timestamp}] {level_str} : {colored_message}")

    def debug(self, msg): self.log(logging.DEBUG, msg)
    def info(self, msg): self.log(logging.INFO, msg)
    def warning(self, msg): self.log(logging.WARNING, msg)
    def error(self, msg): self.log(logging.ERROR, msg)
    def critical(self, msg): self.log(logging.CRITICAL, msg)


logger = ColorLogger("BUILD")