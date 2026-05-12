# File: core/google_maps.py

import os
import asyncio
import aiohttp
from dotenv import load_dotenv
from core.singleton import BaseSingleton
from core.logger import get_logger

load_dotenv()

log = get_logger("google_api")

class GoogleMapsClient(BaseSingleton):
    """
    Klien Asinkron untuk berinteraksi dengan Google Maps Platform.
    Mendukung Places API (New) dan Geocoding API (Classic).
    """

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not self.api_key:
            log.error(
                "❌ GOOGLE_MAPS_API_KEY tidak ditemukan di environment variables (.env)!")

        # API Endpoints
        self.places_url = "https://places.googleapis.com/v1/places:searchText"
        self.geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"

        # Pengaturan Retry
        self.max_retries = 3
        self.retry_delay = 2  # detik

    @property
    def _places_headers(self) -> dict:
        """Mengembalikan headers standar untuk Places API (New)."""
        return {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "places.location,places.addressComponents,places.formattedAddress",
            "Content-Type": "application/json"
        }

    # =========================================================================
    # 1. PLACES API (Mencari berdasarkan Nama Bisnis)
    # =========================================================================
    async def search_place(self, session: aiohttp.ClientSession, query: str) -> dict | None:
        """Mencari tempat berdasarkan Teks Query dengan Places API (New)."""
        if not self.api_key:
            return None

        payload = {"textQuery": query, "languageCode": "id"}

        for attempt in range(self.max_retries):
            try:
                async with session.post(self.places_url, headers=self._places_headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        places = data.get("places", [])
                        if places:
                            return self._parse_place_data(places[0])
                        return None
                    elif resp.status == 429:
                        log.warning(
                            f"⚠️ [Places] Rate Limit 429 tersentuh. Istirahat...")
                        await asyncio.sleep(self.retry_delay * 2)
                        continue
                    elif resp.status >= 500:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    else:
                        return None
            except asyncio.TimeoutError:
                await asyncio.sleep(self.retry_delay)
            except Exception as e:
                return None
        return None

    # =========================================================================
    # 2. GEOCODING API (Mencari berdasarkan Teks Alamat)
    # =========================================================================
    async def geocode_address(self, session: aiohttp.ClientSession, address: str) -> dict | None:
        """Mencari koordinat dan komponen alamat menggunakan Geocoding API."""
        if not self.api_key:
            return None

        query = f"{address}, Indonesia"
        params = {
            "address": query,
            "key": self.api_key,
            "language": "id"
        }

        for attempt in range(self.max_retries):
            try:
                async with session.get(self.geocode_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('status') == 'OK' and len(data.get('results', [])) > 0:
                            return self._parse_geocode_data(data['results'][0])
                        # Jika OVER_QUERY_LIMIT, trigger retry
                        elif data.get('status') == 'OVER_QUERY_LIMIT':
                            log.warning(
                                f"⚠️ [Geocode] Over Query Limit. Istirahat sejenak...")
                            await asyncio.sleep(self.retry_delay * 2)
                            continue
                        return None
                    elif resp.status >= 500:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    else:
                        return None
            except asyncio.TimeoutError:
                await asyncio.sleep(self.retry_delay)
            except Exception as e:
                return None
        return None

    # =========================================================================
    # DATA PARSERS (Pemecah JSON)
    # =========================================================================
    def _parse_place_data(self, place: dict) -> dict:
        """Parser untuk balasan Places API (New)"""
        loc = place.get("location", {})
        kec, kel = self._extract_administrative_areas(
            place.get("addressComponents", []), source="places")
        return {
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "kecamatan": kec,
            "kelurahan": kel,
            "formatted_address": place.get("formattedAddress")
        }

    def _parse_geocode_data(self, result: dict) -> dict:
        """Parser untuk balasan Geocoding API"""
        loc = result.get("geometry", {}).get("location", {})
        kec, kel = self._extract_administrative_areas(
            result.get("address_components", []), source="geocode")
        return {
            "lat": loc.get("lat"),
            "lon": loc.get("lng"),
            "kecamatan": kec,
            "kelurahan": kel,
            "formatted_address": result.get("formatted_address")
        }

    def _extract_administrative_areas(self, components: list, source: str) -> tuple[str | None, str | None]:
        """Ekstrak Kelurahan dan Kecamatan secara universal untuk kedua API"""
        kecamatan, kelurahan = None, None
        text_key = "longText" if source == "places" else "long_name"

        for comp in components:
            types = comp.get("types", [])
            name = comp.get(text_key, "").strip()

            # Kecamatan: level 3 atau neighborhood yang mengandung "Kecamatan"
            if "administrative_area_level_3" in types:
                kecamatan = name

            # Kelurahan: coba semua kemungkinan type yang Google pakai untuk Jakarta
            elif "administrative_area_level_4" in types:
                kelurahan = name
            elif "sublocality_level_1" in types and not kelurahan:
                kelurahan = name
            elif "sublocality" in types and not kelurahan:
                kelurahan = name
            elif "neighborhood" in types and not kelurahan:
                kelurahan = name

        # Normalisasi
        if kecamatan:
            kecamatan = kecamatan.replace("Kecamatan ", "").replace(
                "Kec. ", "").strip().title()
        if kelurahan:
            kelurahan = (kelurahan
                        .replace("Kelurahan ", "").replace("Kel. ", "")
                        .replace("Desa ", "").strip().title())

        return kecamatan, kelurahan

    # =========================================================================
    # REVERSE GEOCODING (Mencari Detail Wilayah Berdasarkan Koordinat)
    # =========================================================================
    async def reverse_geocode(self, session: aiohttp.ClientSession, lat: float, lon: float) -> dict | None:
        """Reverse geocode dari koordinat → dapat kelurahan/kecamatan lebih akurat."""
        if not self.api_key:
            return None

        params = {
            "latlng": f"{lat},{lon}",
            "key": self.api_key,
            "language": "id",
            # Batasi hasil pada wilayah administratif agar tidak terlalu "berisik"
            "result_type": "sublocality|neighborhood|administrative_area_level_4|administrative_area_level_3",
        }

        for attempt in range(self.max_retries):
            try:
                async with session.get(self.geocode_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('status') == 'OK' and data.get('results'):
                            # Ambil hasil paling relevan (biasanya index 0)
                            return self._parse_geocode_data(data['results'][0])
                        elif data.get('status') == 'OVER_QUERY_LIMIT':
                            await asyncio.sleep(self.retry_delay * 2)
                            continue
                        return None
                    elif resp.status >= 500:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    else:
                        return None
            except asyncio.TimeoutError:
                await asyncio.sleep(self.retry_delay)
            except Exception:
                return None
        return None
