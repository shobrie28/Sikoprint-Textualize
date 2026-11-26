import psycopg2
from database import koneksi, hash_password
from tampilan import (garis, input_teks, input_password,
                      segarkan_halaman, jeda_layar, BatasRefreshError)

MAKS_PERCOBAAN_LOGIN = 3


def login_pegawai():
    pesan_login = None
    for percobaan in range(MAKS_PERCOBAAN_LOGIN):
        info_username = []

        def _render_login(pesan_error=None):
            segarkan_halaman(
                "LOGIN PEGAWAI",
                info_baris=info_username if info_username else None,
                pesan_error=pesan_error if pesan_error is not None else pesan_login,
            )

        _render_login()
        try:
            username = input_teks(
                "[+] Username : ",
                maks_panjang=64,
                label="Username",
                render_ulang=_render_login,
            )
            info_username.append(f"[+] Username : {username}")
            pesan_login = None
            _render_login()

            password = input_password(
                "[+] Password : ",
                maks_panjang=64,
                render_ulang=_render_login,
            )
        except BatasRefreshError as err:
            segarkan_halaman("LOGIN PEGAWAI", pesan_error=str(err))
            jeda_layar()
            return None

        garis("-")
        conn = None
        try:
            conn = koneksi()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM pegawai WHERE username = %s AND password = %s",
                    (username, hash_password(password)),
                )
                baris = cur.fetchone()
        except (ConnectionError, psycopg2.Error) as err:
            pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
            segarkan_halaman("LOGIN PEGAWAI", pesan_error=f"[X] Kesalahan database saat login: {pesan}")
            jeda_layar()
            return None
        finally:
            if conn is not None:
                conn.close()

        if baris:
            segarkan_halaman("LOGIN PEGAWAI")
            print(f"[OK] Login berhasil! Selamat datang, {baris['nama_pegawai']}.")
            jeda_layar()
            return dict(baris)

        sisa = MAKS_PERCOBAAN_LOGIN - percobaan - 1
        pesan_login = f"[X] Username atau password salah. Sisa percobaan: {sisa}"

    segarkan_halaman("LOGIN PEGAWAI", pesan_error="[X] Percobaan login habis.")
    jeda_layar()
    return None
