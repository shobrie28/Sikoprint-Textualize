"""SI-KOPRINT versi TUI (Textual by Textualize) - https://textual.textualize.io

Jalankan:  python main.py        (TUI Textual)
           python main.py --cli  (mode konsol klasik)
"""
import contextlib
import io
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import psycopg2
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (Button, DataTable, Footer, Header, Input, Label,
                             Select, Static, TabbedContent, TabPane)

import database
import tampilan
from database import (koneksi, hash_password, DDL_SKEMA, isi_data_awal,
                      _skema_lama_terdeteksi, _selaraskan_kolom_telepon)
from tampilan import (rupiah, format_id_barang, format_tanggal, waktu_sekarang,
                      GEDUNG_PRINTER_ASCII, TEKS_SIKOPRINT_ASCII, TOTAL_MAKSIMUM,
                      HARGA_MINIMUM, HARGA_MAKSIMUM, STOK_MAKSIMUM)
from tarif import (UKURAN, WARNA, TIPE, JILID, hitung_total_print)
from nota import (buat_kode_booking, cetak_nota_print, cetak_nota_atk,
                  FOLDER_NOTA)
from booking_print import simpan_booking_print, DOMAIN_DRIVE_VALID
from antrean_pegawai import ringkas_spesifikasi

# print() asli dipulihkan agar nota bisa ditangkap (redirect_stdout)
import builtins
builtins.print = tampilan._print_asli

MAKS_LOGIN = 3
TEMA_FILE = os.path.join(database.BASE_DIR, ".tema")
TEMA = {"gelap": True}
PALET = {
    True: {"Diproses": "#fbbf24", "Selesai": "#38bdf8", "Tuntas": "#4ade80",
           "ok": "#4ade80", "err": "#f87171"},
    False: {"Diproses": "#b45309", "Selesai": "#0369a1", "Tuntas": "#15803d",
            "ok": "#15803d", "err": "#b91c1c"},
}


def w(kunci):
    """Warna semantik yang menyesuaikan tema terang/gelap aktif."""
    return PALET[TEMA["gelap"]][kunci]


def gaya_status(status):
    return f"bold {w(status)}"


THEME_GELAP = Theme(
    name="sikoprint-gelap", dark=True,
    primary="#3b9eff", secondary="#7aa2c7", accent="#ffb454",
    success="#4ade80", warning="#fbbf24", error="#f87171",
    foreground="#e6edf3", background="#0d1520", surface="#142030", panel="#1b2b3f",
)
THEME_TERANG = Theme(
    name="sikoprint-terang", dark=False,
    primary="#1565c0", secondary="#546e8a", accent="#c2570c",
    success="#15803d", warning="#b45309", error="#b91c1c",
    foreground="#1b2430", background="#eef2f7", surface="#ffffff", panel="#e3eaf3",
)
URUTAN_STATUS = ["Diproses", "Selesai", "Tuntas"]


# ───────────────────────── util ─────────────────────────
def galat_db(err):
    if isinstance(err, psycopg2.Error) and err.pgerror:
        return err.pgerror.strip()
    return str(err)


def tangkap(fn, *args, **kwargs):
    """Menjalankan fungsi bergaya print() dan mengembalikan teksnya."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue().rstrip()


def query(sql, params=(), satu=False):
    conn = koneksi()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone() if satu else cur.fetchall()
    finally:
        conn.close()


def eksekusi(sql, params=()):
    conn = koneksi()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def baris_terpilih(tbl):
    if tbl.row_count == 0:
        return None
    try:
        return tbl.coordinate_to_cell_key(tbl.cursor_coordinate).row_key.value
    except Exception:
        return None


def isi_tabel(tbl, baris):
    """Mengisi ulang DataTable sambil mempertahankan posisi kursor."""
    lama = tbl.cursor_row
    tbl.clear()
    for kunci, sel in baris:
        tbl.add_row(*sel, key=str(kunci))
    if baris:
        tbl.move_cursor(row=min(lama, len(baris) - 1))


# ───────────────────────── validasi ─────────────────────────
def v_username(s):
    if "@" in s:
        return "Username tidak boleh berformat email."
    if not re.fullmatch(r"[a-zA-Z0-9_]{4,64}", s):
        return "Username 4-64 karakter: huruf, angka, garis bawah (tanpa spasi)."
    if not re.search(r"[a-zA-Z]", s):
        return "Username harus mengandung minimal 1 huruf."


def v_nama(s):
    if not re.fullmatch(r"[a-zA-Z\s'.-]{2,64}", s) or len(re.findall(r"[a-zA-Z]", s)) < 2:
        return "Nama 2-64 karakter, hanya huruf/spasi/titik/apostrof/strip."


def v_telepon(s):
    if not (s.isascii() and s.isdigit() and s.startswith("08") and 10 <= len(s) <= 13):
        return "No. telepon harus angka, diawali 08, 10-13 digit."
    if len(set(s[2:])) == 1:
        return "No. telepon tidak valid."


def v_password(s):
    if " " in s or not (6 <= len(s) <= 64):
        return "Password 6-64 karakter tanpa spasi."


def v_link_drive(s):
    if not s or " " in s or len(s) > 255:
        return "Link kosong, mengandung spasi, atau lebih dari 255 karakter."
    p = urlparse(s)
    host = p.netloc.lower().removeprefix("www.")
    if p.scheme not in ("http", "https") or host not in DOMAIN_DRIVE_VALID:
        return "Harus link drive.google.com atau docs.google.com."
    if len(p.path.strip("/")) < 5:
        return "Link Google Drive belum lengkap."


def angka(teks, nama, mn, mx):
    t = teks.strip()
    if not (t.isascii() and t.isdigit()):
        return None, f"{nama} harus berupa angka bulat."
    n = int(t)
    if not (mn <= n <= mx):
        return None, f"{nama} harus antara {mn} sampai {mx:,}.".replace(",", ".")
    return n, None


def profil(nama, peran, detail, kelas):
    """Kartu profil: avatar inisial + nama tebal + peran/detail + petunjuk logout."""
    inisial = (nama.strip()[:1] or "?").upper()
    return Horizontal(
        Static(inisial, classes="avatar"),
        Vertical(Static(nama, classes="p-nama"),
                 Static(f"{peran}  •  {detail}", classes="p-detail"),
                 classes="p-info"),
        Static("Esc  ➜  Logout", classes="p-aksi"),
        id="profil", classes=kelas)


def kolom(label, widget):
    """Pasangan label + input dalam satu kolom rapi."""
    return Vertical(Label(label), widget, classes="col")


# ───────────────────────── modal ─────────────────────────
class KonfirmasiModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "batal", "Batal"), Binding("y", "ya", "Ya"),
                Binding("t", "batal", "Tidak")]

    def __init__(self, pesan, judul="Konfirmasi"):
        super().__init__()
        self.pesan, self.judul = pesan, judul

    def compose(self):
        with Vertical(id="dialog"):
            yield Label(self.judul, id="dialog-judul")
            yield Static(self.pesan, id="dialog-isi")
            with Horizontal(id="dialog-aksi"):
                yield Button("Ya (Y)", variant="success", id="ya")
                yield Button("Tidak (T)", variant="error", id="tidak")

    @on(Button.Pressed, "#ya")
    def action_ya(self):
        self.dismiss(True)

    @on(Button.Pressed, "#tidak")
    def action_batal(self):
        self.dismiss(False)


class NotaModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "tutup", "Tutup"), Binding("enter", "tutup", "Tutup")]

    def __init__(self, teks, judul="Nota"):
        super().__init__()
        self.teks, self.judul = teks, judul

    def compose(self):
        with Vertical(id="nota-box"):
            yield Label(self.judul, id="dialog-judul")
            with VerticalScroll(id="nota-scroll"):
                yield Static(Text(self.teks), id="nota-isi")
            yield Button("Tutup (Esc)", variant="primary", id="tutup")

    @on(Button.Pressed, "#tutup")
    def action_tutup(self):
        self.dismiss(None)


# ───────────────────────── welcome ─────────────────────────
def banner():
    """Logo dua kolom (ikon + teks) yang warnanya diatur CSS mengikuti tema."""
    return Horizontal(
        Static("\n".join(GEDUNG_PRINTER_ASCII), classes="logo"),
        Static("\n".join(TEKS_SIKOPRINT_ASCII), classes="judul-logo"),
        classes="banner")


class WelcomeScreen(Screen):
    AUTO_FOCUS = ""   # tidak ada tombol yang terpilih otomatis
    BINDINGS = [Binding("1", "cust", "Costumer"), Binding("2", "peg", "Pegawai"),
                Binding("q", "app.quit", "Keluar")]

    def compose(self):
        yield Header(show_clock=True)
        with Vertical(id="welcome"):
            with Center():
                yield banner()
            with Center():
                with Vertical(id="peran-box") as box:
                    box.border_title = "Pilih Peran"
                    yield Label("Silakan pilih layanan yang ingin Anda gunakan", id="sub")
                    yield Button("[1]  Layanan Costumer", id="btn-cust", variant="primary")
                    yield Button("[2]  Layanan Pegawai", id="btn-peg", variant="warning")
                    yield Button("[Q]  Keluar", id="btn-keluar", variant="error")
        yield Footer()

    @on(Button.Pressed, "#btn-cust")
    def action_cust(self):
        self.app.push_screen(AuthScreen("customer"))

    @on(Button.Pressed, "#btn-peg")
    def action_peg(self):
        self.app.push_screen(AuthScreen("pegawai"))

    @on(Button.Pressed, "#btn-keluar")
    def keluar(self):
        self.app.exit()


# ───────────────────────── auth ─────────────────────────
class AuthScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Kembali")]

    def __init__(self, role):
        super().__init__()
        self.role = role
        self.gagal = 0

    def _login(self, prefiks):
        yield kolom("Username", Input(placeholder="username", id=f"{prefiks}-user", max_length=64))
        yield kolom("Password", Input(placeholder="password", password=True,
                                      id=f"{prefiks}-pass", max_length=64))
        yield Button("Masuk", variant="primary", id=f"{prefiks}-masuk")
        yield Label("", id=f"{prefiks}-pesan", classes="pesan")

    def compose(self):
        yield Header(show_clock=True)
        judul = "LOGIN COSTUMER" if self.role == "customer" else "LOGIN PEGAWAI"
        with Vertical(id="auth-box") as box:
            box.border_title = "SI-KOPRINT"
            box.border_subtitle = "Esc = kembali"
            yield Static(judul if self.role != "customer" else "LAYANAN COSTUMER",
                         id="auth-judul")
            if self.role == "customer":
                with TabbedContent():
                    with TabPane("Login", id="tab-login"):
                        yield from self._login("l")
                    with TabPane("Registrasi", id="tab-reg"):
                        with Horizontal(classes="row"):
                            yield kolom("Username", Input(id="r-user", max_length=64))
                            yield kolom("Nama Lengkap", Input(id="r-nama", max_length=64))
                        with Horizontal(classes="row"):
                            yield kolom("Password", Input(id="r-pw", password=True, max_length=64))
                            yield kolom("Ulangi Password", Input(id="r-pw2", password=True, max_length=64))
                        yield kolom("No. Telepon (08xxxxxxxxxx)", Input(id="r-tel", max_length=13))
                        yield Button("Daftar", variant="success", id="r-daftar")
                        yield Label("", id="r-pesan", classes="pesan")
            else:
                yield from self._login("l")
        yield Footer()

    def _set_pesan(self, id_, teks, ok=False):
        wd = w("ok" if ok else "err")
        lbl = self.query_one(id_, Label)
        lbl.update(Text(teks, style=f"bold {wd}"))

    @on(Input.Submitted, "#l-user")
    def _pindah(self):
        self.query_one("#l-pass").focus()

    @on(Input.Submitted, "#l-pass")
    @on(Button.Pressed, "#l-masuk")
    def masuk(self):
        user = self.query_one("#l-user", Input).value.strip()
        pw = self.query_one("#l-pass", Input).value
        if not user or not pw:
            return self._set_pesan("#l-pesan", "Username dan password wajib diisi.")
        tabel = "customer" if self.role == "customer" else "pegawai"
        try:
            baris = query(f"SELECT * FROM {tabel} WHERE username = %s AND password = %s",
                          (user, hash_password(pw)), satu=True)
        except (ConnectionError, psycopg2.Error) as err:
            return self._set_pesan("#l-pesan", galat_db(err))
        if baris:
            data = dict(baris)
            if self.role == "customer":
                data["no_telepon"] = data["no_telepon"].strip()
                self.app.notify(f"Selamat datang, {data['nama_customer']}!", title="Login berhasil")
                self.app.switch_screen(CustomerScreen(data))
            else:
                self.app.notify(f"Selamat datang, {data['nama_pegawai']}!", title="Login berhasil")
                self.app.switch_screen(StaffScreen(data))
            return
        self.gagal += 1
        sisa = MAKS_LOGIN - self.gagal
        if sisa <= 0:
            self.app.notify("Percobaan login habis.", severity="error")
            self.app.pop_screen()
            return
        self._set_pesan("#l-pesan", f"Username atau password salah. Sisa percobaan: {sisa}")

    @on(Button.Pressed, "#r-daftar")
    def daftar(self):
        g = lambda i: self.query_one(i, Input).value.strip()
        user, nama, tel = g("#r-user"), g("#r-nama"), g("#r-tel")
        pw = self.query_one("#r-pw", Input).value
        pw2 = self.query_one("#r-pw2", Input).value
        nama = " ".join(nama.split())
        galat = (v_username(user) or v_nama(nama) or v_telepon(tel) or v_password(pw)
                 or (None if pw == pw2 else "Konfirmasi password tidak sama."))
        if galat:
            return self._set_pesan("#r-pesan", galat)
        try:
            if query("SELECT 1 FROM customer WHERE LOWER(username)=LOWER(%s)", (user,), satu=True):
                return self._set_pesan("#r-pesan", "Username sudah digunakan.")
            eksekusi("INSERT INTO customer (username, password, nama_customer, no_telepon) "
                     "VALUES (%s,%s,%s,%s)", (user, hash_password(pw), nama, tel))
        except (ConnectionError, psycopg2.Error) as err:
            return self._set_pesan("#r-pesan", galat_db(err))
        for i in ("#r-user", "#r-nama", "#r-tel", "#r-pw", "#r-pw2"):
            self.query_one(i, Input).value = ""
        self.app.notify("Registrasi berhasil! Silakan login.", title="Sukses")
        self.query_one(TabbedContent).active = "tab-login"
        self.query_one("#l-user", Input).value = user
        self.query_one("#l-pass", Input).focus()


# ───────────────────────── customer ─────────────────────────
class CustomerScreen(Screen):
    BINDINGS = [Binding("escape", "logout", "Logout"),
                Binding("f5", "muat", "Refresh")]

    def __init__(self, costumer):
        super().__init__()
        self.c = costumer
        self.keranjang = {}   # id_barang -> jumlah

    def compose(self):
        yield Header(show_clock=True)
        yield profil(self.c["nama_customer"], "Costumer",
                     f"📞 {self.c['no_telepon']}   •   @{self.c.get('username', '')}", "cust")
        with TabbedContent(id="tabs-cust"):
            with TabPane("🛒 Katalog ATK", id="t-atk"):
                with Horizontal(classes="cols"):
                    with Vertical(classes="panel") as p:
                        p.border_title = "Katalog Barang"
                        yield DataTable(id="tbl-katalog", cursor_type="row", zebra_stripes=True)
                        with Horizontal(classes="toolbar"):
                            yield Label("Jumlah")
                            yield Input("1", id="qty", type="integer", max_length=6)
                            yield Button("➕ Tambah ke Keranjang", variant="primary", id="btn-tambah")
                    with Vertical(classes="panel") as p:
                        p.border_title = "Keranjang Belanja"
                        yield DataTable(id="tbl-cart", cursor_type="row", zebra_stripes=True)
                        yield Static("", id="total-cart")
                        with Horizontal(classes="toolbar"):
                            yield Button("Hapus", id="btn-hapus")
                            yield Button("Kosongkan", variant="warning", id="btn-kosong")
                            yield Button("Checkout ✔", variant="success", id="btn-checkout")
            with TabPane("🖨 Booking Print", id="t-print"):
                with VerticalScroll():
                    with Vertical(classes="panel form") as p:
                        p.border_title = "Form Booking Print Online"
                        yield kolom("Link Google Drive",
                                    Input(placeholder="https://drive.google.com/...",
                                          id="p-link", max_length=255))
                        with Horizontal(classes="row"):
                            yield kolom("Ukuran Kertas", Select(
                                [(l, v) for v, l in UKURAN], value="A4",
                                allow_blank=False, id="p-ukuran"))
                            yield kolom("Warna", Select(
                                [(l, v) for v, l in WARNA], value="BW",
                                allow_blank=False, id="p-warna"))
                            yield kolom("Tipe Cetak", Select(
                                [(l, v) for v, l in TIPE], value="1 Sisi",
                                allow_blank=False, id="p-tipe"))
                            yield kolom("Penjilidan", Select(
                                [(l, v) for v, l in JILID], value="Tanpa",
                                allow_blank=False, id="p-jilid"))
                        with Horizontal(classes="row"):
                            yield kolom("Jumlah Lembar [1-1000]",
                                        Input("1", id="p-lembar", type="integer", max_length=4))
                            yield kolom("Jumlah Eksemplar [1-100]",
                                        Input("1", id="p-eks", type="integer", max_length=3))
                        yield Static("", id="p-estimasi")
                        yield Button("Pesan & Terbitkan Kode Booking", variant="success", id="p-pesan")
            with TabPane("📜 Riwayat & Nota", id="t-riwayat"):
                with Vertical(classes="panel") as p:
                    p.border_title = "Riwayat Pesanan Saya (auto-refresh 5 detik)"
                    yield DataTable(id="tbl-riwayat", cursor_type="row", zebra_stripes=True)
                    with Horizontal(classes="toolbar"):
                        yield Button("Lihat Nota", variant="primary", id="btn-nota")
        yield Footer()

    def on_mount(self):
        k = self.query_one("#tbl-katalog", DataTable)
        k.add_columns("ID", "NAMA BARANG", "HARGA", "STOK", "STATUS")
        c = self.query_one("#tbl-cart", DataTable)
        c.add_columns("ID", "NAMA BARANG", "QTY", "HARGA", "SUBTOTAL")
        r = self.query_one("#tbl-riwayat", DataTable)
        r.add_columns("KODE", "TANGGAL", "JENIS", "TOTAL", "STATUS")
        self.action_muat()
        self.hitung_estimasi()
        self.set_interval(5, self.muat_riwayat)

    def action_muat(self):
        self.muat_katalog()
        self.muat_cart()
        self.muat_riwayat()

    def action_logout(self):
        self.app.notify("Anda telah logout.")
        self.app.pop_screen()

    # --- katalog & keranjang
    def muat_katalog(self):
        try:
            rows = query("SELECT * FROM barang ORDER BY id_barang")
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        isi_tabel(self.query_one("#tbl-katalog", DataTable), [
            (b["id_barang"], (format_id_barang(b["id_barang"]), b["nama_barang"],
                              Text(rupiah(b["harga_satuan"]), justify="right"),
                              Text(str(b["stok_tersedia"]), justify="right"),
                              Text("Tersedia", style=w("ok")) if b["stok_tersedia"] > 0
                              else Text("Habis", style=f"bold {w('err')}")))
            for b in rows])

    def info_cart(self):
        items, total = [], 0
        for idb, jml in self.keranjang.items():
            b = query("SELECT * FROM barang WHERE id_barang=%s", (idb,), satu=True)
            if not b:
                continue
            h = int(round(b["harga_satuan"]))
            items.append({"id": idb, "kode": format_id_barang(idb), "nama": b["nama_barang"],
                          "harga": h, "jumlah": jml, "subtotal": h * jml,
                          "stok_aktual": b["stok_tersedia"]})
            total += h * jml
        return items, total

    def muat_cart(self):
        try:
            items, total = self.info_cart()
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        isi_tabel(self.query_one("#tbl-cart", DataTable), [
            (i["id"], (i["kode"], i["nama"], str(i["jumlah"]), rupiah(i["harga"]),
                       rupiah(i["subtotal"]))) for i in items])
        self.query_one("#total-cart", Static).update(
            f"TOTAL BELANJA : {rupiah(total)}")

    @on(Button.Pressed, "#btn-tambah")
    def tambah(self):
        idb = baris_terpilih(self.query_one("#tbl-katalog", DataTable))
        if idb is None:
            return self.app.notify("Pilih barang terlebih dahulu.", severity="warning")
        idb = int(idb)
        jml, galat = angka(self.query_one("#qty", Input).value, "Jumlah", 1, 100_000)
        if galat:
            return self.app.notify(galat, severity="error")
        b = query("SELECT * FROM barang WHERE id_barang=%s", (idb,), satu=True)
        if not b or b["stok_tersedia"] <= 0:
            return self.app.notify("Stok barang habis.", severity="error")
        baru = self.keranjang.get(idb, 0) + jml
        if baru > b["stok_tersedia"]:
            return self.app.notify(
                f"Stok {b['nama_barang']} hanya {b['stok_tersedia']} unit "
                f"(di keranjang {self.keranjang.get(idb, 0)}).", severity="error")
        self.keranjang[idb] = baru
        self.muat_cart()
        self.app.notify(f"{b['nama_barang']} x{jml} ditambahkan.", title="Keranjang")

    @on(Button.Pressed, "#btn-hapus")
    def hapus(self):
        idb = baris_terpilih(self.query_one("#tbl-cart", DataTable))
        if idb is None:
            return self.app.notify("Keranjang kosong / belum dipilih.", severity="warning")
        self.keranjang.pop(int(idb), None)
        self.muat_cart()

    @on(Button.Pressed, "#btn-kosong")
    def kosongkan(self):
        self.keranjang.clear()
        self.muat_cart()

    @on(Button.Pressed, "#btn-checkout")
    def checkout(self):
        try:
            items, total = self.info_cart()
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        if not items:
            return self.app.notify("Keranjang masih kosong.", severity="warning")
        for it in items:
            if it["jumlah"] > it["stok_aktual"]:
                return self.app.notify(f"Stok {it['nama']} tersisa {it['stok_aktual']}.",
                                       severity="error")
        if total > TOTAL_MAKSIMUM:
            return self.app.notify("Total melebihi batas maksimal transaksi.", severity="error")
        self.app.push_screen(
            KonfirmasiModal(f"Beli {len(items)} jenis barang?\nTotal: {rupiah(total)}",
                            "Konfirmasi Pembelian"),
            lambda ok: self._proses_checkout(ok, items, total))

    def _proses_checkout(self, ok, items, total):
        if not ok:
            return self.app.notify("Pembelian dibatalkan.", severity="warning")
        conn = koneksi()
        try:
            kode = buat_kode_booking(conn, "BELI")
            tgl = waktu_sekarang()
            with conn.cursor() as cur:
                for it in items:
                    cur.execute("UPDATE barang SET stok_tersedia = stok_tersedia - %s "
                                "WHERE id_barang=%s AND stok_tersedia >= %s",
                                (it["jumlah"], it["id"], it["jumlah"]))
                    if cur.rowcount == 0:
                        raise ValueError(f"Stok {it['nama']} tidak mencukupi.")
                cur.execute("INSERT INTO pesanan (kode_booking, id_customer, nama_pemesan, "
                            "tanggal_pesan, jenis_pesanan, total_biaya, status_pesanan) "
                            "VALUES (%s,%s,%s,%s,'ATK',%s,'Diproses')",
                            (kode, self.c["id_customer"], self.c["nama_customer"], tgl, total))
                for it in items:
                    cur.execute("INSERT INTO detail_atk (kode_booking, id_barang, nama_barang, "
                                "harga_satuan, jumlah, subtotal) VALUES (%s,%s,%s,%s,%s,%s)",
                                (kode, it["id"], it["nama"], it["harga"], it["jumlah"], it["subtotal"]))
            conn.commit()
        except (ValueError, psycopg2.Error) as err:
            conn.rollback()
            return self.app.notify(galat_db(err), title="Transaksi gagal", severity="error")
        finally:
            conn.close()
        self.keranjang.clear()
        self.action_muat()
        teks = tangkap(cetak_nota_atk, kode, self.c["nama_customer"], tgl, items, total)
        self.app.push_screen(NotaModal(teks, f"NOTA {kode}"))

    # --- booking print
    def _form_print(self):
        v = lambda i: self.query_one(i, Select).value
        return v("#p-ukuran"), v("#p-warna"), v("#p-tipe"), v("#p-jilid")

    @on(Select.Changed)
    @on(Input.Changed, "#p-lembar")
    @on(Input.Changed, "#p-eks")
    def hitung_estimasi(self, *_):
        try:
            uk, wr, tp, jl = self._form_print()
            lb = int(self.query_one("#p-lembar", Input).value or 0)
            ek = int(self.query_one("#p-eks", Input).value or 0)
        except Exception:
            return
        if not (1 <= lb <= 1000 and 1 <= ek <= 100):
            return self.query_one("#p-estimasi", Static).update(
                Text("Isi jumlah lembar (1-1000) & eksemplar (1-100).", style="dim"))
        h = hitung_total_print(uk, wr, lb, ek, jl)
        self.query_one("#p-estimasi", Static).update(
            f"Cetak {h['lembar_cetak']} lbr x {rupiah(h['tarif_cetak'])} = {rupiah(h['biaya_cetak'])}"
            f"   Jilid: {rupiah(h['biaya_jilid'])}\nESTIMASI TOTAL : {rupiah(h['total'])}")

    @on(Button.Pressed, "#p-pesan")
    def pesan_print(self):
        link = self.query_one("#p-link", Input).value.strip().strip("\"'")
        galat = v_link_drive(link)
        lb, g1 = angka(self.query_one("#p-lembar", Input).value, "Jumlah lembar", 1, 1000)
        ek, g2 = angka(self.query_one("#p-eks", Input).value, "Jumlah eksemplar", 1, 100)
        galat = galat or g1 or g2
        if galat:
            return self.app.notify(galat, title="Input tidak valid", severity="error")
        uk, wr, tp, jl = self._form_print()
        h = hitung_total_print(uk, wr, lb, ek, jl)
        if h["total"] > TOTAL_MAKSIMUM:
            return self.app.notify("Total melebihi batas maksimal transaksi.", severity="error")
        data = {"nama": self.c["nama_customer"], "tanggal": waktu_sekarang(), "berkas": link,
                "ukuran": uk, "warna": wr, "tipe": tp, "lembar": lb, "eksemplar": ek,
                "jilid": jl, "hitung": h}
        pratinjau = tangkap(cetak_nota_print, data, True)
        self.app.push_screen(KonfirmasiModal(pratinjau + "\n\nTerbitkan Kode Booking?",
                                             "Konfirmasi Booking Print"),
                             lambda ok: self._simpan_print(ok, data))

    def _simpan_print(self, ok, data):
        if not ok:
            return self.app.notify("Booking dibatalkan.", severity="warning")
        try:
            data["kode"] = simpan_booking_print(self.c, data)
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), title="Gagal menyimpan", severity="error")
        teks = tangkap(cetak_nota_print, data)
        self.query_one("#p-link", Input).value = ""
        self.muat_riwayat()
        self.app.push_screen(NotaModal(teks, f"NOTA {data['kode']}"))

    # --- riwayat
    def muat_riwayat(self):
        try:
            rows = query("SELECT * FROM pesanan WHERE id_customer=%s ORDER BY urutan DESC",
                         (self.c["id_customer"],))
        except (ConnectionError, psycopg2.Error):
            return
        isi_tabel(self.query_one("#tbl-riwayat", DataTable), [
            (p["kode_booking"], (p["kode_booking"], format_tanggal(p["tanggal_pesan"]),
                                 p["jenis_pesanan"], rupiah(p["total_biaya"]),
                                 Text(p["status_pesanan"].upper(),
                                      style=gaya_status(p['status_pesanan']))))
            for p in rows])

    @on(Button.Pressed, "#btn-nota")
    def lihat_nota(self):
        kode = baris_terpilih(self.query_one("#tbl-riwayat", DataTable))
        if not kode:
            return self.app.notify("Pilih pesanan terlebih dahulu.", severity="warning")
        path = os.path.join(FOLDER_NOTA, f"Nota_{kode}.txt")
        try:
            with open(path, encoding="utf-8") as f:
                self.app.push_screen(NotaModal(f.read().rstrip(), f"NOTA {kode}"))
        except OSError:
            self.app.notify("File nota tidak ditemukan di arsip.", severity="error")


# ───────────────────────── pegawai ─────────────────────────
class StaffScreen(Screen):
    BINDINGS = [Binding("escape", "logout", "Logout"), Binding("f5", "muat", "Refresh")]

    def __init__(self, pegawai):
        super().__init__()
        self.p = pegawai

    def compose(self):
        yield Header(show_clock=True)
        yield profil(self.p["nama_pegawai"], "Pegawai Koperasi",
                     f"@{self.p.get('username', '')}   •   Sedang bertugas", "staff")
        with TabbedContent():
            with TabPane("📋 Antrean Pesanan", id="t-antrean"):
                with Horizontal(id="stats"):
                    yield Static("", id="st-proses", classes="stat")
                    yield Static("", id="st-selesai", classes="stat")
                    yield Static("", id="st-tuntas", classes="stat")
                with Horizontal(classes="cols"):
                    with Vertical(classes="panel", id="pn-antrean") as p:
                        p.border_title = "Antrean Pesanan Masuk"
                        yield DataTable(id="tbl-antrean", cursor_type="row", zebra_stripes=True)
                        with Horizontal(classes="toolbar"):
                            yield Button("⏩ Naikkan Status Pesanan", variant="success", id="btn-status")
                    with Vertical(classes="panel", id="pn-detail") as p:
                        p.border_title = "Detail Pesanan"
                        with VerticalScroll():
                            yield Static("", id="detail")
            with TabPane("📦 Stok Barang", id="t-stok"):
                with Horizontal(classes="cols"):
                    with Vertical(classes="panel", id="pn-stok") as p:
                        p.border_title = "Daftar Stok Barang ATK"
                        yield DataTable(id="tbl-stok", cursor_type="row", zebra_stripes=True)
                    with Vertical(classes="panel form", id="pn-form") as p:
                        p.border_title = "Form Barang"
                        with VerticalScroll():
                            yield kolom("Nama Barang (untuk barang baru)",
                                        Input(id="s-nama", max_length=64))
                            yield kolom("Harga (Rp)", Input(id="s-harga", type="integer", max_length=9))
                            yield kolom("Stok", Input(id="s-stok", type="integer", max_length=6))
                            yield Button("➕ Tambah Barang Baru", variant="success", id="b-tambah")
                            yield Button("Set Stok (baris dipilih)", variant="primary", id="b-stok")
                            yield Button("Set Harga (baris dipilih)", variant="warning", id="b-harga")
            with TabPane("🗂 Arsip Nota & Sistem", id="t-arsip"):
                with Vertical(classes="panel info") as p:
                    p.border_title = "Informasi Sistem"
                    yield Static("", id="sysinfo")
                with Vertical(classes="panel", id="pn-arsip") as p:
                    p.border_title = "File Nota Tersimpan"
                    yield DataTable(id="tbl-arsip", cursor_type="row", zebra_stripes=True)
                with Vertical(classes="panel", id="pn-isi") as p:
                    p.border_title = "Isi Nota"
                    with VerticalScroll():
                        yield Static("", id="arsip-isi")
        yield Footer()

    def on_mount(self):
        self.query_one("#tbl-antrean", DataTable).add_columns(
            "NO", "KODE", "COSTUMER", "SPESIFIKASI", "STATUS")
        self.query_one("#tbl-stok", DataTable).add_columns("ID", "NAMA BARANG", "HARGA", "STOK")
        self.query_one("#tbl-arsip", DataTable).add_columns("FILE", "UKURAN", "WAKTU SIMPAN")
        info = tampilan.info_lingkungan_os()
        self.query_one("#sysinfo", Static).update(Text(
            f"Sistem : {info['sistem']}   |   Pengguna OS : {info['pengguna_os']}\n"
            f"Folder Aplikasi : {database.BASE_DIR}\nFolder Nota     : {FOLDER_NOTA}"))
        self.action_muat()
        self.set_interval(5, self.muat_antrean)

    def action_muat(self):
        self.muat_antrean()
        self.muat_stok()
        self.muat_arsip()

    def action_logout(self):
        self.app.notify("Anda telah logout.")
        self.app.pop_screen()

    # --- antrean
    def muat_antrean(self):
        try:
            conn = koneksi()
        except ConnectionError as err:
            return self.app.notify(str(err), severity="error")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM pesanan WHERE status_pesanan != 'Tuntas' ORDER BY urutan")
                antrean = cur.fetchall()
                cur.execute("SELECT status_pesanan, COUNT(*) AS n FROM pesanan GROUP BY 1")
                hitung = {r["status_pesanan"]: r["n"] for r in cur.fetchall()}
            baris = [(p["kode_booking"], (
                f"{no}.", p["kode_booking"], p["nama_pemesan"], ringkas_spesifikasi(conn, p),
                Text(p["status_pesanan"].upper(), style=gaya_status(p['status_pesanan']))))
                for no, p in enumerate(antrean, 1)]
        except psycopg2.Error as err:
            return self.app.notify(galat_db(err), severity="error")
        finally:
            conn.close()
        isi_tabel(self.query_one("#tbl-antrean", DataTable), baris)
        for id_, nm in (("#st-proses", "Diproses"), ("#st-selesai", "Selesai"),
                        ("#st-tuntas", "Tuntas")):
            self.query_one(id_, Static).update(Text.assemble(
                (f"{nm}: ", "bold"), (str(hitung.get(nm, 0)), gaya_status(nm))))
        if not baris:
            self.query_one("#detail", Static).update(Text("Belum ada pesanan dalam antrean.", style="dim"))
        else:
            self.tampil_detail(baris_terpilih(self.query_one("#tbl-antrean", DataTable)))

    def tampil_detail(self, kode):
        pnl = self.query_one("#detail", Static)
        if not kode:
            return
        try:
            conn = koneksi()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM pesanan WHERE kode_booking=%s", (kode,))
                    p = cur.fetchone()
                    if not p:
                        return
                    baris = [f"Kode Booking : {kode}", f"Costumer     : {p['nama_pemesan']}",
                             f"Tanggal      : {format_tanggal(p['tanggal_pesan'])}"]
                    if p["jenis_pesanan"] == "PRINT":
                        cur.execute("SELECT * FROM booking_print WHERE kode_booking=%s", (kode,))
                        b = cur.fetchone()
                        if b:
                            baris += [f"Link Drive   : {b['nama_link_file']}",
                                      f"Spesifikasi  : {ringkas_spesifikasi(conn, p)}",
                                      f"Tipe Cetak   : {b['tipe_cetak']}  |  "
                                      f"{b['jumlah_lembar']} lbr x {b['jumlah_eksemplar']} eks"]
                    else:
                        cur.execute("SELECT * FROM detail_atk WHERE kode_booking=%s ORDER BY id_detail", (kode,))
                        for it in cur.fetchall():
                            baris.append(f"  - [{format_id_barang(it['id_barang'])}] {it['nama_barang']} "
                                         f"x{it['jumlah']} = {rupiah(it['subtotal'])}")
                    baris.append(f"Total        : {rupiah(p['total_biaya'])}")
            finally:
                conn.close()
        except (ConnectionError, psycopg2.Error):
            return
        pnl.update("\n".join(baris))

    @on(DataTable.RowHighlighted, "#tbl-antrean")
    def _sorot(self, ev):
        if ev.row_key is not None and ev.row_key.value:
            self.tampil_detail(ev.row_key.value)

    @on(DataTable.RowHighlighted, "#tbl-arsip")
    def _sorot_arsip(self, ev):
        if ev.row_key is None or not ev.row_key.value:
            return
        try:
            with open(os.path.join(FOLDER_NOTA, ev.row_key.value), encoding="utf-8") as f:
                self.query_one("#arsip-isi", Static).update(Text(f.read().rstrip()))
        except OSError:
            pass

    @on(Button.Pressed, "#btn-status")
    def naik_status(self):
        kode = baris_terpilih(self.query_one("#tbl-antrean", DataTable))
        if not kode:
            return self.app.notify("Pilih pesanan terlebih dahulu.", severity="warning")
        try:
            p = query("SELECT * FROM pesanan WHERE kode_booking=%s", (kode,), satu=True)
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        if not p:
            return
        pos = URUTAN_STATUS.index(p["status_pesanan"])
        if pos == len(URUTAN_STATUS) - 1:
            return self.app.notify("Pesanan sudah tuntas.", severity="warning")
        baru = URUTAN_STATUS[pos + 1]
        pesan = f"Ubah status {kode} menjadi {baru.upper()}?"
        if baru == "Tuntas":
            pesan += "\n\n⚠ Pastikan Kode Booking sesuai nota & pembayaran sudah diterima."
        self.app.push_screen(KonfirmasiModal(pesan, "Ubah Status"),
                             lambda ok: self._simpan_status(ok, kode, baru))

    def _simpan_status(self, ok, kode, baru):
        if not ok:
            return
        try:
            eksekusi("UPDATE pesanan SET status_pesanan=%s WHERE kode_booking=%s", (baru, kode))
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        self.app.notify(f"{kode} → {baru.upper()}", title="Status diubah")
        self.muat_antrean()

    # --- stok
    def muat_stok(self):
        try:
            rows = query("SELECT * FROM barang ORDER BY id_barang")
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        isi_tabel(self.query_one("#tbl-stok", DataTable), [
            (b["id_barang"], (format_id_barang(b["id_barang"]), b["nama_barang"],
                              rupiah(b["harga_satuan"]),
                              Text("Habis", style=f"bold {w('err')}") if b["stok_tersedia"] == 0
                              else str(b["stok_tersedia"]))) for b in rows])

    def _in(self, id_):
        return self.query_one(id_, Input)

    @on(Button.Pressed, "#b-tambah")
    def tambah_barang(self):
        nama = " ".join(self._in("#s-nama").value.split())
        if not (3 <= len(nama) <= 64 and re.fullmatch(r"[a-zA-Z0-9\s.,/&+-]+", nama)
                and len(re.findall(r"[a-zA-Z]", nama)) >= 2):
            return self.app.notify("Nama barang 3-64 karakter, tanpa simbol terlarang.", severity="error")
        harga, g1 = angka(self._in("#s-harga").value, "Harga", HARGA_MINIMUM, HARGA_MAKSIMUM)
        stok, g2 = angka(self._in("#s-stok").value, "Stok", 0, STOK_MAKSIMUM)
        if g1 or g2:
            return self.app.notify(g1 or g2, severity="error")
        try:
            dup = query("SELECT id_barang FROM barang WHERE LOWER(nama_barang)=LOWER(%s)", (nama,), satu=True)
            if dup:
                return self.app.notify(f"Sudah terdaftar: {format_id_barang(dup['id_barang'])}.", severity="error")
            eksekusi("INSERT INTO barang (nama_barang, harga_satuan, stok_tersedia) VALUES (%s,%s,%s)",
                     (nama, harga, stok))
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        for i in ("#s-nama", "#s-harga", "#s-stok"):
            self._in(i).value = ""
        self.app.notify(f"{nama} ditambahkan.", title="Stok")
        self.muat_stok()

    def _ubah_barang(self, kolom, nilai_input, nama, mn, mx):
        idb = baris_terpilih(self.query_one("#tbl-stok", DataTable))
        if idb is None:
            return self.app.notify("Pilih barang pada tabel.", severity="warning")
        n, galat = angka(self._in(nilai_input).value, nama, mn, mx)
        if galat:
            return self.app.notify(galat, severity="error")
        try:
            eksekusi(f"UPDATE barang SET {kolom}=%s WHERE id_barang=%s", (n, int(idb)))
        except (ConnectionError, psycopg2.Error) as err:
            return self.app.notify(galat_db(err), severity="error")
        self.app.notify(f"{nama} {format_id_barang(idb)} → {n}", title="Diperbarui")
        self.muat_stok()

    @on(Button.Pressed, "#b-stok")
    def set_stok(self):
        self._ubah_barang("stok_tersedia", "#s-stok", "Stok", 0, STOK_MAKSIMUM)

    @on(Button.Pressed, "#b-harga")
    def set_harga(self):
        self._ubah_barang("harga_satuan", "#s-harga", "Harga", HARGA_MINIMUM, HARGA_MAKSIMUM)

    # --- arsip
    def muat_arsip(self):
        try:
            os.makedirs(FOLDER_NOTA, exist_ok=True)
            files = sorted(f for f in os.listdir(FOLDER_NOTA) if f.endswith(".txt"))
        except OSError:
            return
        baris = []
        for f in files:
            pth = os.path.join(FOLDER_NOTA, f)
            baris.append((f, (f, f"{os.path.getsize(pth)} B",
                              datetime.fromtimestamp(os.path.getmtime(pth)).strftime("%d/%m/%Y %H:%M"))))
        isi_tabel(self.query_one("#tbl-arsip", DataTable), baris)


# ───────────────────────── app ─────────────────────────
class SikoprintApp(App):
    TITLE = "SI-KOPRINT"
    SUB_TITLE = "Sistem Informasi Koperasi dan Layanan Booking Printing"
    BINDINGS = [Binding("ctrl+q", "quit", "Keluar"), Binding("ctrl+t", "ganti_tema", "Tema Terang/Gelap")]

    CSS = """
    Screen { background: $background; color: $foreground; }

    /* ── kerangka umum ── */
    Button:focus { text-style: bold; }
    Button.-active { text-style: bold; }
    TabbedContent { height: 1fr; }
    TabbedContent > ContentSwitcher { height: 1fr; }
    TabPane { height: 1fr; padding: 0 0 0 1; }
    #profil { height: 5; margin: 0 1; padding: 0 1; background: $surface;
              border: round $primary; }
    #profil.staff { border: round $accent; }
    .avatar { width: 7; height: 3; content-align: center middle; text-style: bold;
              background: $primary; color: auto 95%; margin-right: 2; }
    #profil.staff .avatar { background: $accent; }
    .p-info { width: 1fr; height: 3; align: left middle; }
    .p-nama { height: 1; width: 100%; text-style: bold; color: $text; }
    .p-detail { height: 1; width: 100%; color: $text-muted; }
    .p-aksi { width: auto; height: 3; content-align: right middle; color: $text-muted; }
    .cols { height: 1fr; }
    .panel { background: $surface; border: round $primary; border-title-color: $accent; border-title-style: bold;
             padding: 0 1; height: 1fr; width: 1fr; margin-right: 1; }
    .panel DataTable { height: 1fr; border: none; padding: 0; }
    .panel.form, .panel.info { height: auto; }
    .toolbar { height: auto; margin-top: 1; }
    .toolbar Label { height: 3; content-align: left middle; padding-right: 1; }
    .toolbar Input { width: 12; margin-right: 1; }
    .toolbar Button { margin-right: 1; }
    .row { height: auto; }
    .col { height: auto; width: 1fr; margin-right: 1; margin-top: 1; }
    .col Label { color: $text-muted; }
    .pesan { margin-top: 1; height: auto; }

    /* ── welcome ── */
    WelcomeScreen { align: center middle; }
    #welcome { width: 100%; height: auto; }
    Center { width: 100%; height: auto; }
    .banner { width: auto; height: auto; }
    .logo { width: auto; height: auto; color: $accent; text-style: bold; }
    .judul-logo { width: auto; height: auto; color: $primary; text-style: bold; margin-left: 2; }
    #peran-box { width: 56; max-width: 100%; height: auto; margin-top: 1; padding: 1 3;
                 background: $surface; border: round $primary;
                 border-title-color: $accent; border-title-style: bold; align: center top; }
    #sub { width: 100%; text-align: center; color: $text-muted; margin-bottom: 1; }
    #peran-box Button { width: 100%; margin-bottom: 1; }
    #peran-box #btn-keluar { margin-bottom: 0; }
    DataTable { background: $surface; }
    Input { background: $background; }
    Select > SelectCurrent { background: $background; }

    /* ── auth ── */
    AuthScreen { align: center middle; }
    #auth-box { background: $surface; width: 76; max-width: 100%; height: auto; max-height: 100%;
                border: round $primary; border-title-color: $accent; border-title-style: bold;
                padding: 1 2; overflow-y: auto; }
    #auth-judul { width: 100%; text-align: center; margin-bottom: 1; color: $primary; text-style: bold; }
    #auth-box TabbedContent { height: auto; }
    #auth-box ContentSwitcher { height: auto; }
    #auth-box TabPane { height: auto; padding: 0; }
    #auth-box Button { width: 100%; margin-top: 1; }

    /* ── customer ── */
    #tbl-katalog, #tbl-cart { height: 1fr; }
    #total-cart { height: auto; padding: 0 1; margin-top: 1; color: $warning; text-style: bold; }
    #p-estimasi { height: auto; border: round $warning; padding: 0 1; margin: 1 0; color: $warning; text-style: bold; }
    #p-pesan { width: 100%; }

    /* ── pegawai ── */
    #stats { height: 3; margin-bottom: 0; }
    .stat { width: 1fr; height: 3; background: $surface; border: round $secondary; content-align: center middle;
            margin-right: 1; }
    #pn-antrean { width: 3fr; }
    #pn-detail { width: 2fr; }
    #detail { height: auto; width: 100%; }
    #pn-stok { width: 3fr; }
    #pn-form { width: 2fr; height: 1fr; }
    #pn-form Button { width: 100%; margin-top: 1; }
    #sysinfo { height: auto; color: $secondary; }
    #pn-arsip { height: 10; margin-right: 0; }
    #pn-isi { margin-right: 0; }

    /* ── modal ── */
    KonfirmasiModal, NotaModal { align: center middle; background: $background 70%; }
    #dialog { width: 92; max-width: 98%; height: auto; max-height: 92%; border: thick $primary;
              background: $panel; padding: 1 2; overflow-y: auto; }
    #dialog-judul { text-style: bold; color: $accent; width: 100%; text-align: center; margin-bottom: 1; }
    #dialog-aksi { height: auto; align: center middle; margin-top: 1; }
    #dialog-aksi Button { margin: 0 2; }
    #nota-box { width: 92; max-width: 98%; height: 92%; border: thick $success;
                background: $panel; padding: 1 2; }
    #nota-scroll { height: 1fr; }
    #nota-box Button { width: 100%; margin-top: 1; }
    """

    def on_mount(self):
        self.register_theme(THEME_GELAP)
        self.register_theme(THEME_TERANG)
        try:
            with open(TEMA_FILE, encoding="utf-8") as f:
                TEMA["gelap"] = f.read().strip() != "terang"
        except OSError:
            pass
        self._terapkan_tema()
        self.push_screen(WelcomeScreen())
        self.siapkan_db()

    def _terapkan_tema(self):
        self.theme = "sikoprint-gelap" if TEMA["gelap"] else "sikoprint-terang"

    def action_ganti_tema(self):
        TEMA["gelap"] = not TEMA["gelap"]
        self._terapkan_tema()
        try:
            with open(TEMA_FILE, "w", encoding="utf-8") as f:
                f.write("gelap" if TEMA["gelap"] else "terang")
        except OSError:
            pass
        # render ulang sel tabel berwarna agar mengikuti tema
        muat = getattr(self.screen, "action_muat", None)
        if callable(muat):
            muat()
        self.notify("Tema " + ("GELAP" if TEMA["gelap"] else "TERANG"), title="Tema")

    # --- inisialisasi database (tanpa input() konsol)
    def siapkan_db(self):
        try:
            conn = koneksi()
            try:
                with conn.cursor() as cur:
                    lama = _skema_lama_terdeteksi(cur)
            finally:
                conn.close()
        except (ConnectionError, psycopg2.Error) as err:
            return self.push_screen(NotaModal(galat_db(err), "Koneksi database gagal"),
                                    lambda _: self.exit())
        if lama:
            self.push_screen(
                KonfirmasiModal("Terdeteksi struktur tabel lama.\nPerbarui tabel otomatis? "
                                "(SEMUA data lama akan dihapus)", "Skema Lama"),
                self._konfirmasi_reset)
        else:
            self._init_db(False)

    def _konfirmasi_reset(self, setuju):
        if setuju:
            self._init_db(True)
        else:
            self.exit(message="Pembaruan tabel dibatalkan. Jalankan schema_sikoprint.sql di pgAdmin.")

    def _init_db(self, reset):
        conn = koneksi()
        try:
            with conn.cursor() as cur:
                if reset:
                    cur.execute("DROP TABLE IF EXISTS detail_atk, booking_print, pesanan, "
                                "barang, customer, pegawai CASCADE")
                cur.execute(DDL_SKEMA)
                _selaraskan_kolom_telepon(cur)
            conn.commit()
            isi_data_awal()
        except psycopg2.Error as err:
            conn.rollback()
            self.push_screen(NotaModal(galat_db(err), "Inisialisasi database gagal"),
                             lambda _: self.exit())
        finally:
            conn.close()


def jalankan():
    SikoprintApp().run()


if __name__ == "__main__":
    jalankan()
