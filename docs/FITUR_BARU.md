# Discord, dasbor review, dan tag produk

## Notifikasi Discord saat handoff
1. Discord: buka channel admin -> Edit Channel -> Integrations -> Webhooks -> New Webhook -> Copy Webhook URL.
2. Di `.env` VPS: `DISCORD_WEBHOOK_URL=<url>`. Opsional: `PANEL_LINK_TEMPLATE=https://panel.tokomu.com/chat/{id}` (judul pesan jadi tautan ke chat
   di panelmu) dan `DISCORD_MENTION_ROLE_ID=<id role>` (mention satu role; `@everyone`/`@here` tidak pernah dipicu, termasuk dari teks pelanggan).
3. Restart: `docker compose -f docker-compose.prod.yml up -d`.

Pesan berisi 6 pesan terakhir (email/telepon dimasker), ID percakapan, dan alasan. Hanya event handoff yang dikirim ke Discord; pesan
pelanggan selama takeover hanya ke webhook panel (`HANDOFF_WEBHOOK_URL`). Keduanya boleh aktif bersamaan. URL webhook Discord bersifat rahasia:
siapa pun yang memilikinya bisa mengirim pesan ke channel-mu, jadi simpan hanya di `.env`.

## Dasbor review (belajar dari log)
Buka `https://DOMAIN/admin/review`, masukkan `ADMIN_TOKEN` (disimpan di sessionStorage tab itu saja).
- Tabel: pesan yang bot ragu atau gagal pahami, dikelompokkan, dengan jumlah kemunculan dan tebakan intent.
- **Simpan**: pilih intent yang benar -> jadi contoh latih di `data/learned.json`; bot memakainya seketika di semua worker.
- **Abaikan**: sembunyikan pesan sampah. **Batalkan**: hapus contoh yang salah dari daftar "sudah dipelajari".
- Pesan yang berisi email/telepon (dimasker) tidak bisa disimpan sebagai contoh.
- `learned.json` terpisah dari `knowledge.yaml`, dan tidak ditimpa saat deploy (sudah dikecualikan di `deploy.yml`).
- Hati-hati: label yang salah membuat bot salah. Setelah menyimpan banyak contoh, coba beberapa pesan nyata; bila ada yang aneh, batalkan contohnya.

## Tag produk
Di `data/products.json` tiap produk punya `tags` (mis. `["santai","farming","multiplayer"]`). Kata pelanggan dipetakan ke tag lewat `tag_aliases`
di `data/knowledge.yaml` ("berdua", "bareng", "co-op" -> `multiplayer`; "relax", "chill" -> `santai`).
- "game santai" / "game buat main berdua" -> bot menyaring dari tag, hanya produk yang stoknya ada.
- Tag yang tak dimiliki produk mana pun (mis. "horor") -> bot bilang belum ada, lalu menampilkan yang rating tertinggi. Tidak ada tebakan.
- Tag di file contoh hanyalah contoh. Ganti dengan tag katalog aslimu; makin lengkap tag, makin pintar bot merekomendasikan.

## Catatan data & deploy
Berkas di `data/` yang ditulis saat bot berjalan: `state.db`, `log.jsonl`, `learned.json`, `review_dismissed.json`. Semuanya harus **tidak** ditimpa
saat deploy. Workflow `deploy.yml` sudah mengecualikan semuanya.
