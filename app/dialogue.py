"""Manajer dialog: slot, tangga fallback, eskalasi. Setiap pesan pasti dibalas, kecuali mode AGENT."""
import json, re, time, pathlib, collections
from .kb import KB, DATA, make_kb
from .nlu import IntentClassifier, detect_lang, normalize, FUNC
from .entities import extract

HIGH, MID = 0.60, 0.42          # ambang keyakinan (dituning lewat tests)
ESC_MIN = 0.72                  # eskalasi ke admin butuh keyakinan lebih tinggi: salah eskalasi lebih mahal daripada bertanya balik
SLOT_INTENTS = {"price", "stock", "find_product"}
CATALOG_INTENTS = {"compare", "alternative", "too_expensive"}     # dijawab dari data katalog, bukan teks tetap
CATALOG_OK = SLOT_INTENTS | {"too_expensive"}                     # intent yang boleh dibelokkan ke pencarian berfilter
ESCALATE = {"human", "complaint"}
ORDER_INTENTS = {"order_status", "delivery", "refund", "license", "payment_issue", "human", "complaint"}
NEUTRAL = {"sama", "beli", "pesan", "order", "mau", "ingin", "pengen", "buat"}        # kata yang tak mengubah maksud "harga X berapa"
FILLER = FUNC | {"aja", "saja", "semua", "lah", "deh", "tapi", "atau", "hingga", "antara", "between", "but", "or"}
HISTORY = 20                                                      # jumlah pesan terakhir yang disimpan per percakapan
LOG_MAX = 20 * 1024 * 1024                                        # ukuran log sebelum dirotasi
RECENT = 6                                                        # produk "terakhir" hanya berlaku beberapa giliran
REFER = re.compile(r"\b(itu|tadi|yang tadi|nya|that|it|this one)\b")
ELLIPSIS = re.compile(r"^(kalau|bagaimana dengan|bagaimana kalau|terus|lalu|dan|how about|what about|and|then)\b")
SOCIAL = {"greeting", "thanks", "goodbye", "ack", "deny", "bot_identity"}   # basa-basi tak boleh mengalahkan pertanyaan harga/stok
FACET_WORDS = re.compile(r"\b(harga\w*|hrg|price|cost\w*|duit|biaya|how much|how many|stok\w*|stock|ready|tersedia|available|sisa|kosong|habis|berapa)\b")
AVAIL_RX = re.compile(r"\bada\b(?!\s+(?!gak|ga|tidak|sih|nih|ya|dan|sama|atau|nggak|ngga|kah)\w)")
HAVE_RX = re.compile(r"\b(ada|punya|jual|have|sell|is there|are there|there is|there are)\b")
STOCK_RX = re.compile(r"\b(left|remaining|stok|stock|ready|tersedia|available|sisa|kosong|habis|in stock)")
PRICE_RX = re.compile(r"\b(harga|hrg|price|cost|duit|biaya|how much)")
TOTAL_RX = re.compile(r"\b(total\w*|jumlah\w*|semuanya|keseluruhan|all together|altogether|in total|sum)\b")
FREE_RX = re.compile(r"\b(gratis|free(?!\s*fire))\b")
NOT_FREE_RX = re.compile(r"\b(ongkir|kirim\w*|shipping|delivery|trial|demo)\b")
QTY_UNIT = r"(?:x|buah|pcs|biji|unit|kali|copies|copy)?"
HUMAN_ASK = re.compile(r"\b(panggil|panggilin|hubungi|hubungkan|sambungkan|minta|call|get|connect|talk|speak|bicara|ngobrol|chat)\b.*\b(admin|cs|agent|human|person|someone|manusia|orang|team|tim)\b")
MASK = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"), (re.compile(r"\+?\d[\d\s-]{7,}\d"), "<telp>")]


def rp(n): return "Rp" + f"{n:,}".replace(",", ".")


def pfmt(p):
    """Harga produk untuk teks/kartu. Game dengan beberapa varian (platform/region) memakai harga termurah: tulis "mulai" agar jujur."""
    return ("mulai " if p.get("variants", 1) > 1 else "") + rp(p["price"])


def stock_txt(p):
    """Stok besar ditulis "50+": angka pastinya berubah tiap saat dan tak berguna bagi pelanggan."""
    return "50+" if p["stock"] > 50 else str(p["stock"])


class Bot:
    def __init__(self, store=None, notifier=None):
        self.notifier = notifier                            # fungsi(event: dict) -> None; webhook ke panel admin
        self.store = store                                  # None = state di memori proses (tes/dev); StateStore = persisten
        self.kb = make_kb()
        self.clf = IntentClassifier(self.kb.intents)
        self.kb.noise = self.clf.vocab_set
        self.state = {}
        self.hits = collections.defaultdict(collections.deque)

    def reload(self):
        self.kb.load(); self.clf = IntentClassifier(self.kb.intents); self.kb.noise = self.clf.vocab_set

    # ---------- util ----------
    def st(self, cid):
        if self.store:
            return self.store.get(cid) or self._new_state()
        return self.state.setdefault(cid, self._new_state())

    def _save(self, cid, s):
        if self.store: self.store.put(cid, s)

    @staticmethod
    def _new_state():
        return ({"mode": "AI", "lang": "id", "pending": None, "miss": 0, "last_product": None, "handoff": False,
                                          "turn": 0, "last_product_turn": -99, "last_products": [], "last_intent": None, "last_facets": None, "history": []})

    def _log(self, cid, text, out):
        for rx, rep in MASK: text = rx.sub(rep, text)
        rec = {"ts": int(time.time()), "cid": cid, "text": text, **{k: out.get(k) for k in ("lang", "intent", "confidence", "action")}}
        try:
            path = DATA / "log.jsonl"
            if path.exists() and path.stat().st_size > LOG_MAX:      # rotasi sederhana: satu berkas cadangan
                path.replace(path.with_suffix(".jsonl.1"))
            with open(path, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _rate_ok(self, cid):
        q, now = self.hits[cid], time.time()
        while q and now - q[0] > 60: q.popleft()
        q.append(now)
        return len(q) <= 20

    def _chips(self, intents, lang):
        return {"type": "quick_replies", "items": [self.kb.label(i, lang) for i in intents if self.kb.intents.get(i, {}).get("label")]}

    def _cards(self, prods):
        return {"type": "products", "items": [{"id": p["id"], "name": p["name"], "price": pfmt(p), "stock": p["stock"], "rating": p.get("rating_label") or p["rating"], "url": p["url"]} for p in prods]}

    def _out(self, blocks, lang, intent=None, conf=0.0, action="answer", handoff=False, silent=False):
        return {"blocks": blocks, "lang": lang, "intent": intent, "confidence": round(conf, 3), "action": action, "handoff": handoff, "silent": silent}

    # ---------- utama ----------
    def _masked(self, text):
        for rx, rep in MASK: text = rx.sub(rep, text)
        return text

    def _emit(self, event, cid, s, **extra):
        if not self.notifier: return
        try:
            self.notifier({"event": event, "conversation_id": cid, "history": s["history"][-10:], **extra})
        except Exception:
            pass                                            # webhook tidak boleh mengganggu chat

    def reply(self, cid, text):
        if self.kb.stamp() != self.kb._stamp:                # data diubah (admin/dasbor/sunting berkas): muat ulang di worker ini juga
            try: self.reload()
            except Exception: pass                           # berkas setengah tertulis: pakai data lama dulu
        s = self.st(cid)
        try:
            if s["mode"] == "AGENT":
                s["history"] = (s["history"] + [{"role": "user", "text": self._masked(text)}])[-HISTORY:]
                self._save(cid, s)
                self._emit("customer_message", cid, s, text=self._masked(text))      # admin sedang menangani: teruskan ke panel
                return self._out([], s["lang"], action="silent", silent=True)
            if not self._rate_ok(cid):
                return self._out([{"type": "text", "text": self.kb.t("rate_limit", s["lang"])}], s["lang"], action="rate_limit")
            out = self._reply(s, text)
            bot_text = " ".join(b["text"] for b in out["blocks"] if b["type"] == "text")
            s["history"] = (s["history"] + [{"role": "user", "text": self._masked(text)}, {"role": "bot", "text": bot_text}])[-HISTORY:]
            self._save(cid, s)
            if out["handoff"]: self._emit("handoff", cid, s, reason=out["action"], intent=out["intent"], lang=out["lang"])
        except Exception:                                   # jaring pengaman: chat tidak boleh mati diam
            out = self._out([{"type": "text", "text": self.kb.t("error", s["lang"])}], s["lang"], action="error")
        self._log(cid, text, out)
        return out

    # ---------- alat bantu ----------
    def _t(self, key, lang, **kw): return {"type": "text", "text": self.kb.t(key, lang, **kw)}

    def _search(self, text):
        found = self.kb.search(text)
        if not found:
            items, hit = self.kb.query(normalize(text), k=3)          # "game pc", "voucher steam": kata kategori
            found = items if hit else []
        return found

    def _recent_product(self, s):
        return s["last_product"] if s["last_product"] and s["turn"] - s["last_product_turn"] <= RECENT else None

    @staticmethod
    def _facets(q):
        """Apa yang ditanyakan tentang produk: (harga/stok/keduanya, lemah?).
        'berapa' polos = harga tapi bukti lemah; 'stok ... berapa' = stok; 'X ada?' (tanpa kata bermakna sesudahnya) = stok."""
        st = bool(STOCK_RX.search(q) or AVAIL_RX.search(q)) or "how many" in q
        pr = bool(PRICE_RX.search(q))
        weak = False
        if not (st or pr) and re.search(r"\bberapa\b", q): pr, weak = True, True
        return {f for f, on in (("price", pr), ("stock", st)) if on}, weak

    @staticmethod
    def _quantities(text, prods):
        """Jumlah per produk dari teks mentah ("beli 2 minecraft", "elden ring x3"). Default 1; hanya 2..99 yang dianggap jumlah."""
        out = {}
        for p in prods:
            out[p["id"]] = 1
            for alias in sorted([p["name"], *p["aliases"]], key=len, reverse=True):
                a = re.escape(alias.lower())
                m = re.search(rf"(?<![\d.,])(\d{{1,2}})\s*{QTY_UNIT}\s*{a}", text) or re.search(rf"{a}\s*(?:x|×)\s*(\d{{1,2}})\b|{a}\s+(\d{{1,2}})\s*(?:x|buah|pcs|biji|unit)\b", text)
                if m:
                    n = int(next(g for g in m.groups() if g))
                    if 2 <= n <= 99: out[p["id"]] = n
                    break
        return out

    def _total_blocks(self, prods, ent, lang):
        """Total harga = jumlah x harga katalog. Hanya muncul bila diminta ("total") atau ada jumlah > 1."""
        qty = self._quantities(ent.text, prods)
        if not (TOTAL_RX.search(normalize(ent.text)) and len(prods) > 1 or any(n > 1 for n in qty.values())):
            return []
        kb, lines, total = self.kb, [], 0
        for p in prods:
            n = qty[p["id"]]; total += n * p["price"]
            lines.append(kb.t("qty_line", lang, name=p["name"], n=n, price=pfmt(p), sub=("mulai " if p.get("variants", 1) > 1 else "") + rp(n * p["price"])))
            if p["stock"] > 0 and n > p["stock"]: lines.append(kb.t("qty_over", lang, name=p["name"], stock=stock_txt(p)))
            elif p["stock"] <= 0: lines.append(kb.t("stock_out", lang, name=p["name"]))
        if len(prods) > 1 or any(n > 1 for n in qty.values()) and len(prods) > 1:
            lines.append(kb.t("total_line_from" if any(p.get("variants", 1) > 1 for p in prods) else "total_line", lang, total=rp(total)))
        return [{"type": "text", "text": " ".join(lines)}]

    def _remember(self, s, intent, prods=None, facets=None):
        s["last_intent"], s["last_facets"] = intent, (set(facets) if facets else None)
        if prods: s["last_product"], s["last_products"], s["last_product_turn"] = prods[-1], list(prods), s["turn"]

    def _clarify(self, lang, ranked, intent, conf):
        opts = [i for i, sc in ranked if sc >= MID * 0.8 and self.kb.intents[i].get("label")][:2] or ["find_product", "human"]
        return self._out([self._t("clarify", lang), self._chips(opts, lang)], lang, intent, conf, "clarify")

    # ---------- utama ----------
    def _reply(self, s, text):
        kb = self.kb
        s["turn"] += 1
        lang = s["lang"] = detect_lang(text, s["lang"])
        ent = extract(text)                                            # harga, urutan, nomor order (dari teks mentah)
        prods, rest = kb.match_products(ent.text)                      # bisa lebih dari satu produk
        ranked = self.clf.classify(rest or ent.text)
        if (ent.sort or ent.max_price or ent.min_price) and not [w for w in normalize(rest or ent.text).split() if w not in FILLER]:
            ranked = []                                                # "yang termurah dong" -> tinggal kata fungsi; jangan ditebak
        intent, conf = ranked[0] if ranked else (None, 0.0)
        q = normalize(ent.text)
        facets, weak = self._facets(rest)

        # 0) nomor order: bot tidak bisa memverifikasi order, jadi catat lalu teruskan ke tim (tidak pernah mengarang status)
        if ent.order_id and (intent in ORDER_INTENTS or s["last_intent"] in ORDER_INTENTS or conf < HIGH):
            return self._handoff(s, lang, "order_status", 1.0, "handoff_order", key="order_received", order=ent.order_id)

        if not prods and s["last_intent"] == "find_product" and re.fullmatch(r"(gimana|bagaimana) caranya|caranya (gimana|bagaimana)|how( do i)?( do it)?", q):
            intent, conf = "how_to_buy", 1.0                            # "gimana caranya?" sesudah menyebut mau beli produk

        if prods and not facets and TOTAL_RX.search(q): facets = {"price"}      # "minecraft dan stardew, total?"
        if intent == "compare" and len(prods) >= 2 and conf >= MID: conf = max(conf, HIGH)   # dua produk + "vs" = jelas minta perbandingan

        # 1) konteks: slot yang ditunggu, pertanyaan ganda (harga+stok), elipsis ("kalau Minecraft?")
        if s["pending"] and prods:
            intent, conf = s["pending"], 1.0
            if intent in ("price", "stock"): facets = facets or {intent}
        elif prods and facets:
            rem = TOTAL_RX.sub(" ", FACET_WORDS.sub(" ", rest))         # apa maksud kalimat setelah kata harga/stok/total dibuang?
            r2 = self.clf.classify(rem) if [w for w in normalize(rem).split() if w not in FILLER and w not in NEUTRAL and not w.isdigit()] else []
            if r2 and r2[0][0] not in SLOT_INTENTS | SOCIAL and r2[0][1] >= (MID if weak else HIGH):
                intent, conf, ranked = r2[0][0], r2[0][1], r2                # mis. "elden ring harganya mahal banget"
            else:
                intent, conf = ("stock" if facets == {"stock"} else "price"), max(conf, HIGH)
        elif prods and s["last_facets"] and ELLIPSIS.match(q) and (intent in SLOT_INTENTS or conf < HIGH):
            facets = set(s["last_facets"])
            intent, conf = ("stock" if facets == {"stock"} else "price"), 1.0
        elif prods and conf < HIGH and not (intent in CATALOG_INTENTS and conf >= MID):
            intent, conf = "find_product", 1.0                         # hanya menyebut produk -> tampilkan kartu

        if not prods and TOTAL_RX.search(q) and s["last_products"] and s["turn"] - s["last_product_turn"] <= RECENT:
            prods, intent, conf, facets = list(s["last_products"]), "price", 1.0, {"price"}     # "totalnya berapa?" -> jumlahkan produk tadi
        if not prods and FREE_RX.search(q) and not NOT_FREE_RX.search(q):
            top, _ = kb.query("", sort="cheap", k=3)                    # jujur: katalog tak punya produk gratis
            s["pending"], s["miss"] = None, 0
            return self._out([self._t("no_free", lang), self._cards(top)], lang, "find_product", 1.0, "search")

        # 2) rujukan ("itu", "tadi") atau intent yang jelas merujuk produk terakhir (alternatif, "kemahalan")
        if not prods and intent in (SLOT_INTENTS | {"alternative", "too_expensive"}) and conf >= MID:
            recent = self._recent_product(s)
            follow = s["last_product_turn"] == s["turn"] - 1 and intent in ("price", "stock") and len(q.split()) <= 3
            if recent and (REFER.search(q) or follow) and intent in ("price", "stock") and kb.unknown_terms(rest, known=self.clf.vocab_set):
                recent = None                                          # menyebut nama yang tak dikenal: jangan diam-diam memakai produk sebelumnya
            if recent and (REFER.search(q) or follow or intent in ("alternative", "too_expensive")): prods = [recent]
        if intent in ("price", "stock") and prods and not facets: facets = {intent}

        if intent in SLOT_INTENTS and intent == "find_product" and conf >= MID:   # mencari produk aman: langsung cari
            conf = max(conf, HIGH)

        # 3) eskalasi (ambang tinggi: salah oper lebih mahal daripada bertanya balik)
        if intent == "human" and conf >= MID and HUMAN_ASK.search(q): conf = max(conf, ESC_MIN)   # perintah eksplisit "panggil admin"
        if intent in ESCALATE and conf >= ESC_MIN:
            return self._handoff(s, lang, intent, conf)
        if intent in ESCALATE and conf >= MID:
            s["miss"] = 0
            return self._out([self._t("clarify", lang), self._chips(["human", "find_product"], lang)], lang, intent, conf, "clarify")

        # 4) pencarian berfilter: "game di bawah 100rb", "yang termurah", "rekomendasi"
        tags, _ = kb.extract_tags(ent.text) if not prods else ([], "")
        if not prods and (ent.max_price or ent.min_price or ent.sort or tags) and (intent in CATALOG_OK or intent in ("compare", "alternative") or conf < MID):
            out = self._catalog(s, ent, lang, conf)
            if out: return out

        if intent in ("deny", "ack") and conf >= HIGH and not prods and len(rest.split()) >= 2:      # "ada zelda gak": 'gak' bukan penolakan
            nf = self._unknown_product(s, prods, rest, ent, facets, lang, conf)
            if nf: return nf

        if conf >= HIGH:
            s["miss"] = 0
            if intent in SLOT_INTENTS:
                return self._product_intent(s, intent, prods, facets, ent, rest, text, lang, conf)
            if intent in CATALOG_INTENTS:
                return self._catalog_intent(s, intent, prods, lang, conf)
            if intent == "deny": s["pending"] = None                    # "nggak jadi" membatalkan slot yang menggantung
            blocks = [{"type": "text", "text": kb.answer(intent, lang)}]
            fu = kb.intents[intent].get("followups")
            if fu: blocks.append(self._chips(fu, lang))
            if intent not in ("ack", "deny"):                            # ack/deny tak boleh menghapus konteks percakapan
                s["pending"] = None
                self._remember(s, intent)
            return self._out(blocks, lang, intent, conf)

        nf = self._unknown_product(s, prods, rest, ent, facets, lang, conf)
        if nf: return nf

        if conf >= MID:                                     # ragu -> tanya balik dengan pilihan
            s["miss"] = 0
            return self._clarify(lang, ranked, intent, conf)

        found = self._search(text) if conf < MID else []          # tidak paham maksud, tapi ada kata yang cocok dengan katalog
        if found:
            s["miss"] = 0
            return self._out([self._t("found", lang), self._cards(found)], lang, "find_product", conf, "search")

        s["miss"] += 1                                      # tidak paham -> tangga fallback
        topics = ["find_product", "payment_methods", "delivery", "order_status", "human"]
        if s["miss"] == 1:
            return self._out([self._t("miss1", lang), self._chips(topics[:4], lang)], lang, intent, conf, "miss1")
        if s["miss"] == 2:
            return self._out([self._t("miss2", lang), self._chips(topics, lang)], lang, intent, conf, "miss2")
        return self._handoff(s, lang, "human", conf, "miss3")

    def _unknown_product(self, s, prods, rest, ent, facets, lang, conf):
        """"gta 5 ada?", "fifa 24", "valorant point ada ga": jelas menanyakan produk yang tak ada di katalog."""
        if prods: return None
        words = normalize(rest or ent.text).split()
        unk = self.kb.unknown_terms(TOTAL_RX.sub(" ", rest or ent.text), known=self.clf.vocab_set)
        if unk and len(words) <= 6 and (facets or HAVE_RX.search(" ".join(words)) or any(w.isdigit() for w in words)):
            if self._search(rest or ent.text): return None                 # ada kata yang cocok katalog -> biar alur pencarian
            s["pending"], s["miss"] = None, 0
            top, _ = self.kb.query("", sort="best", k=3)
            return self._out([self._t("no_product", lang), self._cards(top)], lang, "find_product", conf, "not_found")

    # ---------- jawaban produk ----------
    def _product_lines(self, prods, facets, lang):
        kb, out = self.kb, []
        for p in prods:
            kw = dict(name=p["name"], price=pfmt(p), stock=stock_txt(p))
            if {"price", "stock"} <= facets: out.append(kb.t("price_stock_in" if p["stock"] > 0 else "price_stock_out", lang, **kw))
            elif "stock" in facets: out.append(kb.t("stock_in" if p["stock"] > 0 else "stock_out", lang, **kw))
            else: out.append(kb.t("price_line", lang, **kw))
        return " ".join(out)

    def _alt_blocks(self, prods, lang, cheaper=False, base=None):
        base = base or prods[0]
        alts = [a for a in self.kb.alternatives(base, k=2, cheaper=cheaper) if a not in prods]
        if alts: return [self._t("cheaper_intro" if cheaper else "alt_intro", lang), self._cards(alts)]
        return [self._t("cheaper_none" if cheaper else "alt_none", lang)]

    def _product_intent(self, s, intent, prods, facets, ent, rest, text, lang, conf):
        kb = self.kb
        if intent == "find_product" and not prods:
            found = self._search(text)
            if found:
                s["pending"] = None
                self._remember(s, intent, found)
                return self._out([self._t("found", lang), self._cards(found)], lang, intent, conf, "search")
            unk = kb.unknown_terms(rest, known=self.clf.vocab_set)
            if unk and len(rest.split()) <= 6:                       # "do you have zelda": sebut nama yang tak ada -> jujur
                top, _ = kb.query("", sort="best", k=3)
                return self._out([self._t("no_product", lang), self._cards(top)], lang, intent, conf, "not_found")
            s["pending"] = "find_product"
            return self._out([{"type": "text", "text": kb.answer("find_product", lang)}], lang, intent, conf, "ask_slot")
        if not prods:
            s["pending"] = intent
            unk = kb.unknown_terms(TOTAL_RX.sub(" ", rest), known=self.clf.vocab_set)
            if unk and len(rest.split()) <= 6:                       # menyebut sesuatu yang tak ada di katalog: jangan pura-pura ada
                top, _ = kb.query("", sort="best", k=3)
                return self._out([self._t("no_product", lang), self._cards(top)], lang, intent, conf, "not_found")
            return self._out([self._t("ask_product", lang)], lang, intent, conf, "ask_slot")
        s["pending"] = None
        if intent == "find_product":
            self._remember(s, intent, prods)
            return self._out([self._t("found", lang), self._cards(prods)], lang, intent, conf, "product")
        facets = facets or {intent}
        blocks = [{"type": "text", "text": self._product_lines(prods, facets, lang)}, self._cards(prods)]
        total = self._total_blocks(prods, ent, lang) if "price" in facets else []
        if total: blocks = total + blocks[1:]                          # rincian jumlah menggantikan kalimat harga polos
        oos = next((p for p in prods if p["stock"] <= 0), None)
        if "stock" in facets and oos:                                # habis -> tawarkan yang tersedia, dari data
            blocks += self._alt_blocks(prods, lang, base=oos)
        self._remember(s, intent, prods, facets)
        return self._out(blocks, lang, intent, conf, "product")

    # ---------- pencarian berfilter & intent katalog ----------
    def _catalog(self, s, ent, lang, conf):
        kb = self.kb
        tags, clean = kb.extract_tags(ent.text)
        if tags and not kb.has_tags(tags):                           # katalog memang tak punya tag itu (mis. horor): jujur, jangan menebak
            s["pending"], s["miss"] = None, 0
            top, _ = kb.query("", sort="best", k=3)
            self._remember(s, "find_product", top)
            return self._out([self._t("no_tag", lang, tags=" + ".join(tags)), self._cards(top)], lang, "find_product", conf, "search")
        items, had_hit = kb.query(clean, ent.max_price, ent.min_price, ent.sort, tags=tags)
        unk = kb.unknown_terms(clean, known=self.clf.vocab_set)
        if unk and not had_hit and ent.sort != "best":
            return None                                              # yang dicari tak ada di katalog -> biarkan alur "tidak ditemukan"
        note = kb.t("no_filter", lang, terms=" ".join(unk)) + " " if unk else ""
        mx, mn = (rp(ent.max_price) if ent.max_price else ""), (rp(ent.min_price) if ent.min_price else "")
        if items:
            if ent.max_price and ent.min_price: intro = kb.t("range_intro", lang, min=mn, max=mx)
            elif ent.max_price: intro = kb.t("budget_intro", lang, max=mx)
            elif ent.min_price: intro = kb.t("min_intro", lang, min=mn)
            else: intro = kb.t({"cheap": "cheapest_intro", "pricey": "pricey_intro"}.get(ent.sort, "best_intro"), lang)
            if tags: intro = kb.t("tag_intro", lang, tags=", ".join(tags)) + (" " + intro if (ent.max_price or ent.min_price or ent.sort in ("cheap", "pricey")) else "")
        elif tags and (ent.max_price or ent.min_price):
            near = kb.query(clean, tags=tags, sort="cheap", k=2)[0]           # tag cocok tapi di luar batas harga: tunjukkan yang terdekat
            if near: items, intro = near, kb.t("tag_price_none", lang, tags=", ".join(tags))
            else: items, intro = kb.query("", sort="best", k=3)[0], kb.t("none_generic", lang)
        elif ent.max_price:
            items = kb.query(ent.text, sort="cheap", k=1)[0] or kb.query("", sort="cheap", k=1)[0]
            intro = kb.t("range_none", lang, min=mn, max=mx) if ent.min_price else kb.t("budget_none", lang, max=mx)
        else:
            items, intro = kb.query("", sort="best", k=3)[0], kb.t("none_generic", lang)
        s["pending"], s["miss"] = None, 0
        self._remember(s, "find_product", items)
        return self._out([{"type": "text", "text": note + intro}, self._cards(items)], lang, "find_product", conf, "search")

    def _catalog_intent(self, s, intent, prods, lang, conf):
        kb = self.kb
        if intent == "compare":
            if len(prods) < 2:
                s["pending"] = "compare"
                return self._out([{"type": "text", "text": kb.answer("compare", lang)}], lang, intent, conf, "ask_slot")
            rate = lambda p: p["rating"] or 0
            lines = " ".join(kb.t("compare_line", lang, name=p["name"], price=pfmt(p),
                                  rating=kb.t("metacritic_val", lang, m=p["rating_label"].split()[-1]) if p.get("rating_label") else (kb.t("rating_val", lang, r=p["rating"]) if p["rating"] else kb.t("rating_none", lang)),
                                  stock_word=kb.t("word_in" if p["stock"] > 0 else "word_out", lang)) for p in prods)
            cheapest = min(prods, key=lambda p: p["price"])
            top = [p for p in prods if rate(p) == max(rate(x) for x in prods)]
            tail = kb.t("rating_tie", lang) if len(top) == len(prods) else \
                kb.t("best_is", lang, name=" / ".join(p["name"] for p in top)) + " " + kb.t("compare_note", lang)
            s["pending"] = None
            self._remember(s, intent, prods)
            return self._out([{"type": "text", "text": f'{kb.t("compare_intro", lang)} {lines} {kb.t("cheapest_is", lang, name=cheapest["name"])} {tail}'},
                              self._cards(prods)], lang, intent, conf, "compare")
        base = prods[0] if prods else None
        if intent == "too_expensive" and not base:                   # tanpa produk acuan: tampilkan yang termurah yang tersedia
            s["pending"] = None
            items = kb.query("", sort="cheap", k=3)[0]
            return self._out([self._t("cheapest_intro", lang), self._cards(items)], lang, intent, conf, "search")
        if not base:
            s["pending"] = intent
            return self._out([{"type": "text", "text": kb.answer(intent, lang)}], lang, intent, conf, "ask_slot")
        s["pending"] = None
        blocks = self._alt_blocks([base], lang, cheaper=(intent == "too_expensive"), base=base)
        self._remember(s, intent, [base])
        return self._out(blocks, lang, intent, conf, "alternatives")

    def _handoff(self, s, lang, intent, conf, action="handoff", key="handoff", **kw):
        s["mode"], s["handoff"], s["pending"] = "AGENT", True, None    # bot diam setelah eskalasi
        return self._out([self._t(key, lang, **kw)], lang, intent, conf, action, handoff=True)

    def set_mode(self, cid, mode):
        s = self.st(cid); s["mode"] = mode; s["miss"] = 0
        if mode == "AI": s["handoff"] = False               # admin selesai: percakapan tidak lagi "menunggu"
        self._save(cid, s)
        return s
