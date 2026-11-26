import re
import psycopg2
from database import koneksi
from tampilan import (garis, rupiah, input_teks, input_harga, input_stok,
                      input_pilihan, konfirmasi, HARGA_MINIMUM, _baca_input,
                      _proses_refresh_input, segarkan_halaman, jeda_layar,
                      BatasRefreshError, format_id_barang, parse_id_barang)


def input_nama_barang(prompt, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = " ".join(_baca_input(prompt).strip().split())
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        if len(isi) < 3 or len(isi) > 64:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Nama barang harus terdiri dari 3 sampai 64 karakter."
            )
            continue
        if not re.fullmatch(r"[a-zA-Z0-9\s.,/&+-]+", isi):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Nama barang mengandung simbol yang tidak diperbolehkan."
            )
            continue
        if len(re.findall(r"[a-zA-Z]", isi)) < 2:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Nama barang harus mengandung minimal 2 huruf."
            )
            continue
        return isi


def tampil_stok(conn):
    garis("-")
    print(f"{'ID BARANG':<12}{'NAMA BARANG':<28}{'HARGA BARANG':>15}"
          f"{'STOK BARANG':>17}")
    garis("-")
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM barang ORDER BY id_barang ASC")
        rows = cur.fetchall()
        if not rows:
            print("Belum ada data barang ATK.")
        for b in rows:
            kode_barang = format_id_barang(b["id_barang"])
            stok = b["stok_tersedia"]
            stok_teks = "Habis" if stok == 0 else f"{stok}"
            print(f"{kode_barang:<12}{b['nama_barang']:<28}"
                  f"{rupiah(b['harga_satuan']):>15}{stok_teks:>17}")
    garis("-")


def cari_barang(conn, judul_aksi):
    def _render_cari(pesan_error=None):
        segarkan_halaman(judul_aksi, pesan_error=pesan_error)
        tampil_stok(conn)

    _render_cari()
    try:
        raw_id = input_teks(
            "Masukkan ID Barang : ",
            maks_panjang=20,
            label="ID Barang",
            render_ulang=_render_cari,
        )
    except BatasRefreshError as err:
        segarkan_halaman(judul_aksi, pesan_error=str(err))
        return None

    id_barang = parse_id_barang(raw_id)
    if id_barang is None:
        print("[X] Format ID Barang tidak valid.")
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM barang WHERE id_barang = %s", (id_barang,))
        barang = cur.fetchone()
    if barang is None:
        print(f"[X] ID Barang {format_id_barang(id_barang)} tidak ditemukan.")
    return barang


def tambah_barang(conn):
    info_barang = []

    def _render_tambah(pesan_error=None):
        segarkan_halaman(
            "TAMBAH BARANG ATK BARU",
            info_baris=info_barang if info_barang else None,
            pesan_error=pesan_error,
        )

    try:
        with conn.cursor() as cur:
            _render_tambah()
            nama = input_nama_barang(
                "Nama Barang : ",
                render_ulang=_render_tambah,
            )
            cur.execute(
                "SELECT id_barang FROM barang WHERE LOWER(nama_barang) = LOWER(%s)",
                (nama,),
            )
            duplikat = cur.fetchone()
            if duplikat:
                kode_dup = format_id_barang(duplikat["id_barang"])
                print(f"[X] Barang {nama} sudah terdaftar dengan ID {kode_dup}.")
                return

            info_barang.append(f"Nama Barang  : {nama}")
            _render_tambah()

            harga = input_harga(
                "Harga Barang : ",
                minimum=HARGA_MINIMUM,
                render_ulang=_render_tambah,
            )
            info_barang.append(f"Harga Barang : {rupiah(harga)}")
            _render_tambah()

            stok = input_stok(
                "Stok Awal : ",
                minimum=0,
                render_ulang=_render_tambah,
            )
            info_barang.append(f"Stok Awal    : {stok}")
            _render_tambah()

            if not konfirmasi(
                "Simpan barang baru ini? [Y/T] : ",
                render_ulang=_render_tambah,
            ):
                print("[!] Penambahan barang dibatalkan.")
                return

            cur.execute(
                "INSERT INTO barang (nama_barang, harga_satuan, stok_tersedia) "
                "VALUES (%s, %s, %s) RETURNING id_barang",
                (nama, harga, stok),
            )
            id_baru = cur.fetchone()["id_barang"]
        conn.commit()
        print(f"[OK] Barang baru ditambahkan dengan ID {format_id_barang(id_baru)}.")
    except BatasRefreshError as err:
        conn.rollback()
        segarkan_halaman("TAMBAH BARANG ATK BARU", pesan_error=str(err))
    except psycopg2.Error as err:
        conn.rollback()
        print(f"[X] Gagal menambah barang: {err.pgerror or err}")


def update_stok(conn):
    barang = cari_barang(conn, "UPDATE STOK BARANG ATK")
    if barang is None:
        return
    kode_barang = format_id_barang(barang["id_barang"])
    info_stok = [
        f"Barang        : [{kode_barang}] {barang['nama_barang']}",
        f"Stok Saat Ini : {barang['stok_tersedia']}",
    ]

    def _render_update_stok(pesan_error=None):
        segarkan_halaman(
            "UPDATE STOK BARANG ATK",
            info_baris=info_stok,
            pesan_error=pesan_error,
        )

    _render_update_stok()
    try:
        stok_baru = input_stok(
            "Jumlah Stok Baru : ",
            minimum=0,
            render_ulang=_render_update_stok,
        )
        if stok_baru == barang["stok_tersedia"]:
            print("[!] Jumlah stok baru sama dengan stok saat ini.")
            return

        info_stok.append(f"Stok Baru     : {stok_baru}")
        _render_update_stok()

        if not konfirmasi(
            f"Ubah stok {barang['nama_barang']} menjadi {stok_baru}? [Y/T] : ",
            render_ulang=_render_update_stok,
        ):
            print("[!] Pembaruan stok dibatalkan.")
            return

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE barang SET stok_tersedia = %s WHERE id_barang = %s",
                (stok_baru, barang["id_barang"]),
            )
        conn.commit()
        print("[OK] Stok barang berhasil diperbarui.")
    except BatasRefreshError as err:
        conn.rollback()
        segarkan_halaman("UPDATE STOK BARANG ATK", pesan_error=str(err))
    except psycopg2.Error as err:
        conn.rollback()
        print(f"[X] Gagal memperbarui stok: {err.pgerror or err}")


def update_harga(conn):
    barang = cari_barang(conn, "UPDATE HARGA BARANG ATK")
    if barang is None:
        return
    kode_barang = format_id_barang(barang["id_barang"])
    info_harga = [
        f"Barang         : [{kode_barang}] {barang['nama_barang']}",
        f"Harga Saat Ini : {rupiah(barang['harga_satuan'])}",
    ]

    def _render_update_harga(pesan_error=None):
        segarkan_halaman(
            "UPDATE HARGA BARANG ATK",
            info_baris=info_harga,
            pesan_error=pesan_error,
        )

    _render_update_harga()
    try:
        harga_baru = input_harga(
            "Harga Barang Baru : ",
            minimum=HARGA_MINIMUM,
            render_ulang=_render_update_harga,
        )
        if harga_baru == int(round(barang["harga_satuan"])):
            print("[!] Harga baru sama dengan harga saat ini.")
            return

        info_harga.append(f"Harga Baru     : {rupiah(harga_baru)}")
        _render_update_harga()

        if not konfirmasi(
            f"Ubah harga {barang['nama_barang']} menjadi {rupiah(harga_baru)}? [Y/T] : ",
            render_ulang=_render_update_harga,
        ):
            print("[!] Pembaruan harga dibatalkan.")
            return

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE barang SET harga_satuan = %s WHERE id_barang = %s",
                (harga_baru, barang["id_barang"]),
            )
        conn.commit()
        print("[OK] Harga barang berhasil diperbarui.")
    except BatasRefreshError as err:
        conn.rollback()
        segarkan_halaman("UPDATE HARGA BARANG ATK", pesan_error=str(err))
    except psycopg2.Error as err:
        conn.rollback()
        print(f"[X] Gagal memperbarui harga: {err.pgerror or err}")


def kelola_stok(pegawai=None):
    conn = None
    info_pegawai = [f"Pegawai Aktif : {pegawai['nama_pegawai']}"] if pegawai else None
    try:
        conn = koneksi()
        def _render_kelola_stok(pesan_error=None):
            segarkan_halaman(
                "MANAJEMEN STOK BARANG ATK",
                info_baris=info_pegawai,
                pesan_error=pesan_error,
            )
            tampil_stok(conn)
            print("[1] Tambah Barang  [2] Update Stok  [3] Update Harga  [4] Kembali")
            garis("-")

        while True:
            _render_kelola_stok()
            try:
                pilihan = input_pilihan(
                    "Pilihan Anda [1-4] : ", 1, 4,
                    render_ulang=_render_kelola_stok,
                )
            except BatasRefreshError as err:
                segarkan_halaman("MANAJEMEN STOK BARANG ATK", pesan_error=str(err))
                jeda_layar()
                break

            if pilihan == 1:
                tambah_barang(conn)
                jeda_layar()
            elif pilihan == 2:
                update_stok(conn)
                jeda_layar()
            elif pilihan == 3:
                update_harga(conn)
                jeda_layar()
            else:
                break
    except (ConnectionError, psycopg2.Error) as err:
        pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
        segarkan_halaman("MANAJEMEN STOK BARANG ATK", pesan_error=f"[X] Kesalahan koneksi database: {pesan}")
        jeda_layar()
    finally:
        if conn is not None:
            conn.close()
