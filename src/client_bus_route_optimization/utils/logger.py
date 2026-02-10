import logging
import os
from logging.handlers import RotatingFileHandler

CONSOLE_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(processName)s] %(message)s"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(processName)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_dir: str = "logs"):
    """
    Logging đơn giản cho CLI.
    Mỗi process ghi vào file riêng (app_{pid}.log) để tránh
    PermissionError khi RotatingFileHandler rotate trên Windows.
    """
    os.makedirs(log_dir, exist_ok=True)

    pid = os.getpid()

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(CONSOLE_LOG_FORMAT, DATE_FORMAT))

    app_file = RotatingFileHandler(
        os.path.join(log_dir, f"app_{pid}.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    app_file.setLevel(logging.DEBUG)
    app_file.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    err_file = RotatingFileHandler(
        os.path.join(log_dir, f"error_{pid}.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    err_file.setLevel(logging.WARNING)
    err_file.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(app_file)
    root.addHandler(err_file)