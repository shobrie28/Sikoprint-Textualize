from tampilan import judul, garis, buat_tabel


def ringkas_spesifikasi(conn, pesanan):
    with conn.cursor() as cur:
        if pesanan["jenis_pesanan"] == "PRINT":
            cur.execute(
                "SELECT * FROM booking_print WHERE kode_booking = %s",
                (pesanan["kode_booking"],),
            )
            b = cur.fetchone()
            if not b:
                return "Detail print tidak ditemukan"
            lembar = b["jumlah_lembar"] * b["jumlah_eksemplar"]
            jilid = "Tanpa Jilid" if b["opsi_jilid"] == "Tanpa" else b["opsi_jilid"]
            teks = f"{b['ukuran_kertas']} {b['pilihan_warna']} {lembar} lbr + {jilid}"
        else:
            cur.execute(
                "SELECT nama_barang, jumlah FROM detail_atk WHERE kode_booking = %s",
                (pesanan["kode_booking"],),
            )
            rincian = cur.fetchall()
            if not rincian:
                return "ATK: Detail kosong"
            teks = "ATK: " + ", ".join(
                f"{(r['nama_barang'].split() or ['Barang'])[0]} x{r['jumlah']}"
                for r in rincian
            )
    return teks if len(teks) <= 28 else teks[:25] + "..."


def tampil_antrean(conn):
    judul("DAFTAR ANTREAN PESANAN MASUK")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM pesanan WHERE status_pesanan != 'Tuntas' "
            "ORDER BY urutan ASC"
        )
        antrean = cur.fetchall()
    if not antrean:
        garis("-")
        print("Belum ada pesanan dalam antrean.")
    else:
        baris = [(f"{no}.", p["kode_booking"], p["nama_pemesan"][:13],
                  ringkas_spesifikasi(conn, p), p["status_pesanan"].upper())
                 for no, p in enumerate(antrean, start=1)]
        kolom = [("NO", "right"), ("KODE BOOKING", "left"), ("COSTUMER", "left"),
                 ("DETAIL SPESIFIKASI", "left"), ("STATUS", "left")]
        if not buat_tabel(kolom, baris):
            print(f"{'NO':<4}{'KODE BOOKING':<14}{'COSTUMER':<15}"
                  f"{'DETAIL SPESIFIKASI':<30}{'STATUS'}")
            garis("-")
            for b in baris:
                print(f"{b[0]:<4}{b[1]:<14}{b[2]:<15}{b[3]:<30}{b[4]}")
    garis("-")
    return antrean
