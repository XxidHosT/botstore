# Memasang bot di server jualgame

Bot berjalan di server yang sama dengan website (PM2 + Caddy di `/var/www/jualgame`), hanya di `127.0.0.1`:

```
pengunjung -> Caddy -> Next.js (:3000) -> POST 127.0.0.1:8000/reply (bot)
                                          bot -> GET 127.0.0.1:3000/api/bot/products (X-Bot-Token)  [harga & stok asli]
```
Tidak ada port baru yang terbuka ke internet, dan tidak ada Caddy kedua. Bot mati/lambat -> chat website tetap jalan (bot kata kunci lama).

Prasyarat: PR website `claude/bot-integration` sudah di-merge dan di-deploy (lihat docs/BOT.md di repo website).

## 1. Pasang bot
```bash
# Docker (lewati bila sudah ada)
curl -fsSL https://get.docker.com | sh

git clone https://github.com/XxidHosT/botstore /opt/botstore && cd /opt/botstore
cp .env.example .env
TOKEN=$(openssl rand -hex 32); echo $TOKEN        # simpan; dipakai di langkah 2
nano .env       # ADMIN_TOKEN=<token lain>, CATALOG_TOKEN=$TOKEN, opsional DISCORD_WEBHOOK_URL
chmod a+rwx data
docker compose -f docker-compose.prod.yml up -d --build
curl -s http://127.0.0.1:8000/health              # {"ok":true}
```

## 2. Hubungkan website
Di `/var/www/jualgame/.env` tambahkan `BOT_API_TOKEN=$TOKEN` (sama dengan `CATALOG_TOKEN`) dan `BOT_URL=http://127.0.0.1:8000`, lalu
deploy website seperti biasa (`scripts/deploy-prod.sh`, yang kini juga menjalankan `prisma db push`) atau minimal
`pm2 restart jualgame --update-env`. Blokir `/api/bot/*` di Caddy publik (lihat docs/BOT.md langkah 3).

## 3. Uji
```bash
curl -s -H "x-bot-token: $TOKEN" "http://127.0.0.1:3000/api/bot/products?q=elden%20ring" | head -c 400   # JSON produk
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:3000/api/bot/products?q=elden"                 # 401
curl -s -H 'Content-Type: application/json' -d '{"conversation_id":"uji1","message":"harga elden ring berapa"}' http://127.0.0.1:8000/reply
```
Lalu buka widget di jualgame.id dan tanya "harga <game>" / "game santai" / "panggil admin"; inbox admin menampilkan pesan bot berlabel "Bot"
dan badge **Butuh admin** setelah handoff.

## 4. Operasional
- **Dasbor review** (bot belajar dari pesan yang gagal): hanya di loopback. Dari laptop: `ssh -L 8000:127.0.0.1:8000 user@server`, lalu buka
  `http://localhost:8000/admin/review` dan masukkan `ADMIN_TOKEN` bot.
- **Discord**: isi `DISCORD_WEBHOOK_URL` di `.env` bot, `docker compose -f docker-compose.prod.yml up -d`. Lihat docs/FITUR_BARU.md.
- **Katalog/harga**: tidak ada yang perlu di-sync; bot membaca tabel `KinguinProduct` langsung (cache 30 dtk). Ubah kata/tag lewat `data/knowledge.yaml`
  (`tag_aliases`, `tag_genres`); berlaku otomatis tanpa restart.
- **Log**: `docker compose -f docker-compose.prod.yml logs -f chat-brain`; pesan tercatat di `data/log.jsonl` (email/telepon dimasker).
- **Update bot**: `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
- **Matikan bot**: hapus `BOT_URL` di `.env` website + `pm2 restart jualgame --update-env`.

## 5. Yang sudah dan belum diuji
Diuji end-to-end di lingkungan pengembangan (Next.js dev + SQLite berisi katalog contoh + bot asli + browser): harga "mulai dari", stok habis
+ alternatif, produk tak dikenal, perbandingan (skor Metacritic), total, tag genre, jenis voucher, handoff -> `needsAgent` -> bot diam, widget
menampilkan kartu produk. **Belum diuji**: database dan katalog asli (130 ribu baris; nama genre nyata, kecepatan query), Discord sungguhan,
`deploy-prod.sh` yang diubah, dan Caddy di server. Lakukan uji langkah 3 di server sebelum mengumumkan.

## 6. Belum ada
- **Status order**: bot belum mengecek `KinguinOrder`. Butuh verifikasi pemilik (login atau nomor order + email); belum dibuat agar tidak membocorkan
  data pesanan orang lain.
