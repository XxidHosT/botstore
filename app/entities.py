"""Ekstraksi entitas dari teks mentah: batas harga, urutan (termurah/termahal/rating), nomor order.

Berjalan SEBELUM normalisasi karena normalize() membuang titik/koma ("100.000" -> "100 000").
Angka tanpa kata pembanding ("saldo steam 100rb") sengaja diabaikan: itu bagian nama produk, bukan anggaran.
"""
import re
from dataclasses import dataclass
from typing import Optional

_AMT = r"(?:rp\.?\s*)?(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(rb|ribu|k|jt|juta)?\b"
_MAX_PRE = r"(?:di\s?bawah|kurang\s+dari|under|below|less\s+than|max(?:imal|imum)?|maks(?:imal)?|budget(?:nya)?|tidak\s+lebih\s+dari|sampai|upto|up\s+to|<=?)"
_MIN_PRE = r"(?:di\s?atas|lebih\s+dari|over|above|more\s+than|min(?:imal|imum)?|>=?)"
_MAX_POST = r"\s*(?:ke\s?bawah|or\s+less|and\s+below|atau\s+kurang)"
_MIN_POST = r"\s*(?:ke\s?atas|or\s+more|and\s+above|atau\s+lebih)"

MAX_RX = [re.compile(r"(?<![a-z])" + _MAX_PRE + r"\s*:?\s*" + _AMT), re.compile(_AMT + _MAX_POST)]
MIN_RX = [re.compile(r"(?<![a-z])" + _MIN_PRE + r"\s*:?\s*" + _AMT), re.compile(_AMT + _MIN_POST)]

CHEAP = re.compile(r"\b(termurah|paling\s+murah|yang\s+murah|murah|cheapest|cheap|lowest\s+price|paling\s+terjangkau|terjangkau)\b")
PRICEY = re.compile(r"\b(termahal|paling\s+mahal|most\s+expensive|priciest|highest\s+price)\b")
BEST = re.compile(r"\b(terbaik|rating\s+tertinggi|paling\s+bagus|best\s+rated|top\s+rated|highest\s+rated|best|rekomen\w*|recommend\w*|suggest\w*|saran)\b")

ORDER_RX = [
    re.compile(r"#\s?([a-z]{2,5}[-_]?\d{3,}|\d{4,})\b", re.I),
    re.compile(r"\b((?:inv|ord|trx|jg|po)[-_]?\d{4,})\b", re.I),
    re.compile(r"\b(?:no|nomor|number|order|pesanan)\.?\s*(?:order|pesanan|id)?\s*[:#]?\s*((?:inv|ord|trx|jg)[-_]?\d{3,}|\d{5,})\b", re.I),
]


@dataclass
class Entities:
    text: str                       # teks tanpa frasa harga & nomor order (siap dinormalisasi)
    max_price: Optional[int] = None
    min_price: Optional[int] = None
    sort: Optional[str] = None      # "cheap" | "pricey" | "best"
    order_id: Optional[str] = None


def _to_int(num: str, unit: Optional[str]) -> Optional[int]:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", num):
        val = float(re.sub(r"[.,]", "", num))
    else:
        val = float(num.replace(",", "."))
    mult = {"rb": 1_000, "ribu": 1_000, "k": 1_000, "jt": 1_000_000, "juta": 1_000_000}.get(unit or "", 1)
    val *= mult
    return int(val) if val >= 1_000 else None          # "di bawah 5" bukan harga


def _first(rxs, text):
    for rx in rxs:
        m = rx.search(text)
        if m:
            v = _to_int(m.group(1), m.group(2))
            if v:
                return v, m.span()
    return None, None


def extract(text: str) -> Entities:
    t = text.lower()
    ent = Entities(text=t)
    for rx in ORDER_RX:                                  # nomor order dulu, agar tidak dikira harga/produk
        m = rx.search(t)
        if m:
            ent.order_id = m.group(1).upper().lstrip("#")
            t = t[:m.start()] + " " + t[m.end():]
            break
    for attr, rxs in (("max_price", MAX_RX), ("min_price", MIN_RX)):
        v, span = _first(rxs, t)
        if v:
            setattr(ent, attr, v)
            t = t[:span[0]] + " " + t[span[1]:]
    for name, rx in (("pricey", PRICEY), ("best", BEST), ("cheap", CHEAP)):
        if rx.search(t):
            ent.sort = ent.sort or name
            t = rx.sub(" ", t)                            # kata urutan bukan nama produk: jangan ikut dicocokkan ke katalog
    if ent.max_price and not ent.sort: ent.sort = "best"       # ada anggaran tapi tak minta "termurah" -> yang terbaik di dalam anggaran
    ent.text = re.sub(r"\s+", " ", t).strip()
    return ent
