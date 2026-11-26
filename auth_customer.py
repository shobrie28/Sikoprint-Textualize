import psycopg2
from database import koneksi, hash_password
from tampilan import (garis, input_teks, input_username, input_nama,
                      input_password, input_pilihan, input_telepon,
                      segarkan_halaman, jeda_layar, BatasRefreshError)

MAKS_PERCOBAAN_LOGIN = 3


def registrasi_customer():
    data_terisi = []

    def _render_registrasi(pesan_error=None):
        segarkan_halaman(
            "REGISTRASI COSTUMER BARU",
            info_baris=data_terisi if data_terisi else None,
            pesan_error=pesan_error,
        )

    _render_registrasi()
    conn = None
    try:
        conn = koneksi()
        with conn.cursor() as cur:
            while True:
                username = input_username(
                    "[+] Username : ",
                    maks_panjang=64,
                    render_ulang=_render_registrasi,
                )
                cur.execute(
                    "SELECT 1 FROM customer WHERE LOWER(username) = LOWER(%s)",
                    (username,),
                )
                if cur.fetchone():
                    _render_registrasi("[X] Username sudah digunakan, pilih username lain.")
                else:
                    break
            data_terisi.append(f"[+] Username    : {username}")
            _render_registrasi()

            nama = input_nama(
                "[+] Nama Lengkap : ",
                maks_panjang=64,
                render_ulang=_render_registrasi,
            )
            data_terisi.append(f"[+] Nama        : {nama}")
            _render_registrasi()

            telepon = input_telepon(
                "[+] No. Telepon : ",
                render_ulang=_render_registrasi,
            )
            data_terisi.append(f"[+] No. Telepon : {telepon}")
            _render_registrasi()

            while True:
                password = input_password(
                    "[+] Password : ",
                    maks_panjang=64,
                    render_ulang=_render_registrasi,
                )
                konfirm_pw = input_password(
                    "[+] Ulangi Password : ",
                    maks_panjang=64,
                    render_ulang=_render_registrasi,
                )
                if password != konfirm_pw:
                    _render_registrasi("[X] Konfirmasi password tidak sama.")
                    continue
                break

            cur.execute(
                "INSERT INTO customer (username, password, "
                "nama_customer, no_telepon) VALUES (%s, %s, %s, %s)",
                (username, hash_password(password), nama, telepon),
            )
        conn.commit()
    except BatasRefreshError as err:
        if conn is not None:
            conn.rollback()
        segarkan_halaman("REGISTRASI COSTUMER BARU", pesan_error=str(err))
        jeda_layar()
        return
    except (ConnectionError, psycopg2.Error) as err:
        if conn is not None:
            conn.rollback()
        pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
        segarkan_halaman("REGISTRASI COSTUMER BARU", pesan_error=f"[X] Gagal menyimpan registrasi: {pesan}")
        jeda_layar()
        return
    finally:
        if conn is not None:
            conn.close()

    segarkan_halaman("REGISTRASI COSTUMER BARU", info_baris=data_terisi)
    print("[OK] Registrasi berhasil! Silakan login dengan akun Anda.")
    jeda_layar()


def login_customer():
    pesan_login = None
    for percobaan in range(MAKS_PERCOBAAN_LOGIN):
        info_username = []

        def _render_login(pesan_error=None):
            segarkan_halaman(
                "LOGIN COSTUMER",
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
            segarkan_halaman("LOGIN COSTUMER", pesan_error=str(err))
            jeda_layar()
            return None

        garis("-")
        conn = None
        try:
            conn = koneksi()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM customer WHERE username = %s "
                    "AND password = %s",
                    (username, hash_password(password)),
                )
                baris = cur.fetchone()
        except (ConnectionError, psycopg2.Error) as err:
            pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
            segarkan_halaman("LOGIN COSTUMER", pesan_error=f"[X] Kesalahan database saat login: {pesan}")
            jeda_layar()
            return None
        finally:
            if conn is not None:
                conn.close()

        if baris:
            data = dict(baris)
            data["no_telepon"] = data["no_telepon"].strip()
            segarkan_halaman("LOGIN COSTUMER")
            print(f"[OK] Login berhasil! Selamat datang, {data['nama_customer']}.")
            jeda_layar()
            return data

        sisa = MAKS_PERCOBAAN_LOGIN - percobaan - 1
        pesan_login = f"[X] Username atau password salah. Sisa percobaan: {sisa}"

    segarkan_halaman("LOGIN COSTUMER", pesan_error="[X] Percobaan login habis.")
    jeda_layar()
    return None


def menu_auth_customer():
    def _render_auth_costumer(pesan_error=None):
        segarkan_halaman("LAYANAN COSTUMER SI-KOPRINT", pesan_error=pesan_error)
        print("[1] Login Akun")
        print("[2] Registrasi Akun Baru")
        print("[3] Kembali ke Menu Utama")
        garis("-")

    while True:
        _render_auth_costumer()
        try:
            pilihan = input_pilihan(
                "Pilihan Anda [1-3] : ", 1, 3,
                render_ulang=_render_auth_costumer,
            )
        except BatasRefreshError as err:
            segarkan_halaman("LAYANAN COSTUMER SI-KOPRINT", pesan_error=str(err))
            jeda_layar()
            return None

        if pilihan == 1:
            costumer = login_customer()
            if costumer:
                return costumer
        elif pilihan == 2:
            registrasi_customer()
        else:
            return None
