import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import itertools
import math
import time

import aiohttp
import pandas as pd
import numpy as np
from dotenv import load_dotenv

from core.logger import get_logger
from core.nominatim import NominatimClient

load_dotenv()
log = get_logger("Nominatim Populate")

# ── Konfigurasi Proxy Premium ────────────────────────────────────────

PROXY_FILE = "data/proxy/proxyscrape_premium_http_proxies.txt"


def load_premium_proxies():
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
                pass

    if not formatted_proxies:
        return None

    log.info(f"✅ Berhasil memuat {len(formatted_proxies)} Premium Proxies.")
    return itertools.cycle(formatted_proxies)


PROXY_POOL = load_premium_proxies()

# ── Konfigurasi Data ─────────────────────────────────────────────────

INPUT_CSV = "data/raw/sarana_kesehatan_bersih.csv"
OUTPUT_CSV = "data/processed/sarana_kesehatan_enriched.csv"

BATCH_SIZE = 50
MAX_CONCURRENT = 10

_NULL_VALUES = {"", "n/a", "none", "null", "-",
                "na", "tidak ada", "tidak diketahui", "nan"}


def _is_empty(val) -> bool:
    if pd.isna(val):
        return True
    return str(val).strip().lower() in _NULL_VALUES


def _progress_bar(done: int, total: int, width: int = 30) -> str:
    pct = done / total if total else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct*100:5.1f}% ({done}/{total})"


# ── Transform In-Place (Missing Data Filler) ─────────────────────────

async def populate_missing_data(df: pd.DataFrame) -> None:
    client = NominatimClient()

    mask_kec = df['kecamatan'].apply(_is_empty)
    mask_kel = df['kelurahan'].apply(_is_empty)
    mask_alm = df['alamat'].apply(_is_empty)

    mask_pending = mask_kec | mask_kel | mask_alm
    pending_indices = df[mask_pending].index.tolist()

    total_pending = len(pending_indices)
    total_batches = math.ceil(
        total_pending / BATCH_SIZE) if total_pending else 0

    log.info(
        f"🔍 Ditemukan {total_pending} baris dengan data bolong (Kec/Kel/Alm) untuk di-fetch.")
    if not pending_indices:
        log.info(
            "🎉 Semua baris sudah komplit! Tidak ada yang perlu di-populate via API.")
        return

    timeout = aiohttp.ClientTimeout(total=20)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    time_start = time.perf_counter()
    done_so_far = 0

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        for batch_idx, batch_indices in enumerate(
            itertools.batched(pending_indices, BATCH_SIZE), start=1
        ):
            batch_start = time.perf_counter()
            log.info(
                f"BATCH {batch_idx}/{total_batches} — {_progress_bar(done_so_far, total_pending)}")

            async def process_row(idx):
                row = df.loc[idx]

                is_kec_missing = _is_empty(row.get('kecamatan'))
                is_kel_missing = _is_empty(row.get('kelurahan'))
                is_alm_missing = _is_empty(row.get('alamat'))

                wilayah = str(row.get('wilayah', '')).replace(
                    "KOTA ADM. ", "").replace("KAB. ADM. ", "").title()
                jenis = str(row.get('jenis_sarana_kesehatan', ''))
                nama = str(row.get('nama_infrastruktur', ''))

                alamat = str(row.get('alamat', '')
                             ) if not is_alm_missing else ""
                kecamatan = str(row.get('kecamatan', '')
                                ) if not is_kec_missing else ""

                queries_to_try = []

                # --- 1. ATURAN DESKRIPSI USER ---
                if is_kec_missing and is_kel_missing and is_alm_missing:
                    queries_to_try.append(f"{wilayah}, {jenis}, {nama}")
                elif is_kec_missing and is_kel_missing:
                    queries_to_try.append(
                        f"{wilayah}, {jenis}, {nama}, {alamat}")
                elif is_kel_missing:
                    queries_to_try.append(
                        f"{wilayah}, {kecamatan}, {jenis}, {nama}, {alamat}")
                else:
                    queries_to_try.append(f"{wilayah}, {nama}")

                # --- 2. OSM OPTIMIZED FALLBACK (Penyelamat jika aturan user gagal) ---
                # Mengambil nama jalan murni tanpa nomor rumah agar akurasi OSM meningkat drastis
                alamat_jalan = NominatimClient.extract_street_name(
                    NominatimClient.clean_address(alamat))
                if alamat_jalan:
                    # Ampuh mencari kelurahan/kecamatan dari jalan
                    queries_to_try.append(f"{alamat_jalan}, {wilayah}")
                if nama:
                    # Ampuh jika nama jalannya tidak tercatat di OSM
                    queries_to_try.append(f"{nama}, {wilayah}")

                # Buang query yang isinya sama agar tidak membuang kuota API
                queries_to_try = list(dict.fromkeys(queries_to_try))

                current_proxy = next(PROXY_POOL) if PROXY_POOL else None

                data = None
                for q in queries_to_try:
                    params = {"q": q, "format": "jsonv2",
                              "addressdetails": 1, "countrycodes": "id"}
                    data = await client._fetch(session, params, "Populate", current_proxy)
                    if data and len(data) > 0:
                        break  # Jika berhasil dapat data, berhenti mencoba query selanjutnya!

                return idx, data, is_kec_missing, is_kel_missing, is_alm_missing

            tasks = [process_row(idx) for idx in batch_indices]
            results = await asyncio.gather(*tasks)

            # UPDATE DATAFRAME
            for idx, data, is_kec_missing, is_kel_missing, is_alm_missing in results:
                if data and len(data) > 0:
                    addr = data[0].get('address', {})

                    new_kel = addr.get('suburb') or addr.get(
                        'village') or addr.get('neighbourhood')
                    new_kec = addr.get('city_district') or addr.get(
                        'county') or addr.get('town_district')
                    new_alm = f"{addr.get('road', '')} {addr.get('house_number', '')}".strip(
                    )

                    # TIMPA HANYA JIKA SEBELUMNYA KOSONG, biarkan Null/NaN jika tidak ketemu
                    if is_kel_missing and new_kel:
                        df.loc[idx, 'kelurahan'] = new_kel
                    if is_kec_missing and new_kec:
                        df.loc[idx, 'kecamatan'] = new_kec
                    if is_alm_missing and new_alm:
                        df.loc[idx, 'alamat'] = new_alm

                done_so_far += 1

            df.to_csv(OUTPUT_CSV, index=False)

            batch_elapsed = time.perf_counter() - batch_start
            total_elapsed = time.perf_counter() - time_start
            batches_left = total_batches - batch_idx
            eta_seconds = (total_elapsed / batch_idx) * batches_left

            log.info(
                f"Batch {batch_idx} selesai {batch_elapsed:.1f}s | "
                f"ETA: {eta_seconds/60:.1f} mnt"
            )


# ── Ekstraksi Regex Mandiri (0 Detik, Tanpa API) ────────────────────
def regex_extract_from_alamat(df: pd.DataFrame):
    """Mengekstrak Kecamatan & Kelurahan langsung dari teks alamat sebelum menembak API"""
    log.info("🧹 Menjalankan Ekstraksi Regex dari teks Alamat...")

    # 1. Bersihkan null value agar seragam jadi NaN
    for col in ['kecamatan', 'kelurahan', 'alamat']:
        df[col] = df[col].replace(list(_NULL_VALUES), np.nan)

    # 2. Regex Pattern
    regex_kec = r'(?i)(?:kecamatan|kec\.|kec\s)\s*([a-zA-Z\s]+)(?:,|$|kota|kab|rt|rw|[0-9])'
    regex_kel = r'(?i)(?:kelurahan|kel\.|kel\s|desa\s)\s*([a-zA-Z\s]+)(?:,|$|kec|kota|kab|rt|rw|[0-9])'

    # 3. Ekstrak dan timpa HANYA jika nilainya kosong (NaN)
    ekstrak_kec = df['alamat'].str.extract(
        regex_kec, expand=False).str.strip().str.title()
    ekstrak_kel = df['alamat'].str.extract(
        regex_kel, expand=False).str.strip().str.title()

    df['kecamatan'] = df['kecamatan'].fillna(ekstrak_kec)
    df['kelurahan'] = df['kelurahan'].fillna(ekstrak_kel)

    return df


# ── Main ──────────────────────────────────────────────────────────────

async def main():
    log.info("=" * 60)
    log.info("MULAI — Transform: Populate Data Null dengan API & Regex")
    log.info("=" * 60)

    start = time.perf_counter()

    if not os.path.exists(INPUT_CSV):
        log.error(f"File {INPUT_CSV} tidak ditemukan!")
        return

    df = pd.read_csv(INPUT_CSV)

    # JURUS 1: REGEX OTOMATIS (Sangat Cepat, 0 Kuota API)
    df = regex_extract_from_alamat(df)
    df.to_csv(OUTPUT_CSV, index=False)  # Simpan hasil regex

    # JURUS 2: API NOMINATIM DENGAN OSM-OPTIMIZED FALLBACK
    await populate_missing_data(df)

    # Laporan Akhir
    elapsed = time.perf_counter() - start
    df_final = pd.read_csv(OUTPUT_CSV)

    sisa_kec = df_final['kecamatan'].apply(_is_empty).sum()
    sisa_kel = df_final['kelurahan'].apply(_is_empty).sum()
    sisa_alm = df_final['alamat'].apply(_is_empty).sum()

    log.info("=" * 60)
    log.info("SELESAI — Ringkasan Final Populate")
    log.info(f"  Sisa Kecamatan Null : {sisa_kec}")
    log.info(f"  Sisa Kelurahan Null : {sisa_kel}")
    log.info(f"  Sisa Alamat Null    : {sisa_alm}")
    log.info(f"  Waktu total         : {elapsed/60:.1f} menit")
    log.info("  *Catatan: Sisa data yang Null dibiarkan tetap kosong (NaN).")
    log.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
