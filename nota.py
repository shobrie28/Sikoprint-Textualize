import os
import random
from datetime import datetime
import psycopg2
from database import koneksi
from tampilan import (LEBAR_DEFAULT, garis, rupiah, format_tanggal,
                      input_teks, segarkan_halaman, jeda_layar,
                      BatasRefreshError)
from tarif import LABEL_WARNA, LABEL_TIPE, LABEL_JILID

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER_NOTA = os.path.join(BASE_DIR, "arsip_nota")


def buat_kode_booking(conn, awalan="BOOK"):
    with conn.cursor() as cur:
        while True:
            kode = f"{awalan}-{random.randint(0, 0xFFFF):04X}"
            cur.execute(
                "SELECT 1 FROM pesanan WHERE kode_booking = %s",
                (kode,),
            )
            if not cur.fetchone():
                return kode


def _baris(label, nilai):
    if nilai.startswith("Rp"):
        nilai = nilai.rjust(12)
    return f"{label:<44}: {nilai}"


def _simpan_arsip_nota(kode, baris_nota):
    """Menyimpan salinan struk nota ke folder lokal arsip_nota menggunakan os."""
    try:
        os.makedirs(FOLDER_NOTA, exist_ok=True)
        nama_file = f"Nota_{kode}.txt"
        path_file = os.path.join(FOLDER_NOTA, nama_file)
        with open(path_file, "w", encoding="utf-8") as berkas:
            berkas.write("\n".join(baris_nota) + "\n")
        return os.path.abspath(path_file)
    except OSError as err:
        print(f"[!] Arsip file nota gagal disimpan: {err}")
        return None


def cetak_nota_print(d, pratinjau=False):
    judul_teks = ("PRATINJAU NOTA BOOKING PRINT" if pratinjau
                  else "NOTA BOOKING PRINT ONLINE")
    kode = "Menunggu Konfirmasi" if pratinjau else d["kode"]
    h = d["hitung"]

    isi_nota = [
        "=" * LEBAR_DEFAULT,
        judul_teks.center(LEBAR_DEFAULT),
        "=" * LEBAR_DEFAULT,
        f"KODE BOOKING  : {kode}",
        f"NAMA COSTUMER : {d['nama']}",
        f"TANGGAL PESAN : {format_tanggal(d['tanggal'])}",
        "-" * LEBAR_DEFAULT,
        "RINCIAN SPESIFIKASI CETAK:",
        f"- Link Drive    : {d['berkas']}",
        f"- Kertas & Mode : {d['ukuran']} | {LABEL_WARNA[d['warna']]} | "
        f"{LABEL_TIPE[d['tipe']]}",
        f"- Jumlah        : {d['lembar']} Lembar x {d['eksemplar']} Eksemplar = "
        f"{h['lembar_cetak']} Lembar Cetak",
    ]
    if h["jumlah_jilid"]:
        isi_nota.append(
            f"- Jilid         : {LABEL_JILID[d['jilid']]} ({h['jumlah_jilid']} pcs)"
        )
    else:
        isi_nota.append(f"- Jilid         : {LABEL_JILID[d['jilid']]}")

    isi_nota.extend([
        "-" * LEBAR_DEFAULT,
        "Rincian Biaya:",
        _baris(
            f"- Cetak {d['warna']} {d['ukuran']} "
            f"({h['lembar_cetak']} x {rupiah(h['tarif_cetak'])})",
            rupiah(h["biaya_cetak"]),
        ),
    ])
    if h["jumlah_jilid"]:
        isi_nota.append(
            _baris(
                f"- {LABEL_JILID[d['jilid']]} "
                f"({h['jumlah_jilid']} x {rupiah(h['tarif_jilid'])})",
                rupiah(h["biaya_jilid"]),
            )
        )
    isi_nota.extend([
        "-" * LEBAR_DEFAULT,
        _baris("TOTAL BIAYA CETAK", rupiah(h["total"])),
        _baris("STATUS PESANAN", "DIPROSES"),
        "=" * LEBAR_DEFAULT,
    ])
    if not pratinjau:
        isi_nota.extend([
            "* Simpan KODE BOOKING ini. Tunjukkan kepada pegawai",
            "  saat mengambil hasil cetakan dan melakukan pembayaran.",
            "=" * LEBAR_DEFAULT,
        ])

    print("\n".join(isi_nota))
    if not pratinjau:
        path_tersimpan = _simpan_arsip_nota(d["kode"], isi_nota)
        if path_tersimpan:
            print(f"[FILE] Struk nota diarsipkan ke: {path_tersimpan}")


def cetak_nota_atk(kode, nama, tanggal, items, total):
    isi_nota = [
        "=" * LEBAR_DEFAULT,
        "NOTA PEMBELIAN BARANG ATK".center(LEBAR_DEFAULT),
        "=" * LEBAR_DEFAULT,
        f"KODE BOOKING  : {kode}",
        f"NAMA COSTUMER : {nama}",
        f"TANGGAL PESAN : {format_tanggal(tanggal)}",
        "-" * LEBAR_DEFAULT,
        f"{'NAMA BARANG':<32}{'QTY':>5}{'HARGA':>15}{'SUBTOTAL':>15}",
    ]
    for it in items:
        isi_nota.append(
            f"{it['nama']:<32}{it['jumlah']:>5}"
            f"{rupiah(it['harga']):>15}{rupiah(it['subtotal']):>15}"
        )
    isi_nota.extend([
        "-" * LEBAR_DEFAULT,
        _baris("TOTAL PEMBELIAN", rupiah(total)),
        _baris("STATUS PESANAN", "DIPROSES"),
        "=" * LEBAR_DEFAULT,
        "* Simpan KODE BOOKING ini. Tunjukkan kepada pegawai",
        "  saat mengambil barang dan melakukan pembayaran.",
        "=" * LEBAR_DEFAULT,
    ])

    print("\n".join(isi_nota))
    path_tersimpan = _simpan_arsip_nota(kode, isi_nota)
    if path_tersimpan:
        print(f"[FILE] Struk nota diarsipkan ke: {path_tersimpan}")


def lihat_arsip_nota(costumer=None):
    """Menampilkan daftar dan isi file struk nota di folder arsip_nota."""
    info_header = []
    if costumer is not None:
        info_header.append(f"Nama Costumer : {costumer['nama_customer']}")
    info_header.append(f"Lokasi Folder : {FOLDER_NOTA}")

    kode_milik_costumer = None
    if costumer is not None:
        conn = koneksi()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT kode_booking FROM pesanan WHERE id_customer = %s",
                    (costumer["id_customer"],),
                )
                kode_milik_costumer = {
                    f"NOTA_{baris['kode_booking'].upper()}.TXT"
                    for baris in cur.fetchall()
                }
        except (ConnectionError, psycopg2.Error) as err:
            pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
            segarkan_halaman("ARSIP FILE NOTA TRANSAKSI", pesan_error=f"[X] Gagal memverifikasi nota: {pesan}")
            jeda_layar()
            return
        finally:
            conn.close()

    try:
        os.makedirs(FOLDER_NOTA, exist_ok=True)
        daftar_file = sorted(
            f for f in os.listdir(FOLDER_NOTA)
            if os.path.isfile(os.path.join(FOLDER_NOTA, f)) and f.endswith(".txt")
            and (kode_milik_costumer is None or f.upper() in kode_milik_costumer)
        )
    except OSError as err:
        segarkan_halaman("ARSIP FILE NOTA TRANSAKSI", pesan_error=f"[X] Gagal membaca folder arsip nota: {err}")
        jeda_layar()
        return

    def _render_arsip(pesan_error=None):
        segarkan_halaman(
            "ARSIP FILE NOTA TRANSAKSI",
            info_baris=info_header,
            pesan_error=pesan_error,
        )
        if not daftar_file:
            print("Belum ada file nota yang tersimpan.")
            garis("-")
            return
        print(f"{'NO':<5}{'NAMA FILE NOTA':<26}{'UKURAN':>10}  {'WAKTU SIMPAN'}")
        garis("-")
        for no, nama_file in enumerate(daftar_file, start=1):
            full_path = os.path.join(FOLDER_NOTA, nama_file)
            ukuran = os.path.getsize(full_path)
            waktu_mod = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime(
                "%d/%m/%Y %H:%M"
            )
            print(f"{no:<5}{nama_file:<26}{ukuran:>7} B  {waktu_mod}")
        garis("-")

    _render_arsip()
    if not daftar_file:
        jeda_layar()
        return

    try:
        kode = input_teks(
            "Masukkan Kode Booking [0 untuk kembali] : ",
            maks_panjang=32,
            label="Kode Booking",
            render_ulang=_render_arsip,
        ).upper()
    except BatasRefreshError as err:
        segarkan_halaman("ARSIP FILE NOTA TRANSAKSI", pesan_error=str(err))
        jeda_layar()
        return

    if kode == "0":
        return
    if not kode.startswith("NOTA_"):
        kode = f"Nota_{kode}"
    if not kode.lower().endswith(".txt"):
        kode += ".txt"

    target = None
    for nama_file in daftar_file:
        if nama_file.upper() == kode.upper():
            target = os.path.join(FOLDER_NOTA, nama_file)
            break

    if target is None or not os.path.isfile(target):
        print("[X] File nota dengan Kode Booking tersebut tidak ditemukan.")
        jeda_layar()
        return

    segarkan_halaman("DETAIL FILE NOTA TRANSAKSI")
    try:
        with open(target, "r", encoding="utf-8") as berkas:
            print(berkas.read().rstrip())
    except OSError as err:
        print(f"[X] Gagal membaca isi file nota: {err}")
    jeda_layar()
