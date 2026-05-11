import logging
import sys
from logging.handlers import RotatingFileHandler
from config import get_data_path

def get_logger(name: str) -> logging.Logger:
    """إعداد سجل موحد لكل أجزاء البوت (BOT, USERBOT, RUN)."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False
        # Format explicitly shows the component's name
        formatter = logging.Formatter(
            "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        handler_sys = logging.StreamHandler(sys.stdout)
        handler_sys.setFormatter(formatter)
        logger.addHandler(handler_sys)

        handler_file = RotatingFileHandler(
            get_data_path("bot.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        handler_file.setFormatter(formatter)
        logger.addHandler(handler_file)
        
    return logger
