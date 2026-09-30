# JG chat-brain

Otak chat buatan sendiri: tanpa API AI pihak ketiga, tanpa internet saat jalan. Balasan ~1 ms di CPU.

## Jalankan
    docker compose up --build        # atau: pip install -r requirements.txt && uvicorn app.main:app
    curl localhost:8000/health       # otak saja, tanpa UI
    pytest -q tests                  # 292 tes (regresi perilaku + entitas + invarian keamanan data)
    python -m tools.evaluate         # skor set uji A (67 kasus)   -v untuk lihat balasan yang gagal
    python -m tools.evaluate tests.heldout_b   # skor set uji B (54 kasus); juga heldout_c, _d, _e

## Cara kerja (satu pesan)
1. **entitas** dari teks mentah (`app/entities.py`): batas harga ("di bawah 100rb", "max 150 ribu", "under 100k"),
   urutan ("termurah", "termahal", "rating tertinggi", "rekomendasi"), nomor order ("INV-48213", "#55231")
2. normalisasi (slang, huruf berulang, typo) + deteksi bahasa per pesan (ID/EN)
3. cocokkan **semua** nama produk yang disebut (rapidfuzz), lalu klasifikasi maksud (TF-IDF karakter n-gram ke contoh kalimat).
   Pesan pendek yang tak memuat satu pun kata yang dikenal dipenalti (mencegah "ok" ≈ "stok")
4. dialog: slot ("harganya berapa?" → "produk yang mana?" → "Elden Ring" → harga), rujukan ("itu", "harganya?"),
   elipsis ("kalau Minecraft?" memakai pertanyaan sebelumnya), tangga fallback (tanya balik → daftar topik → eskalasi)
5. angka (harga, stok, rating) selalu dari data, dikirim sebagai kartu produk, tidak pernah dikarang.
   Ada tes invarian untuk ini (`test_every_number_comes_from_data`)

## Yang bisa dijawab
- **Harga / stok / keduanya** sekaligus, untuk beberapa produk sekaligus. "stok X berapa" = stok, bukan harga
- **Jumlah & total**: "beli 2 minecraft berapa", "2 elden ring dan 1 minecraft totalnya berapa", lalu "totalnya berapa?" menjumlahkan produk tadi. Hitungan murni dari harga katalog; jumlah di atas stok diberi catatan
- **Cara beli** ("cara order", "gimana caranya" sesudah menyebut produk) dan **rentang harga** ("100rb-200rb", "antara 90rb dan 150rb")
- **Katalog berfilter**: "game di bawah 150 ribu", "voucher max 120rb", "yang termurah", "rekomendasi game",
  "diatas 300rb". Bila tak ada yang cocok, bot bilang begitu lalu menampilkan yang terdekat
- **Bandingkan** ("minecraft vs stardew"): harga, rating, stok dari data toko. Soal selera bot tidak menilai
- **Alternatif / lebih murah**: produk habis → tawarkan yang tersedia di kategori sama; "kemahalan" → pilihan lebih murah
- **Nomor order**: dicatat dan diteruskan ke tim. Bot **tidak** mengecek atau mengarang status order
- **Jujur soal batas data**: "rekomendasi game horor" → bot bilang belum bisa menyaring genre (katalog tak punya data itu).
  Produk yang tak ada di katalog tidak diberi harga
- Produk yang jelas ditanyakan tapi tak ada ("gta 5 ada?", "fifa 24") dijawab "belum ada di katalog"; "game gratis" dijawab jujur (semua berbayar)
- Intent baru: promo, garansi, keaslian produk, jam operasional, masalah pembayaran, identitas bot
  ("kamu bot?" → dijawab, **tidak** dioper ke admin), ack ("oke"), deny ("nggak jadi")

## Coba tanpa UI
    curl -s localhost:8000/reply -H 'Content-Type: application/json' \
      -d '{"conversation_id":"a1","message":"game steam di bawah 100rb"}'

## API
- POST /reply {conversation_id, message} -> {blocks:[text|products|quick_replies], intent, confidence, action, handoff, silent}
- POST /conversations/{id}/mode {mode:"AI"|"AGENT"}   (admin ambil alih / kembalikan ke bot)
- POST /admin/reload                                  (setelah sunting knowledge.yaml / products.json)

`action` baru: `compare`, `alternatives`, `not_found`, `handoff_order` (selain yang lama).

## Cara membuatnya makin pintar
1. data/log.jsonl mencatat tiap pesan (email/telepon di-mask).
2. `python -m tools.review_log` mengelompokkan pesan yang membuat bot ragu/gagal, menebak intent terdekat, dan
   mencetak kerangka YAML. Alat ini **tidak mengubah file**: kamu yang memutuskan contoh mana yang layak masuk.
3. Tambah kalimat itu ke "examples" di data/knowledge.yaml, lalu /admin/reload.
4. Jalankan `pytest -q tests` dan `python -m tools.evaluate` sebelum deploy. Tambah pesan nyata yang pernah gagal
   ke `tests/heldout*.py` agar tak terulang.
5. Setelah ada ribuan pesan: ganti pencocok TF-IDF dengan klasifikator terlatih milik sendiri (scikit-learn/fastText),
   lalu embedding multibahasa kecil untuk pencarian makna. Semua bisa jalan di CPU.

Catatan YAML: `yes`, `no`, `on`, `off` tanpa tanda kutip dibaca sebagai boolean. Tulis `"yes"` / `"no"`.

## Batas yang perlu diketahui
- Ambang keyakinan (HIGH/MID/ESC_MIN) dan contoh kalimat dituning pada set kecil buatan sendiri, bukan percakapan pelanggan
  sungguhan. Skor set uji bukan prediksi akurasi produksi; ukur ulang dengan log nyata.
- Katalog tak punya data genre/fitur, jadi permintaan seperti "game santai/horor" hanya bisa dijawab berdasar rating,
  dan bot mengatakannya terus terang.
- Deteksi "produk tak ada di katalog" memakai heuristik (pesan pendek + kata tak dikenal). Kata yang belum ada di contoh
  latih maupun katalog bisa salah dikira nama produk; tambahkan ke contoh bila sering terjadi.

## Yang HARUS diganti sebelum produksi
- data/knowledge.yaml: semua jawaban adalah CONTOH (termasuk promo, garansi, keaslian, jam operasional, masalah pembayaran),
  sesuaikan dengan kebijakan Jual Game yang sebenarnya.
- data/products.json: data contoh. Ganti KB.match_products/search/query/alternatives dengan query ke DB (full-text/trigram).
- Email support: ambil dari SiteSetting, jangan di file.
- Status order: jangan diaktifkan tanpa verifikasi (nomor order + email). Saat ini nomor order hanya dicatat dan dioper ke tim.
- State percakapan masih di memori proses: pindahkan ke DB/Redis (tabel ChatBotState dari plan).
- Label di UI: "asisten otomatis" (bukan klaim AI generatif).

## Deploy (website jualgame)
Bot berjalan di server yang sama dengan website, hanya di `127.0.0.1`, dan membaca harga/stok langsung dari website (`/api/bot/products`).
Langkah pemasangan, uji, dan operasional: **`docs/JUALGAME.md`**. Konfigurasi: `.env.example`. Compose produksi: `docker-compose.prod.yml`.
Deploy otomatis (`.github/workflows/deploy.yml`) mengirim kode ke server lewat rsync; secret: VPS_HOST, VPS_USER, VPS_SSH_KEY (kunci khusus deploy), VPS_PATH.

## Panel admin sendiri
Webhook handoff + API percakapan: lihat `docs/PANEL_ADMIN.md`.

## Fitur admin & rekomendasi
Discord, dasbor review `/admin/review`, dan tag produk: lihat `docs/FITUR_BARU.md`.
