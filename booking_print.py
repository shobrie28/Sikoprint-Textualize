import re
from urllib.parse import urlparse
import psycopg2
from database import koneksi
from tampilan import (garis, input_pilihan, input_angka, segarkan_halaman,
                      jeda_layar, konfirmasi, waktu_sekarang, _baca_input,
                      _proses_refresh_input, BatasRefreshError,
                      TOTAL_MAKSIMUM)
from tarif import (UKURAN, WARNA, TIPE, JILID, LABEL_WARNA, LABEL_TIPE,
                   LABEL_JILID, hitung_total_print)
from nota import buat_kode_booking, cetak_nota_print

MAKS_LEMBAR = 1000
MAKS_EKSEMPLAR = 100
EKSTENSI_FILE_DITOLAK = (
    ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".txt", ".zip", ".rar"
)
DOMAIN_DRIVE_VALID = ("drive.google.com", "docs.google.com")


def input_link_drive(prompt, render_ulang=None):
    """Memvalidasi bahwa input hanya berupa link Google Drive yang valid."""
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip().strip('"').strip("'")
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue

        if " " in isi:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Link Google Drive tidak boleh mengandung spasi."
            )
            continue

        if len(isi) > 255:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Panjang link Google Drive maksimal 255 karakter."
            )
            continue

        isi_lower = isi.lower()
        if any(isi_lower.endswith(eks) for eks in EKSTENSI_FILE_DITOLAK) and not isi_lower.startswith(("http://", "https://")):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Pengiriman dalam bentuk file tidak diperbolehkan. Masukkan link Google Drive."
            )
            continue

        if re.match(r"^[a-zA-Z]:\\", isi) or isi.startswith(("/", "\\", "~")):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Path file lokal tidak diperbolehkan. Masukkan link Google Drive."
            )
            continue

        if not isi_lower.startswith(("http://", "https://")):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Input harus berupa link Google Drive yang diawali https://drive.google.com/ atau https://docs.google.com/."
            )
            continue

        parsed = urlparse(isi)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        if host not in DOMAIN_DRIVE_VALID:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Link harus berasal dari Google Drive yaitu drive.google.com atau docs.google.com."
            )
            continue

        path_bersih = parsed.path.strip("/")
        if not path_bersih or len(path_bersih) < 5:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Link Google Drive belum lengkap. Masukkan tautan lengkap file atau folder."
            )
            continue

        return isi


def pilih_opsi(judul_opsi, daftar, render_dasar):
    def _render_opsi(pesan_error=None):
        render_dasar(pesan_error)
        print(judul_opsi)
        for nomor, (_, label) in enumerate(daftar, start=1):
            print(f"    [{nomor}] {label}")

    _render_opsi()
    pilihan = input_pilihan(
        f"    Pilihan [1-{len(daftar)}] : ",
        1,
        len(daftar),
        render_ulang=_render_opsi,
    )
    return daftar[pilihan - 1][0]


def simpan_booking_print(costumer, d):
    conn = koneksi()
    try:
        kode = buat_kode_booking(conn, "BOOK")
        with conn.cursor() as cur:
            cur.execute("CREATE SEQUENCE IF NOT EXISTS seq_booking_print START 1")
            cur.execute(
                "SELECT setval('seq_booking_print', "
                "GREATEST((SELECT COALESCE(MAX(CAST(SUBSTRING(id_booking FROM 4) AS INTEGER)), 0) "
                "FROM booking_print WHERE id_booking ~ '^PR-[0-9]+$'), 1), "
                "EXISTS (SELECT 1 FROM booking_print))"
            )
            cur.execute("SELECT nextval('seq_booking_print') AS nomor_baru")
            nomor_baru = cur.fetchone()["nomor_baru"]

            cur.execute(
                "INSERT INTO pesanan (kode_booking, id_customer, "
                "nama_pemesan, tanggal_pesan, jenis_pesanan, total_biaya, "
                "status_pesanan) VALUES (%s, %s, %s, %s, 'PRINT', %s, 'Diproses')",
                (kode, costumer["id_customer"], d["nama"], d["tanggal"],
                 d["hitung"]["total"]),
            )
            cur.execute(
                "INSERT INTO booking_print (id_booking, kode_booking, "
                "nama_link_file, ukuran_kertas, pilihan_warna, tipe_cetak, "
                "jumlah_lembar, jumlah_eksemplar, opsi_jilid, subtotal_cetak) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (f"PR-{nomor_baru:04d}", kode, d["berkas"], d["ukuran"],
                 d["warna"], d["tipe"], d["lembar"], d["eksemplar"], d["jilid"],
                 d["hitung"]["total"]),
            )
        conn.commit()
        return kode
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def form_booking_print(costumer):
    ringkasan_form = [f"[+] Nama Costumer    : {costumer['nama_customer']}"]

    def _render_form(pesan_error=None):
        segarkan_halaman(
            "FORM BOOKING PRINT ONLINE",
            info_baris=ringkasan_form,
            pesan_error=pesan_error,
        )

    try:
        _render_form()
        berkas = input_link_drive(
            "[1] Link Google Drive : ",
            render_ulang=_render_form,
        )
        ringkasan_form.append(f"[1] Link Google Drive: {berkas}")

        ukuran = pilih_opsi("[2] Pilih Ukuran Kertas :", UKURAN, _render_form)
        ringkasan_form.append(f"[2] Ukuran Kertas    : {ukuran}")

        warna = pilih_opsi("[3] Pilihan Warna :", WARNA, _render_form)
        ringkasan_form.append(f"[3] Pilihan Warna    : {LABEL_WARNA[warna]}")

        tipe = pilih_opsi("[4] Tipe Cetak :", TIPE, _render_form)
        ringkasan_form.append(f"[4] Tipe Cetak       : {LABEL_TIPE[tipe]}")

        _render_form()
        lembar = input_angka(
            "[5] Jumlah Lembar [1-1000] : ",
            minimum=1, maksimum=MAKS_LEMBAR, label="Jumlah lembar",
            render_ulang=_render_form,
        )
        ringkasan_form.append(f"[5] Jumlah Lembar    : {lembar}")

        _render_form()
        eksemplar = input_angka(
            "[6] Jumlah Eksemplar [1-100] : ",
            minimum=1, maksimum=MAKS_EKSEMPLAR, label="Jumlah eksemplar",
            render_ulang=_render_form,
        )
        ringkasan_form.append(f"[6] Jumlah Eksemplar : {eksemplar}")

        jilid = pilih_opsi("[7] Opsi Penjilidan :", JILID, _render_form)
        ringkasan_form.append(f"[7] Opsi Penjilidan  : {LABEL_JILID[jilid]}")
    except BatasRefreshError as err:
        segarkan_halaman("FORM BOOKING PRINT ONLINE", pesan_error=str(err))
        jeda_layar()
        return

    hitung = hitung_total_print(ukuran, warna, lembar, eksemplar, jilid)
    if hitung["total"] > TOTAL_MAKSIMUM:
        segarkan_halaman(
            "FORM BOOKING PRINT ONLINE",
            pesan_error="[X] Total biaya melebihi batas maksimal transaksi.",
        )
        jeda_layar()
        return

    data = {
        "nama": costumer["nama_customer"], "tanggal": waktu_sekarang(),
        "berkas": berkas, "ukuran": ukuran, "warna": warna, "tipe": tipe,
        "lembar": lembar, "eksemplar": eksemplar, "jilid": jilid,
        "hitung": hitung,
    }

    def _render_pratinjau(pesan_error=None):
        segarkan_halaman("KONFIRMASI BOOKING PRINT ONLINE", pesan_error=pesan_error)
        cetak_nota_print(data, pratinjau=True)

    _render_pratinjau()
    try:
        setuju = konfirmasi(
            "Konfirmasi pesanan dan terbitkan Kode Booking? [Y/T] : ",
            render_ulang=_render_pratinjau,
        )
    except BatasRefreshError as err:
        segarkan_halaman("FORM BOOKING PRINT ONLINE", pesan_error=str(err))
        jeda_layar()
        return

    if not setuju:
        print("[!] Pesanan booking print dibatalkan.")
        jeda_layar()
        return

    try:
        data["kode"] = simpan_booking_print(costumer, data)
    except (ConnectionError, psycopg2.Error) as err:
        pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
        segarkan_halaman(
            "FORM BOOKING PRINT ONLINE",
            pesan_error=f"[X] Gagal menyimpan booking print: {pesan}",
        )
        jeda_layar()
        return

    segarkan_halaman("NOTA BOOKING PRINT ONLINE")
    cetak_nota_print(data)
    jeda_layar()
