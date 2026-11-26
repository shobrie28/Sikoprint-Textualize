# Tabel tarif dan opsi layanan Booking Print Online
UKURAN = [("A4", "A4"), ("F4", "F4"), ("A3", "A3")]
WARNA = [("BW", "Hitam-Putih"), ("Color", "Full Color")]
TIPE = [("1 Sisi", "Satu Sisi"), ("2 Sisi", "Bolak-Balik")]
JILID = [("Tanpa", "Tanpa Jilid"), ("Lakban", "Jilid Lakban"),
         ("Spiral", "Jilid Spiral")]

LABEL_WARNA = {"BW": "Hitam-Putih", "Color": "Full Color"}
LABEL_TIPE = {"1 Sisi": "Satu Sisi", "2 Sisi": "Bolak-Balik"}
LABEL_JILID = {"Tanpa": "Tanpa Jilid", "Lakban": "Jilid Lakban",
               "Spiral": "Jilid Spiral"}

# Tarif cetak per lembar dan tarif jilid per paket
TARIF_CETAK = {
    ("A4", "BW"): 500,   ("A4", "Color"): 1000,
    ("F4", "BW"): 600,   ("F4", "Color"): 1200,
    ("A3", "BW"): 1500,  ("A3", "Color"): 3000,
}
TARIF_JILID = {"Tanpa": 0, "Lakban": 3000, "Spiral": 7000}


def hitung_total_print(ukuran, warna, jumlah_lembar, jumlah_eksemplar,
                       opsi_jilid):
    lembar_cetak = jumlah_lembar * jumlah_eksemplar
    tarif_cetak = TARIF_CETAK[(ukuran, warna)]
    biaya_cetak = lembar_cetak * tarif_cetak

    tarif_jilid = TARIF_JILID[opsi_jilid]
    jumlah_jilid = 0 if tarif_jilid == 0 else 1
    biaya_jilid = jumlah_jilid * tarif_jilid

    return {
        "lembar_cetak": lembar_cetak,
        "tarif_cetak": tarif_cetak,
        "biaya_cetak": biaya_cetak,
        "jumlah_jilid": jumlah_jilid,
        "tarif_jilid": tarif_jilid,
        "biaya_jilid": biaya_jilid,
        "total": biaya_cetak + biaya_jilid,
    }
