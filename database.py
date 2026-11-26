import os
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema_sikoprint.sql")


def muat_env(path_env=ENV_PATH):
    """Memuat variabel konfigurasi dari file .env ke os.environ jika tersedia."""
    try:
        if not os.path.isfile(path_env):
            return False
        with open(path_env, "r", encoding="utf-8") as berkas:
            for baris in berkas:
                teks = baris.strip()
                if not teks or teks.startswith("#") or "=" not in teks:
                    continue
                kunci, nilai = teks.split("=", 1)
                kunci = kunci.strip()
                nilai = nilai.strip().strip('"').strip("'")
                if kunci:
                    os.environ.setdefault(kunci, nilai)
        return True
    except OSError:
        return False


muat_env()

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "sikoprint_db"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "Teknik4"),
}

DDL_SKEMA = """
CREATE TABLE IF NOT EXISTS pegawai (
    id_pegawai    SERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password      VARCHAR(64) NOT NULL,
    nama_pegawai  VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS customer (
    id_customer    SERIAL PRIMARY KEY,
    username       VARCHAR(64) NOT NULL UNIQUE,
    password       VARCHAR(64) NOT NULL,
    nama_customer  VARCHAR(64) NOT NULL,
    no_telepon     CHAR(13) NOT NULL
                   CHECK (TRIM(no_telepon) ~ '^08[0-9]{8,11}$')
);

CREATE TABLE IF NOT EXISTS barang (
    id_barang      SERIAL PRIMARY KEY,
    nama_barang    VARCHAR(64) NOT NULL,
    harga_satuan   NUMERIC(12,2) NOT NULL
                   CHECK (harga_satuan >= 500 AND harga_satuan <= 100000000),
    stok_tersedia  INTEGER NOT NULL
                   CHECK (stok_tersedia >= 0 AND stok_tersedia <= 100000)
);

CREATE TABLE IF NOT EXISTS pesanan (
    urutan          SERIAL,
    kode_booking    VARCHAR(32) PRIMARY KEY,
    id_customer     INTEGER NOT NULL
                    REFERENCES customer(id_customer)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    nama_pemesan    VARCHAR(64) NOT NULL,
    tanggal_pesan   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    jenis_pesanan   VARCHAR(16) NOT NULL
                    CHECK (jenis_pesanan IN ('PRINT', 'ATK')),
    total_biaya     INTEGER NOT NULL
                    CHECK (total_biaya >= 0),
    status_pesanan  VARCHAR(20) NOT NULL DEFAULT 'Diproses'
                    CHECK (status_pesanan IN ('Diproses', 'Selesai', 'Tuntas'))
);

CREATE TABLE IF NOT EXISTS booking_print (
    id_booking        VARCHAR(32) PRIMARY KEY,
    kode_booking      VARCHAR(32) NOT NULL
                      REFERENCES pesanan(kode_booking)
                      ON UPDATE CASCADE ON DELETE CASCADE,
    nama_link_file    VARCHAR(255) NOT NULL,
    ukuran_kertas     VARCHAR(10) NOT NULL
                      CHECK (ukuran_kertas IN ('A4', 'F4', 'A3')),
    pilihan_warna     VARCHAR(10) NOT NULL
                      CHECK (pilihan_warna IN ('BW', 'Color')),
    tipe_cetak        VARCHAR(15) NOT NULL
                      CHECK (tipe_cetak IN ('1 Sisi', '2 Sisi')),
    jumlah_lembar     INTEGER NOT NULL
                      CHECK (jumlah_lembar >= 1 AND jumlah_lembar <= 1000),
    jumlah_eksemplar  INTEGER NOT NULL
                      CHECK (jumlah_eksemplar >= 1 AND jumlah_eksemplar <= 100),
    opsi_jilid        VARCHAR(20) NOT NULL
                      CHECK (opsi_jilid IN ('Tanpa', 'Lakban', 'Spiral')),
    subtotal_cetak    INTEGER NOT NULL
                      CHECK (subtotal_cetak >= 500)
);

CREATE TABLE IF NOT EXISTS detail_atk (
    id_detail     SERIAL PRIMARY KEY,
    kode_booking  VARCHAR(32) NOT NULL
                  REFERENCES pesanan(kode_booking)
                  ON UPDATE CASCADE ON DELETE CASCADE,
    id_barang     INTEGER NOT NULL
                  REFERENCES barang(id_barang)
                  ON UPDATE CASCADE ON DELETE RESTRICT,
    nama_barang   VARCHAR(64) NOT NULL,
    harga_satuan  NUMERIC(12,2) NOT NULL
                  CHECK (harga_satuan >= 500),
    jumlah        INTEGER NOT NULL
                  CHECK (jumlah >= 1),
    subtotal      INTEGER NOT NULL
                  CHECK (subtotal >= 500)
);
"""


def koneksi():
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except psycopg2.OperationalError as err:
        raise ConnectionError(
            "Gagal terhubung ke PostgreSQL. Pastikan service PostgreSQL aktif, "
            "database 'sikoprint_db' sudah dibuat di pgAdmin, dan konfigurasi di "
            f"database.py sudah sesuai.\nDetail error: {err}"
        ) from err


def hash_password(teks):
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


def _skema_lama_terdeteksi(cur):
    """Mendeteksi apakah struktur tabel lama masih ada di database."""
    cur.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('pegawai', 'customer', 'barang', 'pesanan')
        """
    )
    rows = cur.fetchall()
    if not rows:
        return False
    kolom = {(r["table_name"], r["column_name"]): r["data_type"] for r in rows}
    if ("customer", "id_customer") not in kolom:
        return True
    if ("pegawai", "id_pegawai") not in kolom:
        return True
    if kolom.get(("barang", "id_barang")) != "integer":
        return True
    if ("pesanan", "id_customer") not in kolom:
        return True
    return False


def _selaraskan_kolom_telepon(cur):
    """Menyelaraskan kolom no_telepon menjadi CHAR(13) tanpa menghapus data."""
    cur.execute(
        """
        SELECT character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'customer'
          AND column_name = 'no_telepon'
        """
    )
    info = cur.fetchone()
    if info and info["character_maximum_length"] == 12:
        cur.execute("ALTER TABLE customer DROP CONSTRAINT IF EXISTS customer_no_telepon_check")
        cur.execute("ALTER TABLE customer ALTER COLUMN no_telepon TYPE CHAR(13)")
        cur.execute(
            "ALTER TABLE customer ADD CONSTRAINT customer_no_telepon_check "
            "CHECK (TRIM(no_telepon) ~ '^08[0-9]{8,11}$')"
        )


def buat_tabel():
    conn = koneksi()
    try:
        with conn.cursor() as cur:
            if _skema_lama_terdeteksi(cur):
                print("[!] Terdeteksi struktur tabel lama pada database 'sikoprint_db'.")
                print("    Struktur tabel akan diperbarui sesuai skema terbaru.")
                while True:
                    try:
                        jawab = input("    Lanjutkan pembaruan tabel otomatis? [Y/T] : ").strip().upper()
                    except EOFError as err:
                        raise KeyboardInterrupt from err
                    if jawab == "Y":
                        cur.execute(
                            """
                            DROP TABLE IF EXISTS detail_atk CASCADE;
                            DROP TABLE IF EXISTS booking_print CASCADE;
                            DROP TABLE IF EXISTS pesanan CASCADE;
                            DROP TABLE IF EXISTS barang CASCADE;
                            DROP TABLE IF EXISTS customer CASCADE;
                            DROP TABLE IF EXISTS pegawai CASCADE;
                            """
                        )
                        break
                    elif jawab == "T":
                        raise RuntimeError(
                            f"Pembaruan tabel dibatalkan. Jalankan file '{SCHEMA_PATH}' "
                            "di Query Tool pgAdmin 4 terlebih dahulu sebelum menjalankan program."
                        )
                    else:
                        print("    [X] Input tidak valid. Ketik Y untuk Ya atau T untuk Tidak.")
            cur.execute(DDL_SKEMA)
            _selaraskan_kolom_telepon(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def isi_data_awal():
    conn = koneksi()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM pegawai")
            if cur.fetchone()["total"] == 0:
                cur.execute(
                    "INSERT INTO pegawai (username, password, nama_pegawai) "
                    "VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    ("rina", hash_password("admin123"), "Rina"),
                )
            cur.execute("SELECT COUNT(*) AS total FROM barang")
            if cur.fetchone()["total"] == 0:
                cur.executemany(
                    "INSERT INTO barang (nama_barang, harga_satuan, stok_tersedia) "
                    "VALUES (%s, %s, %s)",
                    [
                        ("Pulpen Snowman Black", 3500.00, 45),
                        ("Buku Tulis Campus 36", 6000.00, 20),
                        ("Kertas HVS A4 75gr", 48000.00, 12),
                    ],
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def siapkan_database():
    buat_tabel()
    isi_data_awal()
