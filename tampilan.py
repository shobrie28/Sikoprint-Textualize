import os
import re
import sys
import time
import getpass
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import builtins

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH_AKTIF = True
except ImportError:  # fallback: tampilan polos bila rich belum terpasang
    RICH_AKTIF = False


def aktifkan_utf8_konsol():
    """Memastikan stdout/stderr mendukung karakter UTF-8 di konsol."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if os.name == "nt":
        try:
            os.system("")
        except Exception:
            pass


aktifkan_utf8_konsol()

LEBAR_DEFAULT = 81
HARGA_MINIMUM = 500
HARGA_MAKSIMUM = 100_000_000
STOK_MINIMUM = 0
STOK_MAKSIMUM = 100_000
TOTAL_MAKSIMUM = 2_000_000_000

MAKS_REFRESH_INPUT = 5
JEDA_REFRESH_DETIK = 0.15
_waktu_refresh_terakhir = 0.0


class BatasRefreshError(Exception):
    """Dilemparkan saat batas maksimal refresh input tercapai."""


def lebar_layar():
    """Mengambil lebar terminal aktif via os.get_terminal_size."""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def bersihkan_layar():
    """Membersihkan layar konsol menggunakan modul os lintas sistem operasi."""
    global _waktu_refresh_terakhir
    sekarang = time.monotonic()
    selisih = sekarang - _waktu_refresh_terakhir
    if selisih < JEDA_REFRESH_DETIK:
        time.sleep(JEDA_REFRESH_DETIK - selisih)
    _waktu_refresh_terakhir = time.monotonic()
    try:
        perintah = "cls" if os.name == "nt" else "clear"
        os.system(perintah)
    except Exception:
        pass


def _baca_input(prompt):
    try:
        return input(prompt)
    except EOFError:
        raise KeyboardInterrupt


def jeda_layar(pesan="\nTekan [Enter] untuk melanjutkan..."):
    """Menahan tampilan layar sebelum berpindah menu."""
    _baca_input(pesan)


def info_lingkungan_os():
    """Mengembalikan informasi sistem operasi dan direktori kerja saat ini."""
    sistem = "Windows" if os.name == "nt" else f"POSIX ({os.name})"
    pengguna_os = os.environ.get("USERNAME") or os.environ.get("USER") or "pegawai"
    return {
        "sistem": sistem,
        "pengguna_os": pengguna_os,
        "cwd": os.getcwd(),
    }


_print_asli = builtins.print
_console = Console(highlight=False, soft_wrap=True) if RICH_AKTIF else None

_GAYA_PREFIKS = (
    ("[OK]", "bold green"),
    ("[X]", "bold red"),
    ("[!]", "bold yellow"),
)


def _cetak_rich(*args, sep=" ", end="\n", file=None, flush=False):
    """Pengganti print(): pesan [OK]/[X]/[!] diberi warna, nomor menu [1] disorot."""
    if file is not None or not RICH_AKTIF:
        return _print_asli(*args, sep=sep, end=end, file=file, flush=flush)
    teks = Text(sep.join(str(a) for a in args))
    plain = teks.plain.lstrip()
    for prefiks, gaya in _GAYA_PREFIKS:
        if plain.startswith(prefiks):
            teks.stylize(gaya)
            break
    else:
        teks.highlight_regex(r"\[\d+\]", "bold cyan")
        teks.highlight_regex(r"\[ATK\d+\]", "bold cyan")
        if plain.startswith(("TOTAL", "PILIH", "ISI KERANJANG")):
            teks.stylize("bold")
    _console.print(teks, end=end)


builtins.print = _cetak_rich


def garis(karakter="="):
    if RICH_AKTIF:
        _console.print(Text(karakter * LEBAR_DEFAULT, style="dim cyan"))
    else:
        _print_asli(karakter * LEBAR_DEFAULT)


def judul(teks):
    if RICH_AKTIF:
        _console.print(Panel(Text(teks, style="bold white", justify="center"),
                             box=box.DOUBLE, border_style="cyan",
                             width=LEBAR_DEFAULT))
    else:
        garis("=")
        _print_asli(teks.center(LEBAR_DEFAULT))
        garis("=")


def buat_tabel(kolom, baris, judul_tabel=None):
    """Tabel Rich. kolom: [(nama, justify)], baris: list tuple string."""
    if not RICH_AKTIF:
        return False
    t = Table(box=box.ROUNDED, border_style="cyan", header_style="bold magenta",
              row_styles=["", "dim"], width=LEBAR_DEFAULT, title=judul_tabel)
    for nama, justify in kolom:
        t.add_column(nama, justify=justify, overflow="fold")
    for b in baris:
        t.add_row(*[str(x) for x in b])
    _console.print(t)
    return True


GEDUNG_PRINTER_ASCII = [
    "    ╔═════╗    ",
    "╔═══╣ ▪ ▪ ╠═══╗",
    "║ ▪ ║ ▪ ▪ ║ ▪ ║",
    "║ ▪  ┌───┐  ▪ ║",
    "║  ┌─┴───┴─┐  ║",
    "║  │ ▄▄▄▄▄ │  ║",
    "║  └─┬───┬─┘  ║",
    "╚════╧═══╧════╝",
]

TEKS_SIKOPRINT_ASCII = [
    "█████ ████     ██  ██  ████  █████  █████  ████ ███  ██ ██████",
    "██     ██      ██ ██  ██  ██ ██  ██ ██  ██  ██  ████ ██   ██  ",
    "█████  ██  ███ ████   ██  ██ █████  █████   ██  ██ ████   ██  ",
    "   ██  ██      ██ ██  ██  ██ ██     ██ ██   ██  ██  ███   ██  ",
    "█████ ████     ██  ██  ████  ██     ██  ██ ████ ██   ██   ██  ",
    "──────────────────────────────────────────────────────────────",
    "    Sistem Informasi Koperasi dan Layanan Booking Printing    ",
    "──────────────────────────────────────────────────────────────",
]


def cetak_header_utama():
    """Menampilkan header utama SI-KOPRINT agar tetap muncul di setiap halaman."""
    if not RICH_AKTIF:
        _print_asli("═" * LEBAR_DEFAULT)
        for gedung in GEDUNG_PRINTER_ASCII:
            _print_asli(gedung.center(LEBAR_DEFAULT))
        for teks in TEKS_SIKOPRINT_ASCII:
            _print_asli(teks.strip().center(LEBAR_DEFAULT))
        _print_asli("═" * LEBAR_DEFAULT)
        return
    if lebar_layar() >= LEBAR_DEFAULT:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(no_wrap=True)
        grid.add_column(no_wrap=True)
        for g, t in zip(GEDUNG_PRINTER_ASCII, TEKS_SIKOPRINT_ASCII):
            grid.add_row(Text(g, style="bold yellow"), Text(t, style="bold cyan"))
        isi = grid
    else:
        isi = Text("\n".join(
            [g for g in GEDUNG_PRINTER_ASCII] + [""] +
            [t.strip() for t in TEKS_SIKOPRINT_ASCII]),
            style="bold cyan", justify="center")
    _console.print(Panel(isi, box=box.DOUBLE_EDGE, border_style="blue",
                         width=LEBAR_DEFAULT, padding=(0, 1)))


def segarkan_halaman(judul_halaman=None, info_baris=None, pesan_error=None):
    """
    Membersihkan layar via os dan merender ulang header utama beserta konteks halaman
    agar tampilan tidak menumpuk saat terjadi kesalahan atau input kosong.
    """
    bersihkan_layar()
    cetak_header_utama()
    if judul_halaman:
        judul(judul_halaman)
    if info_baris:
        for baris in info_baris:
            print(baris)
        garis("-")
    if pesan_error:
        print(pesan_error)


def _proses_refresh_input(jumlah_refresh, render_ulang, pesan_error):
    """Mengelola pembatasan refresh dan penyegaran layar pada setiap kesalahan input."""
    if jumlah_refresh >= MAKS_REFRESH_INPUT:
        raise BatasRefreshError(
            f"[!] Batas maksimal refresh input tercapai ({MAKS_REFRESH_INPUT}x). "
            "Kembali ke menu sebelumnya."
        )
    if render_ulang is not None:
        render_ulang(pesan_error)
    else:
        segarkan_halaman(pesan_error=pesan_error)


def rupiah(angka):
    nilai = int(round(angka)) if isinstance(angka, (Decimal, float)) else int(angka)
    return "Rp " + f"{nilai:,}".replace(",", ".")


def format_id_barang(id_barang):
    """Menampilkan ID integer dari database menjadi format ATK01."""
    return f"ATK{int(id_barang):02d}"


def parse_id_barang(teks):
    """Mengonversi input ID Barang (ATK01, atk01, 1) menjadi integer >= 1."""
    if teks is None:
        return None
    bersih = teks.strip().upper()
    if not bersih:
        return None
    cocok = re.fullmatch(r"(?:ATK[- ]?)?0*([1-9][0-9]*)", bersih)
    if not cocok:
        return None
    nomor = int(cocok.group(1))
    if nomor <= 0 or nomor > 2_000_000_000:
        return None
    return nomor


def waktu_sekarang():
    """Mengembalikan objek datetime WIB untuk kolom TIMESTAMP PostgreSQL."""
    wib = timezone(timedelta(hours=7))
    return datetime.now(wib).replace(tzinfo=None, microsecond=0)


def format_tanggal(dt):
    """Memformat TIMESTAMP PostgreSQL menjadi string tanggal yang rapi."""
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y %H:%M") + " WIB"
    return str(dt)


def _analisis_integer(teks):
    """
    Memeriksa string bilangan bulat ASCII.
    Mengembalikan tuple (nilai_int_atau_None, pesan_error_atau_None).
    """
    teks = teks.strip()
    if not teks:
        return None, None
    if re.fullmatch(r"[+-]?[0-9]+[.,][0-9]+", teks):
        return None, "[X] Input harus berupa bilangan bulat, bukan desimal."
    if teks.startswith("-"):
        bagian_angka = teks[1:]
        if bagian_angka.isascii() and bagian_angka.isdigit():
            return -int(bagian_angka), None
        return None, "[X] Input harus berupa angka bulat."
    if teks.startswith("+"):
        bagian_angka = teks[1:]
        if bagian_angka.isascii() and bagian_angka.isdigit():
            return int(bagian_angka), None
        return None, "[X] Input harus berupa angka bulat."
    if teks.isascii() and teks.isdigit():
        return int(teks), None
    return None, "[X] Input harus berupa angka bulat."


def input_teks(prompt, min_panjang=1, maks_panjang=255, label="Isian", render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        if len(isi) < min_panjang:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] {label} minimal {min_panjang} karakter."
            )
            continue
        if len(isi) > maks_panjang:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] {label} maksimal {maks_panjang} karakter."
            )
            continue
        return isi


def input_username(prompt, min_panjang=4, maks_panjang=64, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        if "@" in isi:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Username tidak boleh menggunakan format email."
            )
            continue
        if " " in isi:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Username tidak boleh mengandung spasi."
            )
            continue
        if not (min_panjang <= len(isi) <= maks_panjang):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Panjang username harus {min_panjang} sampai {maks_panjang} karakter."
            )
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_]+", isi):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Username hanya boleh berisi huruf, angka, dan garis bawah."
            )
            continue
        if not re.search(r"[a-zA-Z]", isi):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Username harus mengandung minimal 1 huruf."
            )
            continue
        return isi


def input_nama(prompt, min_panjang=2, maks_panjang=64, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = " ".join(_baca_input(prompt).strip().split())
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        if "@" in isi:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Nama tidak boleh menggunakan format email."
            )
            continue
        if re.search(r"[0-9]", isi):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Nama tidak boleh mengandung angka."
            )
            continue
        if not (min_panjang <= len(isi) <= maks_panjang):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Panjang nama harus {min_panjang} sampai {maks_panjang} karakter."
            )
            continue
        if not re.fullmatch(r"[a-zA-Z\s'.-]+", isi):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Nama hanya boleh berisi huruf, spasi, titik, apostrof, atau tanda hubung."
            )
            continue
        if len(re.findall(r"[a-zA-Z]", isi)) < 2:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Nama harus mengandung minimal 2 huruf."
            )
            continue
        return isi


def input_password(prompt, min_panjang=6, maks_panjang=64, render_ulang=None):
    jumlah_refresh = 0
    while True:
        try:
            isi = getpass.getpass(prompt)
        except EOFError:
            raise KeyboardInterrupt
        if not isi or not isi.strip():
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        if " " in isi:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Password tidak boleh mengandung spasi."
            )
            continue
        if len(isi) < min_panjang:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Password minimal {min_panjang} karakter."
            )
            continue
        if len(isi) > maks_panjang:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Password maksimal {maks_panjang} karakter."
            )
            continue
        return isi


def input_pilihan(prompt, minimum, maksimum, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        nilai, galat = _analisis_integer(isi)
        if nilai is None:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Pilihan harus berupa angka bulat antara {minimum} sampai {maksimum}."
            )
            continue
        if not (minimum <= nilai <= maksimum):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Pilihan di luar jangkauan. Masukkan angka {minimum} sampai {maksimum}."
            )
            continue
        return nilai


def input_angka(prompt, minimum=1, maksimum=1_000_000, label="Jumlah", render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        nilai, galat = _analisis_integer(isi)
        if nilai is None:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, galat)
            continue
        if nilai < 0:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] {label} tidak boleh bernilai negatif."
            )
            continue
        if nilai < minimum:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] {label} minimal adalah {minimum}."
            )
            continue
        if maksimum is not None and nilai > maksimum:
            maks_teks = f"{maksimum:,}".replace(",", ".")
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] {label} maksimal adalah {maks_teks}."
            )
            continue
        return nilai


def input_harga(prompt, minimum=HARGA_MINIMUM, maksimum=HARGA_MAKSIMUM, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        nilai, galat = _analisis_integer(isi)
        if nilai is None:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, galat)
            continue
        if nilai < 0:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Harga tidak boleh bernilai negatif."
            )
            continue
        if nilai < minimum:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Harga minimal adalah {rupiah(minimum)}."
            )
            continue
        if nilai > maksimum:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Harga maksimal adalah {rupiah(maksimum)}."
            )
            continue
        return nilai


def input_stok(prompt, minimum=STOK_MINIMUM, maksimum=STOK_MAKSIMUM, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        nilai, galat = _analisis_integer(isi)
        if nilai is None:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, galat)
            continue
        if nilai < 0:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] Stok tidak boleh bernilai negatif."
            )
            continue
        if nilai < minimum:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Stok minimal adalah {minimum}."
            )
            continue
        if nilai > maksimum:
            maks_teks = f"{maksimum:,}".replace(",", ".")
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                f"[X] Stok maksimal adalah {maks_teks}."
            )
            continue
        return nilai


def input_telepon(prompt, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        if "@" in isi or re.search(r"\.[a-zA-Z]{2,}$", isi):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] No. telepon tidak boleh menggunakan format email."
            )
            continue
        if re.search(r"[a-zA-Z]", isi):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] No. telepon tidak boleh mengandung huruf."
            )
            continue
        if not (isi.isascii() and isi.isdigit()):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] No. telepon hanya boleh berisi angka 0 sampai 9."
            )
            continue
        if not isi.startswith("08"):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] No. telepon harus diawali dengan 08."
            )
            continue
        if not (10 <= len(isi) <= 13):
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] No. telepon harus terdiri dari 10 sampai 13 digit."
            )
            continue
        if len(set(isi[2:])) == 1:
            jumlah_refresh += 1
            _proses_refresh_input(
                jumlah_refresh, render_ulang,
                "[X] No. telepon tidak valid."
            )
            continue
        return isi


def konfirmasi(prompt, render_ulang=None):
    jumlah_refresh = 0
    while True:
        isi = _baca_input(prompt).strip().upper()
        if not isi:
            jumlah_refresh += 1
            _proses_refresh_input(jumlah_refresh, render_ulang, None)
            continue
        if isi in ("Y", "T"):
            return isi == "Y"
        jumlah_refresh += 1
        _proses_refresh_input(
            jumlah_refresh, render_ulang,
            "[X] Input tidak valid. Ketik Y untuk Ya atau T untuk Tidak."
        )
