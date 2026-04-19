import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """إعداد سجل موحد لكل أجزاء البوت (BOT, USERBOT, RUN)."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        # Format explicitly shows the component's name
        formatter = logging.Formatter(
            "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        handler_sys = logging.StreamHandler(sys.stdout)
        handler_sys.setFormatter(formatter)
        logger.addHandler(handler_sys)

        handler_file = logging.FileHandler("bot.log", encoding="utf-8")
        handler_file.setFormatter(formatter)
        logger.addHandler(handler_file)
        
    return logger
