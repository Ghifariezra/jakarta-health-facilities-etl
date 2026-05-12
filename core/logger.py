# core/logger.py
#
# Logger sederhana dengan fitur:
# - Tulis ke file + console sekaligus
# - OVERWRITE file setiap kali script dijalankan ulang (mode="w")
# - Auto-rotate jika file > MAX_BYTES dalam 1 kali run (default 5MB)
# - Simpan max 3 file backup
# - Format: [TIMESTAMP] LEVEL | pesan
# - Singleton (satu instance per nama logger)
# ─────────────────────────────────────────────────────────────────────

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Direktori log (relatif terhadap root project)
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "etl.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

# Format: [2026-05-10 02:30:00] INFO  | pesan
_FORMAT = "[%(asctime)s] %(levelname)-5s | %(message)s"
_DATE = "%Y-%m-%d %H:%M:%S"

# Cache agar get_logger() tidak buat handler duplikat
_loggers: dict[str, logging.Logger] = {}

def get_logger(name: str = "etl", level: int = logging.INFO) -> logging.Logger:
    """
    Ambil atau buat logger dengan nama tertentu.
    Aman dipanggil berkali-kali — tidak akan duplikasi handler.
    """
    if name in _loggers:
        return _loggers[name]

    # Buat direktori log jika belum ada
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Jangan tambah handler jika sudah ada (untuk reload-safe)
    if logger.handlers:
        _loggers[name] = logger
        return logger

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE)

    # ── Handler 1: Tulis ke file (Overwrite Mode) ────────────────
    file_handler = RotatingFileHandler(
        LOG_FILE,
        mode="w",  # <--- KUNCI OVERWRITE: Ubah default 'a' menjadi 'w'
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # ── Handler 2: Tampilkan ke console ──────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Jangan propagate ke root logger (cegah output duplikat)
    logger.propagate = False

    _loggers[name] = logger
    return logger
