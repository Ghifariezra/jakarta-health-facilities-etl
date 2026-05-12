# File: core/models.py

from sqlalchemy import Column, String, Float, SmallInteger, ForeignKey, DateTime, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Skema database yang digunakan
SCHEMA_NAME = 'infrastruktur_jakarta'

# ============================================================
#  1. WILAYAH
# ============================================================


class Wilayah(Base):
    __tablename__ = 'wilayah'
    __table_args__ = {'schema': SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    nama_wilayah = Column(String(150), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)

    # Relasi
    kecamatans = relationship(
        "Kecamatan", back_populates="wilayah", cascade="all, delete")

# ============================================================
#  2. KECAMATAN
# ============================================================


class Kecamatan(Base):
    __tablename__ = 'kecamatan'
    __table_args__ = (
        UniqueConstraint('wilayah_id', 'nama_kecamatan', name='uq_kecamatan'),
        {'schema': SCHEMA_NAME}
    )

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    wilayah_id = Column(UUID(as_uuid=True), ForeignKey(
        f'{SCHEMA_NAME}.wilayah.id', onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    nama_kecamatan = Column(String(150), nullable=False)
    created_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)

    # Relasi
    wilayah = relationship("Wilayah", back_populates="kecamatans")
    kelurahans = relationship(
        "Kelurahan", back_populates="kecamatan", cascade="all, delete")

# ============================================================
#  3. KELURAHAN
# ============================================================


class Kelurahan(Base):
    __tablename__ = 'kelurahan'
    __table_args__ = (
        UniqueConstraint('kecamatan_id', 'nama_kelurahan',
                         name='uq_kelurahan'),
        {'schema': SCHEMA_NAME}
    )

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    kecamatan_id = Column(UUID(as_uuid=True), ForeignKey(
        f'{SCHEMA_NAME}.kecamatan.id', onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    nama_kelurahan = Column(String(150), nullable=False)
    created_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)

    # Relasi
    kecamatan = relationship("Kecamatan", back_populates="kelurahans")
    infrastrukturs = relationship("Infrastruktur", back_populates="kelurahan")

# ============================================================
#  4. JENIS_SARANA
# ============================================================


class JenisSarana(Base):
    __tablename__ = 'jenis_sarana'
    __table_args__ = {'schema': SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    nama_jenis = Column(String(200), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)

    # Relasi
    infrastrukturs = relationship(
        "Infrastruktur", back_populates="jenis_sarana")

# ============================================================
#  5. GEO_STRATEGY
# ============================================================


class GeoStrategy(Base):
    __tablename__ = 'geo_strategy'
    __table_args__ = {'schema': SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    nama_strategy = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)

    # Relasi
    infrastrukturs = relationship(
        "Infrastruktur", back_populates="geo_strategy")

# ============================================================
#  6. GEO_STATUS
# ============================================================


class GeoStatus(Base):
    __tablename__ = 'geo_status'
    __table_args__ = {'schema': SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    nama_status = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)

    # Relasi
    infrastrukturs = relationship("Infrastruktur", back_populates="geo_status")

# ============================================================
#  7. INFRASTRUKTUR (Fact Table)
# ============================================================


class Infrastruktur(Base):
    __tablename__ = 'infrastruktur'
    __table_args__ = (
        UniqueConstraint('nama_infrastruktur', 'kelurahan_id',
                         'periode_data', name='uq_infrastruktur'),
        {'schema': SCHEMA_NAME}
    )

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    periode_data = Column(SmallInteger, nullable=False)

    # Foreign Keys
    kelurahan_id = Column(UUID(as_uuid=True), ForeignKey(
        f'{SCHEMA_NAME}.kelurahan.id', onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    jenis_sarana_id = Column(UUID(as_uuid=True), ForeignKey(
        f'{SCHEMA_NAME}.jenis_sarana.id', onupdate="CASCADE", ondelete="RESTRICT"), nullable=False)
    geo_strategy_id = Column(UUID(as_uuid=True), ForeignKey(
        f'{SCHEMA_NAME}.geo_strategy.id', onupdate="CASCADE", ondelete="SET NULL"), nullable=False)
    geo_status_id = Column(UUID(as_uuid=True), ForeignKey(
        f'{SCHEMA_NAME}.geo_status.id', onupdate="CASCADE", ondelete="SET NULL"), nullable=False)

    # Detail Info
    nama_infrastruktur = Column(String(255), nullable=False)
    alamat = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    created_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=text("NOW()"), nullable=False)

    # Relasi balik ke Lookup Tables
    kelurahan = relationship("Kelurahan", back_populates="infrastrukturs")
    jenis_sarana = relationship("JenisSarana", back_populates="infrastrukturs")
    geo_strategy = relationship("GeoStrategy", back_populates="infrastrukturs")
    geo_status = relationship("GeoStatus", back_populates="infrastrukturs")
