# ETL Pipeline - Sarana Kesehatan DKI Jakarta

Proyek ini adalah pipeline **ETL (Extract, Transform, Load)** berbasis Python yang dirancang untuk mengumpulkan, membersihkan, memperkaya (enrich via geocoding), dan menyimpan data Sarana Kesehatan di Provinsi DKI Jakarta ke dalam database (Supabase PostgreSQL).

## ✨ Fitur Utama

- **Asynchronous HTTP Requests**: Ekstraksi data berkecepatan tinggi dari API Satu Data Jakarta menggunakan `aiohttp` dan `asyncio`.
- **Multi-Layer Geocoding**:
  - Transformasi mandiri menggunakan Regex.
  - OpenStreetMap (Nominatim) untuk pencarian berbasis Open Source.
  - Google Maps Places & Geocoding API sebagai *fallback* presisi tinggi.
- **Dukungan Proxy**: Rotasi Premium Proxy otomatis untuk menghindari limitasi *rate-limiting* API Geocoding pihak ketiga.
- **Robust Asynchronous Database Loader**: Skema *Star/Snowflake* Database menggunakan ORM SQLAlchemy (dengan *driver* `asyncpg`) untuk proses loading yang sangat cepat & *non-blocking* ke Supabase.
- **Pola Arsitektur yang Bersih**: Menggunakan OOP dan pattern *Singleton* untuk koneksi DB dan HTTP Client agar alokasi *resource* lebih efisien.
- **Rotasi Log Terpusat**: Logging terstruktur dengan fitur *auto-rotation* (menyimpan backup log otomatis) untuk memantau berjalannya *pipeline* tanpa membebani disk space.

## 📂 Struktur Proyek

```text
sarana-kesehatan/
├── core/                   # Modul utama sistem (inti)
│   ├── base_etl.py         # Base / Abstract class ETL
│   ├── http_client.py      # Async HTTP client (Satu Data Jakarta request)
│   ├── google_maps.py      # Wrapper untuk API Google Maps
│   ├── nominatim.py        # Wrapper untuk Nominatim OSM
│   ├── logger.py           # Konfigurasi custom rotating logger
│   ├── models.py           # Skema Tabel Database (SQLAlchemy)
│   └── singleton.py        # Metaclass Singleton Pattern
├── data/
│   ├── raw/                # Data mentah setelah ditarik dari API
│   ├── processed/          # Data setelah melewati Transform & Geocode
│   └── proxy/              # Konfigurasi / daftar Proxy 
├── services/               # Layanan atau task spesifik
│   ├── loaders.py          # Logika Database insertion (Supabase Loader)
│   └── transform/          # Script khusus untuk Data Enrichment (Geo, Patch)
│       ├── openstreet_nominatim.py 
│       ├── final_patch.py
│       └── google-maps/    # Fallback pencari alamat
├── utils/                  # Fungsi helper/utilities pendukung (misal progress_bar)
├── main.py                 # Entry point untuk fase Ekstraksi awal
├── requirements.txt        # Daftar librari Python
└── .env.example            # Contoh Environment Variables
```

## ⚙️ Persyaratan Sistem

- Python 3.10+
- PostgreSQL Database Cloud (contoh: Supabase)
- Premium HTTP Proxy (Opsional, sangat disarankan untuk Nominatim)
- Google Maps API Key (Untuk fitur fallback geocoding)

## 🚀 Setup & Instalasi

1. **Clone repository ini & buat Virtual Environment (Opsional)**
    ```bash
    python -m venv venv
    venv\Scripts\activate   # (Untuk Windows)
    # source venv/bin/activate # (Untuk Linux/Mac)
    ```

2. **Jalankan script instalasi atau install manual**
    Menggunakan powershell script:
    ```powershell
    .\scripts\install.ps1
    ```
    Atau install dependensi secara manual:
    ```bash
    pip install -r requirements.txt
    ```

3. **Konfigurasi Environment Variable**
    Salin file `.env.example` ke `.env` lalu isikan kredensial database dan API key Anda.
    ```bash
    cp .env.example .env
    ```

## 🛠️ Cara Penggunaan

Proyek ini telah dibagi menjadi *task* modular:

1. **Ekstraksi Data Awal**
   Menarik semua baris data dari API dan menyimpannya di file CSV (di dalam `data/raw`).
   ```bash
   python main.py
   ```

2. **Data Enrichment (Geocoding - OSM)**
   Menambahkan latitude, longitude, kecamatan, dan kelurahan via OpenStreetMap Nominatim.
   ```bash
   python services/transform/openstreet_nominatim.py
   ```

3. **Data Enrichment (Geocoding - Fallback Google Maps)**
   Mencari sisa baris yang masih belum ketemu koordinat / alamatnya via Google Places & Geocode API.
   ```bash
   python services/transform/google-maps/google_places.py
   python services/transform/google-maps/google_geocode.py
   ```

4. **Final Patch**
   Injeksi / perbaikan paksa tahap akhir sebelum data dikirim ke Database untuk mengatasi anomali seperti kasus area Pantai Indah Kapuk (PIK).
   ```bash
   python services/transform/final_patch.py
   ```

5. **Loading Data ke PostgreSQL (Supabase)**
   Mensinkronkan `sarana_kesehatan_enriched_final.csv` langsung ke entitas skema *Fact Table* dan *Dimension Table* milik kita.
   ```bash
   python services/loaders.py
   ```

## 📝 Logging

Log aplikasi akan dicetak di konsol dan juga dicatat ke folder `logs/etl.log`. Log sudah dikonfigurasi untuk auto-rotate agar file tetap rapi.
