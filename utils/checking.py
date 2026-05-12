import pandas as pd

_NULL_VALUES = {"", "n/a", "none", "null", "-",
                "na", "tidak ada", "tidak diketahui", "nan"}

def is_empty(val) -> bool:
    if pd.isna(val):
        return True
    return str(val).strip().lower() in _NULL_VALUES

def progress_bar(done: int, total: int, width: int = 30) -> str:
    pct = done / total if total else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct*100:5.1f}% ({done}/{total})"
