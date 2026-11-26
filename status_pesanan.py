import re
import psycopg2
from database import koneksi
from tampilan import (garis, rupiah, input_teks, konfirmasi, format_id_barang,
                      segarkan_halaman, jeda_layar, BatasRefreshError)
from antrean_pegawai import ringkas_spesifikasi, tampil_antrean

URUTAN_STATUS = ["Diproses", "Selesai", "Tuntas"]
KETERANGAN = {
    "Diproses": "DIPROSES",
    "Selesai": "SELESAI",
    "Tuntas": "TUNTAS",
}


def ubah_status_pesanan(pegawai=None):
    conn = None
    try:
        conn = koneksi()
        info_pegawai = [f"Pegawai Aktif : {pegawai['nama_pegawai']}"] if pegawai else None

        def _render_cari_booking(pesan_error=None):
            segarkan_halaman(
                "UBAH STATUS PESANAN",
                info_baris=info_pegawai,
                pesan_error=pesan_error,
            )
            tampil_antrean(conn)

        _render_cari_booking()
        try:
            kode = input_teks(
                "Masukkan Kode Booking [0 untuk batal] : ",
                maks_panjang=32,
                label="Kode Booking",
                render_ulang=_render_cari_booking,
            ).upper()
        except BatasRefreshError as err:
            segarkan_halaman("UBAH STATUS PESANAN", pesan_error=str(err))
            jeda_layar()
            return

        if kode == "0":
            print("[!] Perubahan status dibatalkan.")
            jeda_layar()
            return

        if not re.fullmatch(r"(BOOK|BELI)-[0-9A-F]{4}", kode):
            print("[X] Format Kode Booking tidak valid.")
            jeda_layar()
            return

        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pesanan WHERE kode_booking = %s",
                (kode,),
            )
            pesanan = cur.fetchone()

        if pesanan is None:
            print("[X] Kode Booking tidak ditemukan.")
            jeda_layar()
            return

        detail_baris = [
            f"Kode Booking    : {pesanan['kode_booking']}",
            f"Costumer        : {pesanan['nama_pemesan']}",
            f"Spesifikasi     : {ringkas_spesifikasi(conn, pesanan)}",
        ]
        if pesanan["jenis_pesanan"] == "PRINT":
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM booking_print WHERE kode_booking = %s",
                    (kode,),
                )
                cetak = cur.fetchone()
            if cetak:
                detail_baris.extend([
                    f"Link Drive      : {cetak['nama_link_file']}",
                    f"Tipe Cetak      : {cetak['tipe_cetak']}",
                    f"Jumlah          : {cetak['jumlah_lembar']} lembar x {cetak['jumlah_eksemplar']} eksemplar",
                ])
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id_barang, nama_barang, jumlah, subtotal "
                    "FROM detail_atk WHERE kode_booking = %s ORDER BY id_detail ASC",
                    (kode,),
                )
                daftar_atk = cur.fetchall()
            if daftar_atk:
                detail_baris.append("Rincian Barang  :")
                for item in daftar_atk:
                    detail_baris.append(
                        f"  - [{format_id_barang(item['id_barang'])}] "
                        f"{item['nama_barang']} x{item['jumlah']} "
                        f"= {rupiah(item['subtotal'])}"
                    )
        detail_baris.extend([
            f"Total Biaya     : {rupiah(pesanan['total_biaya'])}",
            f"Status Saat Ini : {KETERANGAN[pesanan['status_pesanan']]}",
        ])

        def _render_detail_status(pesan_error=None):
            segarkan_halaman(
                "DETAIL STATUS PESANAN",
                info_baris=detail_baris,
                pesan_error=pesan_error,
            )

        _render_detail_status()
        posisi = URUTAN_STATUS.index(pesanan["status_pesanan"])
        if posisi == len(URUTAN_STATUS) - 1:
            print("[!] Pesanan ini sudah tuntas dan tidak dapat diubah.")
            jeda_layar()
            return

        status_baru = URUTAN_STATUS[posisi + 1]
        if status_baru == "Tuntas":
            print("[!] Pastikan Kode Booking sesuai dengan nota costumer dan pembayaran sudah diterima.")
            garis("-")

        try:
            setuju = konfirmasi(
                f"Ubah status menjadi {KETERANGAN[status_baru]}? [Y/T] : ",
                render_ulang=_render_detail_status,
            )
        except BatasRefreshError as err:
            segarkan_halaman("DETAIL STATUS PESANAN", pesan_error=str(err))
            jeda_layar()
            return

        if setuju:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pesanan SET status_pesanan = %s "
                    "WHERE kode_booking = %s",
                    (status_baru, kode),
                )
            conn.commit()
            print(f"[OK] Status pesanan {kode} diubah menjadi {KETERANGAN[status_baru]}.")
        else:
            print("[!] Perubahan status dibatalkan.")
        jeda_layar()
    except (ConnectionError, psycopg2.Error) as err:
        if conn is not None:
            conn.rollback()
        pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
        segarkan_halaman("UBAH STATUS PESANAN", pesan_error=f"[X] Gagal memproses status pesanan: {pesan}")
        jeda_layar()
    finally:
        if conn is not None:
            conn.close()
