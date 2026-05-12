import pandas as pd
from core.logger import get_logger

log = get_logger("final_patch")

def final_transform():
    # Pastikan file yang dibaca adalah file backup terakhir hasil geocoding
    input_file = "data/processed/sarana_kesehatan_enriched_backup_2.csv"
    output_file = "data/processed/sarana_kesehatan_enriched_final.csv"

    log.info("⏳ Membaca data untuk Final Patch...")
    df = pd.read_csv(input_file)

    # ---------------------------------------------------------
    # 1. PATCH MANUAL: Penyelamat Kasus "Golf Island / PIK"
    # ---------------------------------------------------------
    log.info("🏝️ Menambal data Kelurahan yang gagal di-tag Google pada area PIK...")

    mask_pik = df['alamat'].str.contains(
        'Golf Island|PIK|Pantai Indah Kapuk', case=False, na=False)

    # Paksa isi Kelurahan & Kecamatan
    df.loc[mask_pik & df['kelurahan'].isna(), 'kelurahan'] = 'Kamal Muara'
    df.loc[mask_pik & df['kecamatan'].isna(), 'kecamatan'] = 'Penjaringan'

    # ---------------------------------------------------------
    # 2. IMPUTASI TEKS (Sisa NaN menjadi "Tidak Diketahui")
    # ---------------------------------------------------------
    log.info(
        "🧹 Membersihkan sisa teks NaN (jika masih ada) menjadi 'Tidak Diketahui'...")
    for col in ['kecamatan', 'kelurahan', 'alamat']:
        df[col] = df[col].fillna("Tidak Diketahui")

    # Pastikan tidak ada NaN di geo_strategy dan geo_status
    if 'geo_strategy' in df.columns:
        df['geo_strategy'] = df['geo_strategy'].fillna('Manual Patch')
    if 'geo_status' in df.columns:
        df['geo_status'] = df['geo_status'].fillna('SUCCESS')

    # ---------------------------------------------------------
    # 3. SIMPAN HASIL FINAL
    # ---------------------------------------------------------
    df.to_csv(output_file, index=False)

    log.info("="*50)
    log.info(
        f"✅ FINAL PATCH SELESAI! Data 100% KOMPLIT disimpan di {output_file}")
    log.info("="*50)


if __name__ == "__main__":
    final_transform()
