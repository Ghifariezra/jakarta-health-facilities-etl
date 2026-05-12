import aiohttp
import os
import itertools
from core.logger import get_logger

log = get_logger("proxy")

# ── Konfigurasi Proxy Premium ────────────────────────────────────────

PROXY_FILE = "data/proxy/proxyscrape_premium_http_proxies.txt"

def load_premium_proxies() -> "itertools.cycle | None":
    """Membaca list proxy dari file format user:pass@ip:port"""
    if not os.path.exists(PROXY_FILE):
        log.warning(
            f"⚠️ File proxy {PROXY_FILE} tidak ditemukan! Berjalan TANPA proxy.")
        return None

    formatted_proxies = []
    with open(PROXY_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                auth_part, ip_part = line.split("@")
                user, pwd = auth_part.split(":")
                formatted_proxies.append({
                    "url": f"http://{ip_part}",
                    "auth": aiohttp.BasicAuth(user, pwd)
                })
            except ValueError:
                log.warning(
                    f"⚠️ Format baris proxy tidak dikenali (dilewati): {line}")

    if not formatted_proxies:
        return None

    log.info(f"✅ Berhasil memuat {len(formatted_proxies)} Premium Proxies.")
    return itertools.cycle(formatted_proxies)

PROXY_POOL = load_premium_proxies()