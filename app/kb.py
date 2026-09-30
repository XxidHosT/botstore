"""Basis pengetahuan + pencarian produk. Ganti ProductIndex dengan query DB (FTS/trigram) di produksi."""
import json, pathlib, yaml
from rapidfuzz import fuzz
from .nlu import normalize

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


class KB:
    noise = frozenset()                                       # kosakata intent (harga, stok, berapa...): bukan nama produk; diisi Bot setelah klasifikator dibuat

    def __init__(self):
        self.load()

    FILES = ("knowledge.yaml", "products.json", "learned.json")

    def stamp(self):
        """Tanda waktu berkas data; dipakai supaya setiap worker memuat ulang sendiri saat data berubah (reload di satu worker tak cukup)."""
        return tuple((DATA / f).stat().st_mtime_ns if (DATA / f).exists() else 0 for f in self.FILES)

    def load(self):
        self._stamp = self.stamp()
        k = yaml.safe_load((DATA / "knowledge.yaml").read_text(encoding="utf-8"))
        self.site, self.intents, self.texts = k["site"], k["intents"], k["texts"]
        self.products = self._load_products()
        self.tag_aliases = {tag: [normalize(a) for a in al] for tag, al in (k.get("tag_aliases") or {}).items()}
        learned = DATA / "learned.json"                       # contoh kalimat dari dasbor review; terpisah dari knowledge.yaml agar mudah dibatalkan
        if learned.exists():
            for intent, per_lang in json.loads(learned.read_text(encoding="utf-8")).items():
                if intent in self.intents:
                    for lang, exs in per_lang.items():
                        self.intents[intent]["examples"].setdefault(lang, []).extend(exs)

    def _load_products(self):
        return json.loads((DATA / "products.json").read_text(encoding="utf-8"))

    def _candidates(self, q):
        """Calon produk untuk dicocokkan dengan pesan. Katalog lokal: semuanya; katalog jarak jauh: hasil pencarian."""
        return list(self.products)

    def t(self, key, lang, **kw):
        return self.texts[key].get(lang, self.texts[key]["id"]).format(email=self.site["support_email"], **kw)

    def answer(self, intent, lang):
        a = self.intents[intent]["answer"]
        return (a.get(lang) or a["id"]).format(email=self.site["support_email"])

    def label(self, intent, lang):
        lab = self.intents[intent].get("label", {})
        return lab.get(lang) or lab.get("id") or intent

    def _best_alias(self, q, candidates):
        best = None
        for p in candidates:
            for alias in [p["name"]] + p["aliases"]:
                a = normalize(alias)
                if len(a) < 4 or len(a) > len(q) + 2:      # pesan yang cuma potongan nama ("steam key") bukan penyebutan produk
                    continue
                al = fuzz.partial_ratio_alignment(a, q)
                if al.score >= 88 and (best is None or (al.score, len(a)) > best[0]):
                    rest = (q[:al.dest_start] + " " + q[al.dest_end:]).strip() if len(a) <= len(q) else ""
                    best = ((al.score, len(a)), p, rest)
        return best

    def match_products(self, text, limit=3):
        """Semua produk yang disebut di pesan (urut kemunculan pencarian terbaik). Return (daftar_produk, sisa_teks)."""
        q0 = q = normalize(text)
        found, left = [], self._candidates(q0)
        while len(found) < limit:
            best = self._best_alias(q, left)
            if not best:
                break
            found.append(best[1]); q = best[2]; left = [p for p in left if p is not best[1]]

        def pos(p):     # urutan sesuai penyebutan di pesan asli
            hits = [fuzz.partial_ratio_alignment(normalize(a), q0) for a in [p["name"]] + p["aliases"] if len(normalize(a)) >= 4]
            return min((h.dest_start for h in hits if h.score >= 88), default=0)
        return sorted(found, key=pos), q

    def match_product(self, text):
        """Kompatibel dengan versi lama: satu produk saja."""
        found, rest = self.match_products(text, limit=1)
        return (found[0], rest) if found else (None, rest)

    STOP = set("ada apa yang mau cari beli game games produk murah dong nih ya kak min saya aku kamu punya jual gak tidak bisa untuk buat dan atau di ke dari the a an do you have any looking for want buy show me cheap".split())

    def search(self, text, k=3):
        toks = [t for t in normalize(text).split() if len(t) >= 3 and t not in self.STOP]
        if not toks:
            return []
        scored = []
        for p in self.products:
            words = normalize(" ".join([p["name"], p["category"]] + p["aliases"])).split()
            hit = sum(1 for t in toks if any(fuzz.ratio(t, w) >= 85 for w in words))
            if hit:
                scored.append((hit / len(toks), hit, p))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [p for _, _, p in scored[:k]]

    # ---------- katalog: filter, urutan, alternatif ----------
    CATEGORY_HINT = {"game", "games", "steam", "voucher", "topup", "top", "up", "roblox", "pc"}
    GENERIC = set("semua seluruh all every daftar list katalog rekomendasi recommend suggest something sesuatu saran produk apa aja saja dong lah ya nih game games yang buat untuk".split())

    def _words(self, p):
        return set(normalize(" ".join([p["name"], p["category"]] + p["aliases"])).split())

    def extract_tags(self, text, only=None):
        """(tag kanonik yang disebut, teks tanpa frasa tag). Kata tag tak boleh ikut dicocokkan ke nama produk atau dianggap 'tak dikenal'."""
        import re
        q, found = normalize(text), []
        for tag, aliases in self.tag_aliases.items():
            if only is not None and tag not in only: continue
            for a in sorted(aliases, key=len, reverse=True):
                if re.search(rf"\b{re.escape(a)}\b", q):
                    found.append(tag); q = re.sub(rf"\b{re.escape(a)}\b", " ", q)
                    break
        return found, " ".join(q.split())

    def has_tags(self, tags):
        """Adakah produk (stok apa pun) yang memuat semua tag ini?"""
        return any(set(tags) <= set(p.get("tags", [])) for p in self.products)

    def query(self, text="", max_price=None, min_price=None, sort=None, k=3, in_stock=True, tags=()):
        """Filter katalog: kata kategori dari teks + batas harga + urutan. Semua angka murni dari data."""
        toks = [t for t in normalize(text).split() if (len(t) >= 3 or t in self.CATEGORY_HINT) and t not in self.STOP and t not in self.GENERIC]
        toks += [t for t in normalize(text).split() if t in ("game", "games")]
        toks = [t.rstrip("s") if t == "games" else t for t in toks]
        pool = [p for p in self.products if (p["stock"] > 0 or not in_stock)]
        if tags: pool = [p for p in pool if set(tags) <= set(p.get("tags", []))]
        had_hit = False
        if toks:
            scored = []
            for p in pool:
                words = self._words(p)
                hit = sum(1 for t in toks if any(fuzz.ratio(t, w) >= 85 for w in words))
                if hit: scored.append((hit, p))
            top = max((h for h, _ in scored), default=0)
            had_hit = top > 0
            if had_hit: pool = [p for h, p in scored if h == top]     # tak ada kata yang cocok -> jangan kosongkan pool
        if max_price is not None: pool = [p for p in pool if p["price"] <= max_price]
        if min_price is not None: pool = [p for p in pool if p["price"] >= min_price]
        keys = {"cheap": lambda p: (p["price"], -p["rating"]), "pricey": lambda p: (-p["price"], -p["rating"]),
                "best": lambda p: (-p["rating"], p["price"])}
        return sorted(pool, key=keys.get(sort, keys["best"]))[:k], had_hit

    def unknown_terms(self, text, known=frozenset()):
        """Kata bermakna yang tidak dikenal katalog, kata umum, maupun kosakata intent (mis. 'horor', 'fifa').
        Dipakai supaya bot jujur soal batas datanya, bukan pura-pura paham."""
        from .nlu import FUNC
        vocab = set().union(*[self._words(p) for p in self.products]) | self.STOP | self.GENERIC | self.CATEGORY_HINT | set(known)
        return [t for t in normalize(text).split()
                if len(t) >= 3 and t not in FUNC and not any(c.isdigit() for c in t) and not any(fuzz.ratio(t, w) >= 80 for w in vocab)]

    def alternatives(self, prod, k=2, cheaper=False):
        """Produk lain yang tersedia dengan kategori mirip (kata kategori yang sama), opsional harus lebih murah."""
        cat = set(normalize(prod["category"]).split())
        cands = []
        for p in self.products:
            if p["id"] == prod["id"] or p["stock"] <= 0: continue
            if cheaper and p["price"] >= prod["price"]: continue
            shared = len(cat & set(normalize(p["category"]).split()))
            if shared: cands.append((-shared, -p["rating"], p["price"], p))
        cands.sort(key=lambda x: x[:3])
        return [c[3] for c in cands[:k]]


def make_kb():
    """Katalog dari website bila CATALOG_URL + CATALOG_TOKEN diisi; selain itu berkas lokal (dev/tes)."""
    import os
    url, token = os.getenv("CATALOG_URL", ""), os.getenv("CATALOG_TOKEN", "")
    if url and token:
        from .remote_kb import RemoteKB
        return RemoteKB(url, token, site_url=os.getenv("SITE_URL", ""))
    return KB()
