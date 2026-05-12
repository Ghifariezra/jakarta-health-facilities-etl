import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import itertools
import math
import time

import aiohttp
import pandas as pd
from dotenv import load_dotenv

from core.logger import get_logger
from core.google_maps import GoogleMapsClient
from utils.checking import is_empty, progress_bar

load_dotenv()
log = get_logger("Google Places API")

INPUT_CSV = "data/processed/sarana_kesehatan_enriched.csv"
OUTPUT_CSV = "data/processed/sarana_kesehatan_enriched.csv"

# BATCH & CONCURRENCY
# BATCH_SIZE sedikit dinaikkan karena client sudah memiliki auto-retry 429
BATCH_SIZE = 30
MAX_CONCURRENT = 5

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


async def enrich_with_google(df: pd.DataFrame):
    client = GoogleMapsClient()

    # FILTER: Cari yang Kecamatan ATAU Kelurahan ATAU Lat/Lon nya Kosong/Gagal
    mask_missing = (
        (df['kecamatan'].apply(is_empty)) |
        (df['kelurahan'].apply(is_empty)) |
        (df['lat'].isna()) |
        (df['lon'].isna()) |
        (df['geo_status'] == 'FAILED') |
        (df['geo_status'] == 'UNPROCESSED')
    )

    pending_indices = df[mask_missing].index.tolist()
    total_pending = len(pending_indices)
    total_batches = math.ceil(
        total_pending / BATCH_SIZE) if total_pending else 0

    log.info(
        f"🔍 Ditemukan {total_pending} baris dengan data bolong. Mengirim ke Google API...")
    if not pending_indices:
        log.info(
            "🎉 SEMUA DATA SUDAH KOMPLIT 100%! Tidak ada yang perlu dikirim ke Google.")
        return

    # Client Session dengan Timeout lebih toleran untuk mengakomodasi auto-retry di dalam client
    timeout = aiohttp.ClientTimeout(total=45)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    time_start = time.perf_counter()
    done_so_far = 0

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        for batch_idx, batch_indices in enumerate(
            itertools.batched(pending_indices, BATCH_SIZE), start=1
        ):
            batch_start = time.perf_counter()
            log.info(
                f"BATCH {batch_idx}/{total_batches} — {progress_bar(done_so_far, total_pending)}")

            async def process_row(idx):
                row = df.loc[idx]
                nama = str(row.get('nama_infrastruktur', '')).strip()
                wilayah = str(row.get('wilayah', '')).replace(
                    "KOTA ADM. ", "").title().strip()
                alamat = str(row.get('alamat', '')).strip()

                # Lewati jika nama infrastruktur tidak ada
                if is_empty(nama):
                    return idx, None

                # Query 1: Spesifik (Nama, Alamat, Wilayah)
                query = f"{nama}, {alamat}, {wilayah}".strip(", ")
                result = await client.search_place(session, query)

                # Fallback Query 2: Lebih luas (Nama + Wilayah) jika query spesifik gagal
                if not result and not is_empty(alamat):
                    query_fallback = f"{nama}, {wilayah}".strip(", ")
                    log.debug(
                        f"Row {idx}: Query spesifik gagal, mencoba fallback: {query_fallback}")
                    result = await client.search_place(session, query_fallback)

                return idx, result

            tasks = [process_row(idx) for idx in batch_indices]
            results = await asyncio.gather(*tasks)

            # UPDATE DATAFRAME
            for idx, g_data in results:
                if g_data:
                    # Update data HANYA jika nilainya valid dari Google
                    if g_data.get('kelurahan'):
                        df.loc[idx, 'kelurahan'] = g_data['kelurahan']
                    if g_data.get('kecamatan'):
                        df.loc[idx, 'kecamatan'] = g_data['kecamatan']
                    if g_data.get('lat') is not None:
                        df.loc[idx, 'lat'] = float(g_data['lat'])
                    if g_data.get('lon') is not None:
                        df.loc[idx, 'lon'] = float(g_data['lon'])

                    df.loc[idx, 'geo_strategy'] = 'Google Places API'
                    df.loc[idx, 'geo_status'] = 'SUCCESS'

                done_so_far += 1

            # Save checkpoint per batch
            df.to_csv(OUTPUT_CSV, index=False)

            batch_elapsed = time.perf_counter() - batch_start
            total_elapsed = time.perf_counter() - time_start
            batches_left = total_batches - batch_idx
            eta_seconds = (total_elapsed / batch_idx) * batches_left

            log.info(
                f"Batch {batch_idx} selesai {batch_elapsed:.1f}s | "
                f"ETA: {eta_seconds/60:.1f} mnt"
            )

            # Jeda diatur ke 1 detik karena retry_delay di GoogleMapsClient akan menangani throttles
            await asyncio.sleep(1)


async def main():
    log.info("=" * 60)
    log.info("MULAI — Google Places API Smart Imputation")
    log.info("=" * 60)
    start = time.perf_counter()

    # Memastikan tipe data agar tidak terjadi ValueError
    df = pd.read_csv(
        INPUT_CSV,
        dtype={
            'geo_strategy': object,
            'geo_status': object,
            'kelurahan': object,
            'kecamatan': object
        }
    )

    # Inisialisasi kolom jika belum ada
    for col in ["lat", "lon", "geo_strategy", "geo_status"]:
        if col not in df.columns:
            df[col] = None

    await enrich_with_google(df)

    # REKAPITULASI
    df_final = pd.read_csv(OUTPUT_CSV)
    sisa_kec = df_final['kecamatan'].apply(is_empty).sum()
    sisa_kel = df_final['kelurahan'].apply(is_empty).sum()
    sisa_lat = df_final['lat'].isna().sum()

    sukses_google = len(
        df_final[df_final['geo_strategy'] == 'Google Places API'])

    elapsed = time.perf_counter() - start

    log.info("=" * 60)
    log.info("SELESAI — Ringkasan Google Places API")
    log.info(f"  Diperbaiki Google : {sukses_google} data")
    log.info(f"  Sisa Kecamatan Null: {sisa_kec}")
    log.info(f"  Sisa Kelurahan Null: {sisa_kel}")
    log.info(f"  Sisa Lat/Lon Null  : {sisa_lat}")
    log.info(f"  Waktu eksekusi    : {elapsed/60:.1f} menit")
    log.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
