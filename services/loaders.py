import urllib.parse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pandas as pd
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from core.logger import get_logger
from core.models import (
    Wilayah, Kecamatan, Kelurahan, JenisSarana,
    GeoStrategy, GeoStatus, Infrastruktur
)

# Load environment variables
load_dotenv()
log = get_logger("db_loader")

INPUT_CSV = "data/processed/sarana_kesehatan_enriched_final.csv"

# ---------------------------------------------------------
# 1. SETUP KONEKSI ASYNC KE SUPABASE
# ---------------------------------------------------------
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")
HOST = os.getenv("HOST")
PORT = os.getenv("PORT")
DBNAME = os.getenv("DATABASE")

# Encode password agar aman dari special characters
safe_password = urllib.parse.quote_plus(PASSWORD)

# Menggunakan driver asyncpg dan password yang sudah aman
DATABASE_URL = f"postgresql+asyncpg://{USER}:{safe_password}@{HOST}:{PORT}/{DBNAME}"

# Buat Async Engine.
# Catatan: Supabase membutuhkan SSL, asyncpg menggunakan connect_args untuk SSL
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set True jika ingin melihat query SQL yang berjalan di terminal
    connect_args={"ssl": "require"},
    pool_size=10,
    max_overflow=15
)

# Session factory khusus async
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# ---------------------------------------------------------
# 2. MEMORY CACHE (Untuk mempercepat lookup ID)
# ---------------------------------------------------------
cache = {
    "wilayah": {},        # {"Nama Wilayah": UUID}
    "kecamatan": {},      # {(Wilayah_UUID, "Nama Kecamatan"): UUID}
    "kelurahan": {},      # {(Kecamatan_UUID, "Nama Kelurahan"): UUID}
    "jenis_sarana": {},   # {"Nama Jenis": UUID}
    "geo_strategy": {},   # {"Nama Strategy": UUID}
    "geo_status": {}      # {"Nama Status": UUID}
}

async def get_or_create(session: AsyncSession, model, cache_dict: dict, cache_key: tuple | str, **kwargs):
    """
    Mencari ID di memori RAM -> Jika tidak ada, cari di DB -> Jika tidak ada, Insert Baru.
    """
    if cache_key in cache_dict:
        return cache_dict[cache_key]

    stmt = select(model).filter_by(**kwargs)
    result = await session.execute(stmt)
    instance = result.scalars().first()

    if not instance:
        instance = model(**kwargs)
        session.add(instance)
        await session.flush()  # Dapatkan UUID tanpa perlu commit total

    cache_dict[cache_key] = instance.id
    return instance.id

# ---------------------------------------------------------
# 3. FUNGSI UTAMA LOAD DATA
# ---------------------------------------------------------

async def load_data_to_db():
    log.info("🚀 Memulai proses Load Data Asinkron ke PostgreSQL...")

    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        log.error(f"❌ File {INPUT_CSV} tidak ditemukan!")
        return

    total_rows = len(df)
    log.info(f"📊 Ditemukan {total_rows} baris data untuk disisipkan.")

    async with AsyncSessionLocal() as session:
        try:
            for index, row in df.iterrows():
                if index % 500 == 0 and index > 0:
                    log.info(
                        f"⏳ Sedang memproses baris {index} / {total_rows}...")

                # --- RESOLVE DIMENSI (Lookup Tables) ---
                wilayah_name = str(row['wilayah']).strip()
                w_id = await get_or_create(session, Wilayah, cache["wilayah"], wilayah_name, nama_wilayah=wilayah_name)

                kec_name = str(row['kecamatan']).strip()
                kec_key = (w_id, kec_name)
                kec_id = await get_or_create(session, Kecamatan, cache["kecamatan"], kec_key, wilayah_id=w_id, nama_kecamatan=kec_name)

                kel_name = str(row['kelurahan']).strip()
                kel_key = (kec_id, kel_name)
                kel_id = await get_or_create(session, Kelurahan, cache["kelurahan"], kel_key, kecamatan_id=kec_id, nama_kelurahan=kel_name)

                js_name = str(row['jenis_sarana_kesehatan']).strip()
                js_id = await get_or_create(session, JenisSarana, cache["jenis_sarana"], js_name, nama_jenis=js_name)

                g_strat = str(row['geo_strategy']).strip()
                strat_id = await get_or_create(session, GeoStrategy, cache["geo_strategy"], g_strat, nama_strategy=g_strat)

                g_status = str(row['geo_status']).strip()
                status_id = await get_or_create(session, GeoStatus, cache["geo_status"], g_status, nama_status=g_status)

                # --- PREPARE FACT TABLE UPSERT ---
                stmt = insert(Infrastruktur).values(
                    periode_data=int(row['periode_data']),
                    kelurahan_id=kel_id,
                    jenis_sarana_id=js_id,
                    geo_strategy_id=strat_id,
                    geo_status_id=status_id,
                    nama_infrastruktur=str(row['nama_infrastruktur']).strip(),
                    alamat=str(row['alamat']).strip(),
                    lat=float(row['lat']),
                    lon=float(row['lon'])
                )

                # UPSERT: Update data jika infrastruktur ini sudah ada di database
                stmt = stmt.on_conflict_do_update(
                    constraint='uq_infrastruktur',
                    set_={
                        'alamat': stmt.excluded.alamat,
                        'lat': stmt.excluded.lat,
                        'lon': stmt.excluded.lon,
                        'geo_strategy_id': stmt.excluded.geo_strategy_id,
                        'geo_status_id': stmt.excluded.geo_status_id,
                        'jenis_sarana_id': stmt.excluded.jenis_sarana_id,
                        'updated_at': select(text("NOW()")).scalar_subquery()
                    }
                )

                await session.execute(stmt)

            # Simpan seluruh perubahan ke Database
            await session.commit()
            log.info("✅ BINGO! 100% Data berhasil dimuat ke Supabase!")

        except Exception as e:
            await session.rollback()
            log.error(f"❌ TERJADI KESALAHAN SAAT INSERT: {str(e)}")

        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(load_data_to_db())
