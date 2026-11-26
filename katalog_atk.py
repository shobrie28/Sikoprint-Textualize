import psycopg2
from database import koneksi
from tampilan import (garis, buat_tabel, rupiah, input_teks, input_angka,
                      input_pilihan, konfirmasi, waktu_sekarang,
                      segarkan_halaman, jeda_layar, BatasRefreshError,
                      format_id_barang, parse_id_barang, TOTAL_MAKSIMUM)
from nota import buat_kode_booking, cetak_nota_atk


def tampil_katalog(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM barang ORDER BY id_barang ASC")
        rows = cur.fetchall()
    if not rows:
        garis("-")
        print("Belum ada barang ATK di katalog.")
        garis("-")
        return
    baris = []
    for b in rows:
        stok = b["stok_tersedia"]
        status = "[green]Tersedia[/green]" if stok > 0 else "[red]Habis[/red]"
        baris.append((format_id_barang(b["id_barang"]), b["nama_barang"],
                      rupiah(b["harga_satuan"]), stok, status))
    kolom = [("ID BARANG", "left"), ("NAMA BARANG", "left"),
             ("HARGA BARANG", "right"), ("STOK", "right"), ("STATUS", "left")]
    if not buat_tabel(kolom, baris):
        garis("-")
        print(f"{'ID BARANG':<12}{'NAMA BARANG':<26}{'HARGA BARANG':>15}"
              f"{'STOK':>8}  STATUS")
        garis("-")
        for b in baris:
            status = "Tersedia" if "Tersedia" in b[4] else "Habis"
            print(f"{b[0]:<12}{b[1]:<26}{b[2]:>15}{b[3]:>8}  {status}")
        garis("-")


def tambah_ke_keranjang(conn, keranjang):
    def _render_tambah(pesan_error=None):
        segarkan_halaman("TAMBAH BARANG KE KERANJANG", pesan_error=pesan_error)
        tampil_katalog(conn)

    _render_tambah()
    try:
        raw_id = input_teks(
            "Masukkan ID Barang : ",
            maks_panjang=20,
            label="ID Barang",
            render_ulang=_render_tambah,
        )
    except BatasRefreshError as err:
        segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=str(err))
        return

    id_barang = parse_id_barang(raw_id)
    if id_barang is None:
        print("[X] Format ID Barang tidak valid.")
        return

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM barang WHERE id_barang = %s", (id_barang,))
        barang = cur.fetchone()

    if barang is None:
        print(f"[X] Barang dengan ID {format_id_barang(id_barang)} tidak ditemukan.")
        return

    if barang["stok_tersedia"] <= 0:
        print(f"[X] Stok barang {barang['nama_barang']} habis dan tidak dapat dipesan.")
        return

    sudah_di_keranjang = keranjang.get(id_barang, 0)
    sisa_stok = barang["stok_tersedia"] - sudah_di_keranjang
    if sisa_stok <= 0:
        print(f"[X] Semua stok {barang['nama_barang']} sudah berada di keranjang.")
        return

    def _render_jumlah(pesan_error=None):
        segarkan_halaman(
            "TAMBAH BARANG KE KERANJANG",
            info_baris=[
                f"Barang        : [{format_id_barang(id_barang)}] {barang['nama_barang']}",
                f"Harga Barang  : {rupiah(barang['harga_satuan'])}",
                f"Stok Tersedia : {sisa_stok} unit",
            ],
            pesan_error=pesan_error,
        )

    _render_jumlah()
    try:
        jumlah = input_angka(
            f"Jumlah Beli [1-{sisa_stok}] : ",
            minimum=1, maksimum=sisa_stok, label="Jumlah beli",
            render_ulang=_render_jumlah,
        )
    except BatasRefreshError as err:
        segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=str(err))
        return

    keranjang[id_barang] = sudah_di_keranjang + jumlah
    print(f"[OK] {barang['nama_barang']} x{jumlah} ditambahkan ke keranjang.")


def hapus_dari_keranjang(conn, keranjang):
    if not keranjang:
        print("[!] Keranjang masih kosong.")
        return

    def _render_hapus(pesan_error=None):
        segarkan_halaman("HAPUS BARANG DARI KERANJANG", pesan_error=pesan_error)
        tampil_keranjang(conn, keranjang)

    _render_hapus()
    try:
        raw_id = input_teks(
            "Masukkan ID Barang yang akan dihapus : ",
            maks_panjang=20,
            label="ID Barang",
            render_ulang=_render_hapus,
        )
    except BatasRefreshError as err:
        segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=str(err))
        return

    id_barang = parse_id_barang(raw_id)
    if id_barang is None or id_barang not in keranjang:
        print("[X] ID Barang tersebut tidak ada di keranjang.")
        return
    del keranjang[id_barang]
    print(f"[OK] Barang {format_id_barang(id_barang)} dihapus dari keranjang.")


def tampil_keranjang(conn, keranjang):
    items, total = [], 0
    garis("-")
    print("ISI KERANJANG BELANJA")
    garis("-")
    with conn.cursor() as cur:
        for id_barang, jumlah in list(keranjang.items()):
            cur.execute("SELECT * FROM barang WHERE id_barang = %s",
                        (id_barang,))
            b = cur.fetchone()
            if b is None:
                del keranjang[id_barang]
                continue
            harga_int = int(round(b["harga_satuan"]))
            subtotal = harga_int * jumlah
            total += subtotal
            items.append({
                "id": id_barang,
                "kode": format_id_barang(id_barang),
                "nama": b["nama_barang"],
                "harga": harga_int,
                "jumlah": jumlah,
                "subtotal": subtotal,
                "stok_aktual": b["stok_tersedia"],
            })
            ket_stok = "" if b["stok_tersedia"] >= jumlah else " [STOK KURANG]"
            print(f"[{format_id_barang(id_barang)}] {b['nama_barang']:<24}{jumlah:>4} x "
                  f"{rupiah(harga_int):>11} = {rupiah(subtotal):>12}{ket_stok}")
    if not items:
        print("Keranjang masih kosong.")
    garis("-")
    print(f"TOTAL BELANJA : {rupiah(total)}")
    return items, total


def checkout(conn, costumer, keranjang):
    def _render_checkout(pesan_error=None):
        segarkan_halaman("CHECKOUT PEMBELIAN BARANG ATK", pesan_error=pesan_error)
        tampil_keranjang(conn, keranjang)

    _render_checkout()
    items, total = tampil_keranjang(conn, keranjang) if False else ([], 0) 
    # Ambil data keranjang tanpa mencetak tabel dua kali
    with conn.cursor() as cur:
        for id_barang, jumlah in list(keranjang.items()):
            cur.execute("SELECT * FROM barang WHERE id_barang = %s", (id_barang,))
            b = cur.fetchone()
            if b is None:
                continue
            harga_int = int(round(b["harga_satuan"]))
            subtotal = harga_int * jumlah
            total += subtotal
            items.append({
                "id": id_barang,
                "kode": format_id_barang(id_barang),
                "nama": b["nama_barang"],
                "harga": harga_int,
                "jumlah": jumlah,
                "subtotal": subtotal,
                "stok_aktual": b["stok_tersedia"],
            })

    if not items:
        return False

    for it in items:
        if it["stok_aktual"] <= 0:
            print(f"[X] Checkout ditolak: stok {it['nama']} habis.")
            return False
        if it["jumlah"] > it["stok_aktual"]:
            print(f"[X] Checkout ditolak: stok {it['nama']} hanya tersisa {it['stok_aktual']} unit.")
            return False

    if total > TOTAL_MAKSIMUM:
        print("[X] Total belanja melebihi batas maksimal transaksi.")
        return False

    try:
        setuju = konfirmasi(
            "Konfirmasi pembelian? [Y/T] : ",
            render_ulang=_render_checkout,
        )
    except BatasRefreshError as err:
        segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=str(err))
        return False

    if not setuju:
        print("[!] Pembelian dibatalkan.")
        return False

    try:
        kode = buat_kode_booking(conn, "BELI")
        tanggal = waktu_sekarang()
        with conn.cursor() as cur:
            for it in items:
                cur.execute(
                    "UPDATE barang SET stok_tersedia = stok_tersedia - %s "
                    "WHERE id_barang = %s AND stok_tersedia >= %s",
                    (it["jumlah"], it["id"], it["jumlah"]),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        f"Stok {it['nama']} tidak mencukupi atau sudah habis."
                    )
            cur.execute(
                "INSERT INTO pesanan (kode_booking, id_customer, "
                "nama_pemesan, tanggal_pesan, jenis_pesanan, total_biaya, "
                "status_pesanan) VALUES (%s, %s, %s, %s, 'ATK', %s, 'Diproses')",
                (kode, costumer["id_customer"], costumer["nama_customer"],
                 tanggal, total),
            )
            for it in items:
                cur.execute(
                    "INSERT INTO detail_atk (kode_booking, id_barang, "
                    "nama_barang, harga_satuan, jumlah, subtotal) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (kode, it["id"], it["nama"], it["harga"], it["jumlah"],
                     it["subtotal"]),
                )
        conn.commit()
    except (ValueError, ConnectionError, psycopg2.Error) as galat:
        conn.rollback()
        pesan = galat.pgerror if isinstance(galat, psycopg2.Error) and galat.pgerror else str(galat)
        print(f"[X] Transaksi gagal: {pesan}")
        return False

    segarkan_halaman("NOTA PEMBELIAN BARANG ATK")
    cetak_nota_atk(kode, costumer["nama_customer"], tanggal, items, total)
    return True


def menu_pembelian_atk(costumer):
    conn = None
    keranjang = {}
    try:
        conn = koneksi()
        def _render_menu_atk(pesan_error=None):
            segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=pesan_error)
            tampil_katalog(conn)
            if keranjang:
                print(f"Keranjang: {len(keranjang)} jenis barang, {sum(keranjang.values())} unit.")
                garis("-")
            print("[1] Tambah Barang ke Keranjang   [2] Lihat Keranjang")
            print("[3] Hapus Barang dari Keranjang  [4] Kosongkan Keranjang")
            print("[5] Checkout                     [6] Kembali")
            garis("-")

        while True:
            _render_menu_atk()
            try:
                pilihan = input_pilihan(
                    "Pilihan Anda [1-6] : ", 1, 6,
                    render_ulang=_render_menu_atk,
                )
            except BatasRefreshError as err:
                segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=str(err))
                jeda_layar()
                break

            if pilihan == 1:
                tambah_ke_keranjang(conn, keranjang)
                jeda_layar()
            elif pilihan == 2:
                segarkan_halaman("KERANJANG BELANJA")
                tampil_keranjang(conn, keranjang)
                jeda_layar()
            elif pilihan == 3:
                hapus_dari_keranjang(conn, keranjang)
                jeda_layar()
            elif pilihan == 4:
                if not keranjang:
                    print("[!] Keranjang sudah kosong.")
                    jeda_layar()
                else:
                    try:
                        if konfirmasi(
                            "Kosongkan seluruh isi keranjang? [Y/T] : ",
                            render_ulang=_render_menu_atk,
                        ):
                            keranjang.clear()
                            print("[OK] Keranjang berhasil dikosongkan.")
                            jeda_layar()
                    except BatasRefreshError as err:
                        segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=str(err))
                        jeda_layar()
            elif pilihan == 5:
                if checkout(conn, costumer, keranjang):
                    keranjang.clear()
                    jeda_layar()
                    break
                jeda_layar()
            else:
                if keranjang:
                    try:
                        if not konfirmasi(
                            "Keranjang masih berisi barang. Keluar tanpa checkout? [Y/T] : ",
                            render_ulang=_render_menu_atk,
                        ):
                            continue
                    except BatasRefreshError as err:
                        segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=str(err))
                        jeda_layar()
                        continue
                break
    except (ConnectionError, psycopg2.Error) as err:
        pesan = err.pgerror if isinstance(err, psycopg2.Error) and err.pgerror else str(err)
        segarkan_halaman("KATALOG & PEMBELIAN BARANG ATK", pesan_error=f"[X] Kesalahan koneksi database: {pesan}")
        jeda_layar()
    finally:
        if conn is not None:
            conn.close()
