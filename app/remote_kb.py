"""Katalog jarak jauh: produk, harga, dan stok dibaca LANGSUNG dari website (GET /api/bot/products), bukan salinan.
Sumbernya tabel yang sama dengan halaman /games, jadi harga yang disebut bot sama dengan yang dilihat pelanggan.
Cache pendek (30 dtk) hanya untuk meringankan beban; kegagalan katalog diteruskan sebagai CatalogUnavailable."""
import json, os, re, time, urllib.parse, urllib.request
from rapidfuzz import fuzz
from .kb import KB, DATA
from .nlu import normalize, FUNC

TTL = 30
NOISE_SUFFIX = re.compile(r"\b(steam|cd key|key|global|pc|eu|us|row|region free|digital download|gift card|account|epic games|gog|xbox|playstation|nintendo|switch|dlc)\b.*$")
TYPE_HINT = {"voucher": "GIFTCARD", "giftcard": "GIFTCARD", "dlc": "DLC"}


class CatalogUnavailable(RuntimeError):
    pass


def derive_aliases(name):
    """Nama produk Kinguin berbuntut platform/region ("Elden Ring Steam CD Key Global"); pelanggan hanya menulis "elden ring"."""
    plain = normalize(re.sub(r"\([^)]*\)", " ", name))
    words = " ".join(NOISE_SUFFIX.sub("", plain).split()).split()
    # Semua awalan nama: "Minecraft Java Bedrock" -> minecraft / minecraft java / minecraft java bedrock. Pelanggan jarang menulis nama penuh;
    # yang menentukan pilihan adalah awalan terpanjang yang cocok (lihat KB._best_alias).
    out = [" ".join(words[:i]) for i in range(1, len(words) + 1) if len(" ".join(words[:i])) >= 4]
    return out or [plain]


def rating_of(item):
    m = item.get("metacritic")
    return round(m / 20, 1) if isinstance(m, (int, float)) and m > 0 else None


class RemoteKB(KB):
    def __init__(self, base_url, token, timeout=2.5, site_url=""):
        self.base, self.token, self.timeout, self.site_url = base_url.rstrip("/"), token, timeout, site_url.rstrip("/")
        self._cache = {}
        super().__init__()

    FILES = ("knowledge.yaml", "learned.json")                # katalog tidak lagi berkas lokal

    def _load_products(self):
        return []

    def load(self):
        super().load()
        k = __import__("yaml").safe_load((DATA / "knowledge.yaml").read_text(encoding="utf-8"))
        self.tag_genres = {t: list(g) for t, g in (k.get("tag_genres") or {}).items()}
        self._cache.clear()

    # ---------- HTTP ----------
    def _get(self, **params):
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        key = json.dumps(clean, sort_keys=True)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
        qs = urllib.parse.urlencode(clean, doseq=True)
        req = urllib.request.Request(f"{self.base}/api/bot/products?{qs}", headers={"X-Bot-Token": self.token, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())["data"]
        except Exception as e:                                # jaringan, 401/503, JSON rusak: semuanya "katalog tak tersedia"
            raise CatalogUnavailable(str(e)) from e
        if len(self._cache) > 512: self._cache.clear()
        self._cache[key] = (time.time(), data)
        return data

    def _p(self, it):
        """Entri API -> bentuk produk yang dipakai dialog."""
        r = rating_of(it)
        return {"id": it["id"], "name": it["name"], "aliases": derive_aliases(it["name"]), "category": " ".join(it.get("platforms", [])),
                "price": int(it["priceIdr"]), "stock": int(it["qty"]) if it.get("inStock") else 0, "rating": r,
                "rating_label": f"Metacritic {int(it['metacritic'])}" if r else None,
                "url": (self.site_url + it["url"]) if it["url"].startswith("/") else it["url"], "tags": it.get("genres", []),
                "variants": int(it.get("variants", 1)), "platforms": it.get("platforms", [])}

    # ---------- kata kunci ----------
    def _tokens(self, text):
        skip = self.STOP | self.GENERIC | set(FUNC)
        return [t for t in normalize(text).split() if len(t) >= 2 and t not in skip]

    def _name_tokens(self, text):
        """Kata yang mungkin bagian dari nama produk: bukan kata fungsi dan bukan kosakata intent (harga, stok, berapa...)."""
        toks = self._tokens(text)
        core = [t for t in toks if t not in self.noise and t not in self.CATEGORY_HINT]
        return core or [t for t in toks if t not in self.noise]

    def _type_of(self, text):
        for w in normalize(text).split():
            if w in TYPE_HINT: return TYPE_HINT[w]
        return None

    def _genre_params(self, tags):
        return ["|".join(self.tag_genres.get(t, [t])) for t in tags]

    # ---------- antarmuka KB ----------
    def _candidates(self, q):
        toks = self._name_tokens(q)
        if not toks: return []
        return [self._p(i) for i in self._get(q=" ".join(toks[:6]), all=1, limit=30)["items"]]

    def search(self, text, k=3):
        toks = [t for t in self._tokens(text) if len(t) >= 3][:6]
        if not toks: return []
        return [self._p(i) for i in self._get(q=" ".join(toks), limit=k)["items"]]

    def extract_tags(self, text):
        """Hanya tag yang punya padanan genre di katalog (tag_genres); sisanya (mis. voucher) ditangani lewat jenis produk."""
        return super().extract_tags(text, only=self.tag_genres)

    def has_tags(self, tags):
        return bool(self._get(genre=self._genre_params(tags), all=1, limit=1)["items"])

    def query(self, text="", max_price=None, min_price=None, sort=None, k=3, in_stock=True, tags=()):
        toks = self._name_tokens(text)
        d = self._get(q=" ".join(toks[:6]), maxPrice=max_price, minPrice=min_price, sort=sort if sort in ("best", "cheap", "pricey") else "best",
                      genre=self._genre_params(tags), type=self._type_of(text), all=None if in_stock else 1, limit=k)
        return [self._p(i) for i in d["items"]], bool(d.get("hadHit"))

    def unknown_terms(self, text, known=frozenset()):
        """Kata bermakna yang tak dikenal. Untuk katalog besar: kata dianggap tak dikenal bila TIDAK ada produk yang memuatnya."""
        cand = [t for t in self._tokens(text) if len(t) >= 3 and not any(c.isdigit() for c in t) and t not in self.noise and t not in known
                and t not in self.CATEGORY_HINT and t not in self.tag_words()]
        if not cand: return []
        if self._get(q=" ".join(cand[:6]), all=1, limit=1)["items"]: return []
        return [t for t in cand if not self._get(q=t, all=1, limit=1)["items"] and not any(fuzz.ratio(t, w) >= 80 for w in known)]

    def tag_words(self):
        return {w for al in self.tag_aliases.values() for a in al for w in a.split()}

    def alternatives(self, prod, k=2, cheaper=False):
        genres = prod.get("tags") or []
        d = self._get(genre=[genres[0]] if genres else None, maxPrice=prod["price"] - 1 if cheaper else None, sort="best", type="GAME", limit=k + 1)
        return [p for p in (self._p(i) for i in d["items"]) if p["id"] != prod["id"]][:k]
