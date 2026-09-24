import logging
import sys
from typing import Optional

def setup_logging(logger_name: str = __name__, log_file: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """
    Sets up and returns a configured logger.
    Ensures uniform logging across all application modules.
    """
    logger = logging.getLogger(logger_name)
    
    if not logger.handlers:
        logger.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        if log_file:
            file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
    return logger
