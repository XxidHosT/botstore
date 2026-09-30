"""NLU tanpa model eksternal: normalisasi + TF-IDF karakter n-gram + kemiripan cosine ke contoh kalimat."""
import re, unicodedata
from functools import lru_cache
from rapidfuzz import fuzz, process
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SLANG = {
    "brpa": "berapa", "brp": "berapa", "berapaan": "berapa", "gmn": "bagaimana", "gmana": "bagaimana", "gimana": "bagaimana",
    "bgmn": "bagaimana", "yg": "yang", "dgn": "dengan", "utk": "untuk", "tdk": "tidak", "gk": "tidak", "ga": "tidak", "gak": "tidak",
    "nggak": "tidak", "ngga": "tidak", "engga": "tidak", "enggak": "tidak", "udh": "sudah", "udah": "sudah", "blm": "belum",
    "krn": "karena", "tp": "tapi", "bs": "bisa", "bsa": "bisa", "dmn": "dimana", "kpn": "kapan", "hrg": "harga", "hrga": "harga",
    "pengirimn": "pengiriman", "pngiriman": "pengiriman", "tlg": "tolong", "plis": "tolong", "thx": "thanks", "makasi": "makasih",
    "mksh": "makasih", "trims": "terima kasih", "pesenan": "pesanan", "psnan": "pesanan", "byr": "bayar", "pembayarn": "pembayaran",
    "admn": "admin", "hlo": "halo", "halb": "halo", "hallo": "halo", "hy": "hai", "hlw": "halo", "gue": "saya", "gua": "saya", "lu": "kamu", "nyampe": "sampai", "nyampe2": "sampai", "sampe": "sampai", "kok": "kok", "topup": "top up", "tf": "transfer",
    "bgt": "banget", "bngt": "banget", "sy": "saya", "aq": "aku", "sdh": "sudah", "jgn": "jangan", "dpt": "dapat", "lg": "lagi",
    "kmrn": "kemarin", "klo": "kalau", "kalo": "kalau", "trs": "terus", "mo": "mau", "tpi": "tapi", "rekomen": "rekomendasi",
    "pls": "please", "plz": "please", "ty": "thanks", "kemahalan": "terlalu mahal", "kemaren": "kemarin", "mksih": "makasih", "makasih": "makasih", "bli": "beli", "blii": "beli", "pesen": "pesan", "ordr": "order", "cr": "cara", "cra": "cara", "carany": "caranya", "gmna": "bagaimana", "tau": "tahu", "sm": "sama", "dr": "dari", "klu": "kalau", "brapa": "berapa", "brpaa": "berapa", "hbs": "habis", "redy": "ready", "redi": "ready", "stk": "stok", "stck": "stock",
}
ID_WORDS = set("yang dan di ke dari untuk dengan saya aku kamu apa berapa bagaimana bisa tidak sudah belum mau ada cara harga pesanan bayar kirim kapan dimana kak min tolong gak ga nggak udah banget dong sih ya".split())
EN_WORDS = set("any there which hey cheaper free cheapest buy the is are a an to of for with i you what how much can do does not have want need my order where when price pay please hello hi thanks it in on".split())


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(.)\1{2,}", r"\1", t)          # haloooo -> halo
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return " ".join(SLANG.get(w, w) for w in t.split())


def detect_lang(text: str, prev: str = "id") -> str:
    words = normalize(text).split()
    idn = sum(w in ID_WORDS for w in words)
    eng = sum(w in EN_WORDS for w in words)
    if idn == eng:
        return prev
    return "id" if idn > eng else "en"


# kata fungsi: tidak membawa maksud, jadi tak dihitung saat menilai "apakah pesan ini memakai kata yang kukenal"
FUNC = set("yang dan di ke dari untuk dengan saya aku kamu apa ini itu the a an to of is are i you my it in on sih dong ya nih deh kok kak min tolong please nya mau ada bisa".split())


def augment(text: str, rng, n: int = 3):
    """Varian bertypo dari satu contoh kalimat (huruf hilang/tertukar/dobel) supaya pencocok tahan salah ketik. Deterministik lewat rng."""
    out = []
    for _ in range(n):
        w = text.split()
        if not w: break
        i = rng.randrange(len(w)); word = w[i]
        if len(word) >= 5:
            j = rng.randrange(1, len(word) - 1); op = rng.randrange(3)
            word = word[:j] + word[j + 1:] if op == 0 else word[:j] + word[j + 1] + word[j] + word[j + 2:] if op == 1 and j + 2 <= len(word) else word[:j] + word[j] + word[j:]
            w[i] = word; out.append(" ".join(w))
    return out


class IntentClassifier:
    def __init__(self, intents: dict):
        texts, labels = [], []
        for name, spec in intents.items():
            for lang_examples in spec["examples"].values():
                for ex in lang_examples:
                    texts.append(normalize(ex)); labels.append(name)
            for lab in spec.get("label", {}).values():      # label tombol quick-reply harus kembali ke intent-nya
                texts.append(normalize(lab)); labels.append(name)
        import random
        n_orig, rng = len(texts), random.Random(7)
        for t, l in list(zip(texts, labels)):
            for v in augment(t, rng):
                texts.append(v); labels.append(l)
        self.labels = labels
        self.vocab = sorted({w for t in texts[:n_orig] for w in t.split()} - FUNC)
        self.vocab_set = set(self.vocab)
        self._known = lru_cache(maxsize=4096)(self._is_known)
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
        self.matrix = self.vec.fit_transform(texts)

    def _is_known(self, w: str) -> bool:
        if w in self.vocab_set: return True
        return len(w) >= 5 and process.extractOne(w, self.vocab, scorer=fuzz.ratio, score_cutoff=82) is not None

    def coverage(self, q: str) -> float:
        """Porsi kata bermakna di pesan yang dikenal dari contoh latih. Kata asing = bukti lemah, bukan bukti kuat."""
        toks = [w for w in q.split() if w not in FUNC and not w.isdigit()]
        if not toks: return 1.0
        return sum(self._known(w) for w in toks) / len(toks)

    def classify(self, text: str, top: int = 3):
        q = normalize(text)
        if not q:
            return []
        sims = cosine_similarity(self.vec.transform([q]), self.matrix)[0]
        best = {}
        for label, s in zip(self.labels, sims):
            if s > best.get(label, 0):
                best[label] = float(s)
        # n-gram karakter mudah "kebetulan mirip" (mis. "ok" ~ "stok"). Pesan pendek tanpa satu pun kata yang dikenal
        # tidak boleh mendapat keyakinan penuh.
        cov = self.coverage(q)
        if cov == 0.0 or (len(q.split()) <= 2 and cov < 1.0):
            factor = 0.6 + 0.4 * cov
            best = {k: v * factor for k, v in best.items()}
        return sorted(best.items(), key=lambda x: -x[1])[:top]
