import psycopg2
from database import siapkan_database, koneksi, BASE_DIR
from tampilan import (judul, garis, input_pilihan, segarkan_halaman,
                      jeda_layar, info_lingkungan_os, BatasRefreshError)
from auth_pegawai import login_pegawai
from auth_customer import menu_auth_customer
from katalog_atk import menu_pembelian_atk
from booking_print import form_booking_print
from antrean_pegawai import tampil_antrean
from status_pesanan import ubah_status_pesanan
from stok_pegawai import kelola_stok
from nota import lihat_arsip_nota


def menu_customer(costumer):
    def _render_menu_costumer(pesan_error=None):
        segarkan_halaman(
            f"MENU COSTUMER - {costumer['nama_customer'].upper()}",
            pesan_error=pesan_error,
        )
        print("[1] Pembelian Barang ATK")
        print("[2] Booking Print Online")
        print("[3] Lihat Arsip File Nota")
        print("[4] Logout")
        garis("-")

    while True:
        _render_menu_costumer()
        try:
            pilihan = input_pilihan(
                "Pilihan Anda [1-4] : ", 1, 4,
                render_ulang=_render_menu_costumer,
            )
        except BatasRefreshError as err:
            segarkan_halaman(
                f"MENU COSTUMER - {costumer['nama_customer'].upper()}",
                pesan_error=str(err),
            )
            jeda_layar()
            continue

        if pilihan == 1:
            menu_pembelian_atk(costumer)
        elif pilihan == 2:
            form_booking_print(costumer)
        elif pilihan == 3:
            lihat_arsip_nota(costumer)
        else:
            print("[OK] Anda telah logout.")
            jeda_layar()
            break


def dashboard_pegawai(pegawai):
    while True:
        conn = None
        try:
            conn = koneksi()
            def _render_dashboard(pesan_error=None):
                segarkan_halaman(
                    "DASHBOARD PEGAWAI",
                    info_baris=[f"Pegawai Aktif : {pegawai['nama_pegawai']}"],
                )
                tampil_antrean(conn)
                if pesan_error:
                    print(pesan_error)
                print("PILIH AKSI PEGAWAI:")
                print("[1] Ubah Status Pesanan")
                print("[2] Kelola Stok Barang ATK")
                print("[3] Lihat Arsip File Nota & Info Sistem")
                print("[4] Logout")
                garis("-")

            _render_dashboard()
            try:
                pilihan = input_pilihan(
                    "Pilihan Anda [1-4] : ", 1, 4,
                    render_ulang=_render_dashboard,
                )
            except BatasRefreshError as err:
                segarkan_halaman("DASHBOARD PEGAWAI", pesan_error=str(err))
                jeda_layar()
                continue
        except (ConnectionError, psycopg2.Error) as err:
            pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
            segarkan_halaman("DASHBOARD PEGAWAI", pesan_error=f"[X] Gagal memuat antrean pesanan: {pesan}")
            jeda_layar()
            break
        finally:
            if conn is not None:
                conn.close()

        if pilihan == 1:
            ubah_status_pesanan(pegawai)
        elif pilihan == 2:
            kelola_stok(pegawai)
        elif pilihan == 3:
            segarkan_halaman(
                "INFORMASI SISTEM & DIREKTORI APLIKASI",
                info_baris=[
                    f"Sistem Operasi  : {info_lingkungan_os()['sistem']}",
                    f"Pengguna OS     : {info_lingkungan_os()['pengguna_os']}",
                    f"Folder Aplikasi : {BASE_DIR}",
                    f"Working Dir     : {info_lingkungan_os()['cwd']}",
                ],
            )
            lihat_arsip_nota()
        else:
            print("[OK] Anda telah logout.")
            jeda_layar()
            break


def main():
    try:
        siapkan_database()
    except (ConnectionError, RuntimeError, psycopg2.Error) as err:
        pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
        print(f"[X] Inisialisasi database gagal:\n{pesan}")
        return

    def _render_menu_utama(pesan_error=None):
        segarkan_halaman("MENU UTAMA SI-KOPRINT", pesan_error=pesan_error)
        print("PILIH PERAN:")
        print("[1] Layanan Costumer")
        print("[2] Layanan Pegawai")
        print("[3] Keluar")
        garis("=")

    while True:
        _render_menu_utama()
        try:
            pilihan = input_pilihan(
                "Pilihan Anda [1-3] : ", 1, 3,
                render_ulang=_render_menu_utama,
            )
        except BatasRefreshError as err:
            segarkan_halaman("MENU UTAMA SI-KOPRINT", pesan_error=str(err))
            jeda_layar()
            continue

        if pilihan == 1:
            costumer = menu_auth_customer()
            if costumer:
                menu_customer(costumer)
        elif pilihan == 2:
            pegawai = login_pegawai()
            if pegawai:
                dashboard_pegawai(pegawai)
        else:
            print("Terima kasih telah menggunakan SI-KOPRINT.")
            break


def _pastikan_textual():
    """Memastikan textual & rich terpasang; mencoba memasangnya otomatis."""
    try:
        import textual  # noqa: F401
        import rich  # noqa: F401
        return True
    except ImportError:
        pass
    import subprocess
    import sys
    print("[!] Textual/Rich belum terpasang. Mencoba memasang otomatis...")
    hasil = subprocess.run(
        [sys.executable, "-m", "pip", "install", "textual>=0.86.0", "rich>=13.7.0"])
    if hasil.returncode != 0:
        return False
    try:
        import textual  # noqa: F401
        return True
    except ImportError:
        return False


def jalankan_tui():
    if not _pastikan_textual():
        print("\n[X] Gagal memasang Textual. Jalankan manual:\n"
              "    pip install -r requirements.txt\n"
              "Lalu jalankan ulang: python main.py\n"
              "(Mode lama tanpa Textual: python main.py --cli)")
        return
    from tui import jalankan
    jalankan()


if __name__ == "__main__":
    import sys
    try:
        if "--cli" in sys.argv:
            main()
        else:
            jalankan_tui()
    except KeyboardInterrupt:
        print("\nProgram dihentikan oleh pengguna.")
