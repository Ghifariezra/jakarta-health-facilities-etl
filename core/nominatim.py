# File: core/nominatim.py

import os
import re
import asyncio
import aiohttp
from core.singleton import BaseSingleton
from core.logger import get_logger

log = get_logger("nominatim")


class NominatimClient(BaseSingleton):
    def __init__(self):
        self.base_url = os.getenv(
            "BASE_URL_NOMINATIM", "https://nominatim.openstreetmap.org/search")
        self.headers = {
            "User-Agent": "SaranaKesehatanETL/1.0 (riset-sarana-kesehatan-dki; ucupnurin444@gmail.com)",
            "Accept": "application/json",
            "Accept-Language": "id",
        }
        self._cache = {}
        log.info(
            "[NominatimClient] Engine Geocoding siap dengan Proxy Mode (Tanpa Limit).")

    async def _fetch(
        self, session: aiohttp.ClientSession, params: dict, label: str, proxy: dict = None
    ) -> list | None:
        kwargs = {"params": params, "headers": self.headers}
        if proxy:
            kwargs["proxy"] = proxy["url"]
            kwargs["proxy_auth"] = proxy["auth"]

        try:
            async with session.get(self.base_url, **kwargs) as resp:
                if resp.status == 429:
                    log.warning(
                        f"    ⚠️ Rate limited via Proxy! Tunggu 5 detik...")
                    await asyncio.sleep(5)
                    return None
                if resp.status != 200:
                    log.error(f"    ❌ HTTP Error {resp.status} via Proxy")
                    return None
                return await resp.json()
        except asyncio.TimeoutError:
            log.warning(f"    ⏳ Timeout [{label}] via Proxy")
            return None
        except Exception as e:
            log.error(f"    ❌ Error [{label}] via Proxy: {type(e).__name__}")
            return None

    @staticmethod
    def clean_address(alamat: str) -> str:
        noise = r",?\s*(Desa|Kelurahan|Kec\.?|RT\.?\s*\d+|RW\.?\s*\d+)\s*$"
        return re.sub(noise, "", alamat, flags=re.IGNORECASE).strip().rstrip(",").strip()

    @staticmethod
    def extract_street_name(alamat_bersih: str) -> str:
        return re.sub(r",?\s*No\.?\s*\d+.*$", "", alamat_bersih, flags=re.IGNORECASE).strip()

    @staticmethod
    def extract_kelurahan(address_obj: dict) -> str:
        priority_keys = ["suburb", "village",
                         "neighbourhood", "quarter", "city_district"]
        for key in priority_keys:
            if address_obj.get(key):
                return address_obj[key]
        return "TIDAK DITEMUKAN"

    # --- PERBAIKAN: Tambah parameter kelurahan_regex ---
    async def geocode_alamat(
        self, session: aiohttp.ClientSession, alamat: str, kecamatan: str, kota: str,
        kelurahan_regex: str = "", proxy: dict = None
    ) -> dict:

        alamat_bersih = self.clean_address(alamat)
        nama_jalan = self.extract_street_name(alamat_bersih)

        _kec = str(kecamatan).strip() if kecamatan else ""
        has_kecamatan = bool(_kec and _kec.lower() not in [
                             "n/a", "none", "null", "tidak diketahui", "nan", ""])
        kecamatan_clean = _kec.title() if has_kecamatan else ""

        # Bersihkan kelurahan hasil regex
        _kel = str(kelurahan_regex).strip()
        has_kelurahan = bool(_kel and _kel.lower() not in [
                             "n/a", "none", "null", "tidak diketahui", "nan", ""])
        kelurahan_clean = _kel.title() if has_kelurahan else ""

        # CEK CACHE
        cache_key = f"{alamat_bersih}_{kecamatan_clean}_{kelurahan_clean}_{kota}"
        if cache_key in self._cache:
            log.info("  ⚡ Menggunakan data dari CACHE memori (0 detik!)")
            return self._cache[cache_key]

        base_params = {
            "format": "jsonv2", "limit": 1, "addressdetails": 1, "countrycodes": "id"
        }

        data = None
        strategy = ""

        # S1: Structured (Jalan + Nomor + Kota)
        if alamat_bersih:
            data = await self._fetch(session, {**base_params, "street": alamat_bersih, "city": kota, "country": "Indonesia"}, "S1", proxy)
            if data:
                strategy = "S1 (Jalan+No)"

        # S2: Structured (Jalan Saja + Kota)
        if not data and nama_jalan and (nama_jalan != alamat_bersih):
            data = await self._fetch(session, {**base_params, "street": nama_jalan, "city": kota, "country": "Indonesia"}, "S2", proxy)
            if data:
                strategy = "S2 (Jalan)"

        # S3: Free-form (Jalan Saja + Kota)
        if not data and nama_jalan:
            q3 = f"{nama_jalan}, {kota}, DKI Jakarta, Indonesia"
            data = await self._fetch(session, {**base_params, "q": q3}, "S3", proxy)
            if data:
                strategy = "S3 (Free-form Jalan)"

        # S4: Structured (Kecamatan + Kota)
        if not data and has_kecamatan:
            data = await self._fetch(session, {**base_params, "county": kecamatan_clean, "city": kota, "country": "Indonesia"}, "S4", proxy)
            if data:
                strategy = "S4 (Structured Kec)"

        # S5: Free-form (Kecamatan + Kota)
        if not data and has_kecamatan:
            q5 = f"{kecamatan_clean}, {kota}, DKI Jakarta, Indonesia"
            data = await self._fetch(session, {**base_params, "q": q5}, "S5", proxy)
            if data:
                strategy = "S5 (Free-form Kec)"

        # --- OPTIMASI BARU: S6 & S7 MENGGUNAKAN KELURAHAN REGEX ---
        # S6: Structured (Kelurahan + Kota)
        if not data and has_kelurahan:
            # Di OSM, kelurahan biasanya masuk ke 'suburb'
            data = await self._fetch(session, {**base_params, "suburb": kelurahan_clean, "city": kota, "country": "Indonesia"}, "S6", proxy)
            if data:
                strategy = "S6 (Structured Kel)"

        # S7: Free-form (Kelurahan + Kota) - Sangat Toleran
        if not data and has_kelurahan:
            q7 = f"{kelurahan_clean}, {kota}, Indonesia"
            data = await self._fetch(session, {**base_params, "q": q7}, "S7", proxy)
            if data:
                strategy = "S7 (Free-form Kel)"

        result = {
            "status": "FAILED", "kelurahan": "TIDAK DITEMUKAN",
            "lat": None, "lon": None, "display_name": None, "strategy": None
        }

        if data and len(data) > 0:
            best = data[0]
            result.update({
                "status": "SUCCESS",
                "kelurahan": self.extract_kelurahan(best.get("address", {})),
                "lat": best.get("lat"),
                "lon": best.get("lon"),
                "display_name": best.get("display_name", "-"),
                "strategy": strategy,
            })

        self._cache[cache_key] = result
        return result
