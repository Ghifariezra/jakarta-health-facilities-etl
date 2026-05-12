import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import aiohttp
import pandas as pd

from core.google_maps import GoogleMapsClient
from core.logger import get_logger
from utils.checking import is_empty

log = get_logger("Google Geocoding API")

INPUT_CSV = "data/processed/sarana_kesehatan_enriched_backup_2.csv"
OUTPUT_CSV = "data/processed/sarana_kesehatan_enriched_backup_2.csv"


async def main():
    log.info("🚀 Memulai Google Geocoding API (Fallback) untuk sisa data...")
    df = pd.read_csv(
        INPUT_CSV,
        dtype={
            'geo_strategy': object,
            'geo_status': object,
            'kelurahan': object,
            'kecamatan': object
        }
    )

    # 1. Pastikan Tipe Data Aman
    for col in ["lat", "lon", "geo_strategy", "geo_status"]:
        if col not in df.columns:
            df[col] = None

    # Kasus A: punya koordinat (lat/lon) TAPI kecamatan, kelurahan, ATAU alamat ada yang kosong
    # → Pakai Reverse Geocoding untuk melengkapi detailnya
    mask_reverse = (
        df['lat'].notna() & df['lon'].notna() &
        (df['kecamatan'].apply(is_empty) | df['kelurahan'].apply(is_empty) | df['alamat'].apply(is_empty))
    )

    # Kasus B: koordinat (lat/lon) belum ada sama sekali
    # → Pakai Text Geocoding
    mask_geocode = (
        (df['lat'].isna() | df['lon'].isna()) &
        ~mask_reverse
    )

    reverse_indices = df[mask_reverse].index.tolist()
    geocode_indices = df[mask_geocode].index.tolist()

    log.info(f"🔄 Ditemukan {len(reverse_indices)} baris untuk Reverse Geocoding")
    log.info(f"📍 Ditemukan {len(geocode_indices)} baris untuk Text Geocoding")

    if not reverse_indices and not geocode_indices:
        log.info("🎉 Tidak ada data yang perlu dicari lagi!")
        return

    client = GoogleMapsClient()

    async with aiohttp.ClientSession() as session:
        # --- Kasus A: Reverse Geocoding ---
        if reverse_indices:
            log.info("--- Memulai Proses REVERSE Geocoding ---")
            for idx in reverse_indices:
                row = df.loc[idx]
                lat, lon = float(row['lat']), float(row['lon'])

                log.info(f"Row {idx} | Lat: {lat:.5f}, Lon: {lon:.5f}")
                g_data = await client.reverse_geocode(session, lat, lon)

                if g_data:
                    updated = []
                    # Update HANYA jika nilainya saat ini masih kosong
                    if is_empty(df.loc[idx, 'kecamatan']) and g_data.get('kecamatan'):
                        df.loc[idx, 'kecamatan'] = g_data['kecamatan']
                        updated.append(f"kec={g_data['kecamatan']}")
                    if is_empty(df.loc[idx, 'kelurahan']) and g_data.get('kelurahan'):
                        df.loc[idx, 'kelurahan'] = g_data['kelurahan']
                        updated.append(f"kel={g_data['kelurahan']}")
                    if is_empty(df.loc[idx, 'alamat']) and g_data.get('formatted_address'):
                        df.loc[idx, 'alamat'] = g_data['formatted_address']
                        updated.append("alamat=filled")
                    
                    if updated:
                         log.info(f"  ✅ Updated: {', '.join(updated)}")
                    else:
                         log.info("  ⚠️ Data dari Google tidak memberikan detail tambahan.")
                else:
                    log.warning(f"  ❌ Gagal reverse geocode row {idx}")

                await asyncio.sleep(0.5)

        # --- Kasus B: Text Geocoding ---
        if geocode_indices:
             log.info("--- Memulai Proses TEXT Geocoding ---")
             for idx in geocode_indices:
                 row = df.loc[idx]

                 nama = str(row.get('nama_infrastruktur', '')).strip()
                 alamat = str(row.get('alamat', '')).strip()
                 kelurahan = str(row.get('kelurahan', '')).strip()
                 wilayah = str(row.get('wilayah', '')).replace("KOTA ADM. ", "").title().strip()

                 query = None
                 # Coba 1: Nama Tempat + Kelurahan + Wilayah
                 if not is_empty(nama) and not is_empty(kelurahan) and not is_empty(wilayah):
                     query = f"{nama}, {kelurahan}, {wilayah}"
                 # Coba 2: Alamat Lengkap + Wilayah
                 elif not is_empty(alamat) and not is_empty(wilayah):
                     query = f"{alamat}, {wilayah}"
                 # Coba 3: Nama Tempat + Wilayah
                 elif not is_empty(nama) and not is_empty(wilayah):
                     query = f"{nama}, {wilayah}"

                 if not query:
                     log.warning(f"Row {idx}: Data terlalu kosong untuk dicari.")
                     continue

                 log.info(f"Mencari: {query[:60]}...")
                 g_data = await client.geocode_address(session, query)

                 if g_data:
                     # Update koordinat
                     if g_data.get('lat') is not None: df.loc[idx, 'lat'] = float(g_data['lat'])
                     if g_data.get('lon') is not None: df.loc[idx, 'lon'] = float(g_data['lon'])
                     
                     # Update wilayah jika kosong
                     if is_empty(df.loc[idx, 'kelurahan']) and g_data.get('kelurahan'):
                         df.loc[idx, 'kelurahan'] = g_data['kelurahan']
                     if is_empty(df.loc[idx, 'kecamatan']) and g_data.get('kecamatan'):
                         df.loc[idx, 'kecamatan'] = g_data['kecamatan']
                     
                     # Update alamat jika kosong
                     if is_empty(df.loc[idx, 'alamat']) and g_data.get('formatted_address'):
                         df.loc[idx, 'alamat'] = g_data['formatted_address']

                     df.loc[idx, 'geo_strategy'] = 'Google Geocoding API'
                     df.loc[idx, 'geo_status'] = 'SUCCESS'
                     log.info("  ✅ Sukses Text Geocode")
                 else:
                     log.warning(f"  ❌ Gagal text geocode row {idx}")

                 await asyncio.sleep(0.5)

    # 4. Simpan ke File
    df.to_csv(OUTPUT_CSV, index=False)
    log.info(f"✅ Selesai mencoba dengan Geocoding API. Data tersimpan di: {OUTPUT_CSV}")

if __name__ == "__main__":
    asyncio.run(main())