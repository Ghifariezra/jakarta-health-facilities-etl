import asyncio
import itertools
import os

import pandas as pd
from dotenv import load_dotenv

from core.base_etl import BaseETL
from core.http_client import AsyncHTTPClient

load_dotenv()

class SaranaKesehatanETL(BaseETL):
    def __init__(self):
        super().__init__()
        print("[SaranaKesehatanETL] Diinisialisasi.")

        self.http_client = AsyncHTTPClient(
            timeout_seconds=30,
            max_concurrent=5,   # Sesuaikan dengan toleransi server
            max_retries=3,
        )

        base_url = os.getenv("BASE_URL_JAKARTA")
        self.api_url = f"{base_url}/detail"
        self.kategori = "dataset"
        self.page_url = "data-keberadaan-sarana-kesehatan-di-provinsi-dki-jakarta"

    # --- FASE 1: EXTRACT ---
    async def extract_data(self, total_pages: int) -> None:
        print(f"Memulai ekstraksi {total_pages} halaman...")

        payloads = [
            {
                "kategori": self.kategori,
                "page_url": self.page_url,
                "data_no": page,
                "per_page": 100,
            }
            for page in range(1, total_pages + 1)
        ]

        raw_results = await self.http_client.fetch_all_post(self.api_url, payloads)

        # Filter None, ambil "filedata", ratakan
        file_data_lists = (
            res["filedata"]
            for res in raw_results
            if isinstance(res, dict) and res.get("filedata")
        )
        self.hasil_ekstrak.extend(
            itertools.chain.from_iterable(file_data_lists))

        print(f"Ekstraksi selesai. Total baris: {len(self.hasil_ekstrak)}")

    # --- FASE 2: TRANSFORM ---
    def transform_data(self) -> None:
        print("Memulai transformasi...")

        if not self.hasil_ekstrak:
            print("Tidak ada data untuk ditransformasi.")
            return

        df = pd.DataFrame(self.hasil_ekstrak)

        if "kelurahan" in df.columns:
            df["kelurahan"] = df["kelurahan"].fillna("N/A")

        # Simpan data mentah ke CSV untuk referensi (opsional)
        raw_data = "data/raw/sarana_kesehatan_bersih.csv"
        os.makedirs(os.path.dirname(raw_data), exist_ok=True)
        df.to_csv(raw_data, index=False)
        print(f"Raw data disimpan di: {raw_data}")

        # # Transformasi Data: mengisi kolom "kelurahan" yang kosong dengan "N/A" dan menyimpan koordinat yang ditemukan
        # missingData = df[(df['kecamatan'].isna()) | (
        #     df['kelurahan'].isna()) | (df['alamat'].isna())]
        
        print("Transformasi selesai.")

    # --- FASE 3: LOAD ---
    def load_data(self) -> None:
        print("Fase Load: (belum diimplementasikan)")

if __name__ == "__main__":
    etl = SaranaKesehatanETL()
    asyncio.run(etl.run_pipeline(total_pages=84))