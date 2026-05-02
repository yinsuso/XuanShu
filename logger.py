import logging
import sys
from typing import Optional
from .config import LOG_LEVEL, LOG_FILE


def setup_logger(name: str = "local_agent") -> logging.Logger:
    """配置并返回一个日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if LOG_FILE:
        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"无法创建日志文件 {LOG_FILE}: {e}")
    
    return logger


logger = setup_logger()