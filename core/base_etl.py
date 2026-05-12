# core/base_etl.py
import time
from abc import abstractmethod
from core.singleton import BaseSingleton

# Tidak perlu import ABC lagi — sudah tergabung di dalam BaseSingleton


class BaseETL(BaseSingleton):
    def __init__(self):
        self.hasil_ekstrak: list = []

    @abstractmethod
    async def extract_data(self, total_pages: int) -> None:
        """Tarik data dari sumber."""

    @abstractmethod
    def transform_data(self) -> None:
        """Bersihkan dan bentuk ulang data."""

    @abstractmethod
    def load_data(self) -> None:
        """Simpan data ke tujuan akhir."""

    async def run_pipeline(self, total_pages: int = 5) -> None:
        print(f"\n🚀 [{self.__class__.__name__}] Memulai Pipeline ETL...")
        start_time = time.perf_counter()

        try:
            await self.extract_data(total_pages)
            self.transform_data()
            self.load_data()
        except Exception as e:
            print(f"❌ [{self.__class__.__name__}] Pipeline gagal: {e}")
            raise
        finally:
            elapsed = time.perf_counter() - start_time
            print(
                f"✅ [{self.__class__.__name__}] Pipeline selesai "
                f"dalam {elapsed:.2f} detik.\n"
            )
