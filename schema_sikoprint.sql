-- ============================================================
-- SKEMA DATABASE SI-KOPRINT UNTUK POSTGRESQL (pgAdmin 4)
-- Jalankan script ini di Query Tool pada database: sikoprint_db
-- ============================================================

DROP TABLE IF EXISTS detail_atk CASCADE;
DROP TABLE IF EXISTS booking_print CASCADE;
DROP TABLE IF EXISTS pesanan CASCADE;
DROP TABLE IF EXISTS barang CASCADE;
DROP TABLE IF EXISTS customer CASCADE;
DROP TABLE IF EXISTS pegawai CASCADE;

-- 1. Tabel Pegawai
CREATE TABLE pegawai (
    id_pegawai    SERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password      VARCHAR(64) NOT NULL,
    nama_pegawai  VARCHAR(64) NOT NULL
);

-- 2. Tabel Costumer
CREATE TABLE customer (
    id_customer    SERIAL PRIMARY KEY,
    username       VARCHAR(64) NOT NULL UNIQUE,
    password       VARCHAR(64) NOT NULL,
    nama_customer  VARCHAR(64) NOT NULL,
    no_telepon     CHAR(13) NOT NULL
                   CHECK (TRIM(no_telepon) ~ '^08[0-9]{8,11}$')
);

-- 3. Tabel Katalog & Stok Barang ATK
CREATE TABLE barang (
    id_barang      SERIAL PRIMARY KEY,
    nama_barang    VARCHAR(64) NOT NULL,
    harga_satuan   NUMERIC(12,2) NOT NULL
                   CHECK (harga_satuan >= 500 AND harga_satuan <= 100000000),
    stok_tersedia  INTEGER NOT NULL
                   CHECK (stok_tersedia >= 0 AND stok_tersedia <= 100000)
);

-- 4. Tabel Pesanan
CREATE TABLE pesanan (
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

-- 5. Tabel Booking Print
CREATE TABLE booking_print (
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

-- 6. Tabel Detail Pembelian Barang ATK
CREATE TABLE detail_atk (
    id_detail     SERIAL PRIMARY KEY,
    kode_booking  VARCHAR(32) NOT NULL UNIQUE
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

-- ============================================================
-- DATA AWAL PEGAWAI & KATALOG BARANG ATK
-- ============================================================
INSERT INTO pegawai (username, password, nama_pegawai)
VALUES (
    'sheila',
    '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9',
    'Sheila Aishameglio Duta Chiara'
)
ON CONFLICT (username) DO NOTHING;

INSERT INTO barang (nama_barang, harga_satuan, stok_tersedia)
VALUES
    ('Pulpen Snowman Black', 3500.00, 45),
    ('Buku Tulis Campus 36', 6000.00, 20),
    ('Kertas HVS A4 75gr', 48000.00, 12);
