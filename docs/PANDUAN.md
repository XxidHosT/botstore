# Panduan: install di VPS + sambungkan ke widget chat

## 1. Install di VPS (sekali)
Butuh: VPS Linux, domain yang A-record-nya mengarah ke IP VPS, akses SSH.

```bash
# a) Docker + rsync
curl -fsSL https://get.docker.com | sh
apt install -y rsync git

# b) ambil kode (setelah PR #1 di-merge ke main)
git clone https://github.com/XxidHosT/botstore /opt/botstore
cd /opt/botstore

# c) konfigurasi
cp .env.example .env
openssl rand -hex 32          # salin hasilnya ke ADMIN_TOKEN
nano .env                     # isi ADMIN_TOKEN, DOMAIN (mis. chat.tokomu.com), ALLOWED_ORIGINS (mis. https://tokomu.com)
chmod a+rwx data              # container berjalan non-root dan menulis data/state.db

# d) jalankan
docker compose -f docker-compose.prod.yml up -d --build
curl -s https://chat.tokomu.com/health      # -> {"ok":true}
```
Buka firewall untuk port 80 dan 443 saja (`ufw allow 80,443/tcp`). Port 8000 tidak perlu dibuka.

## 2. Sinkronisasi kode (update)
- **Otomatis:** push ke `main` -> GitHub Actions menguji, lalu mengirim kode ke VPS lewat rsync (isi secret `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` [kunci baru khusus deploy], `VPS_PATH=/opt/botstore`).
- **Manual:** `cd /opt/botstore && git pull && docker compose -f docker-compose.prod.yml up -d --build`
- **Ubah jawaban/katalog tanpa rebuild:** sunting `data/knowledge.yaml` atau `data/products.json`, lalu
  `curl -X POST https://chat.tokomu.com/admin/reload -H "Authorization: Bearer $ADMIN_TOKEN"`

## 3. Sambungkan ke widget chat
Widget cukup memanggil satu endpoint publik dari browser (pastikan domain situsmu ada di `ALLOWED_ORIGINS`):

`POST https://chat.tokomu.com/reply`  `{ "conversation_id": "<id unik per pengunjung>", "message": "teks" }`

Balasan: `{ blocks, intent, confidence, action, handoff, silent }`
- `blocks[]` bertipe `text` (`text`), `products` (`items[]`: name, price, stock, rating, url), `quick_replies` (`items[]`: label tombol; saat diklik, kirim label itu sebagai pesan berikutnya)
- `handoff: true` -> bot sudah meneruskan ke tim; tampilkan "menunggu admin"
- `silent: true` -> percakapan dipegang admin; **jangan** tampilkan balasan bot

Contoh minimal (JavaScript murni):
```html
<div id="log"></div><input id="in"><button id="go">Kirim</button>
<script>
const API = "https://chat.tokomu.com";
const cid = localStorage.cid ||= crypto.randomUUID();
const log = document.getElementById("log");
const add = (html) => log.insertAdjacentHTML("beforeend", html);
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function send(text) {
  add(`<p><b>Kamu:</b> ${esc(text)}</p>`);
  const r = await fetch(API + "/reply", {method: "POST", headers: {"Content-Type": "application/json"},
                                         body: JSON.stringify({conversation_id: cid, message: text})});
  if (r.status === 429) return add("<p><i>Pelan-pelan ya.</i></p>");
  const out = await r.json();
  if (out.silent) return;                                   // admin sedang menangani
  for (const b of out.blocks) {
    if (b.type === "text") add(`<p><b>Bot:</b> ${esc(b.text)}</p>`);
    if (b.type === "products") add(b.items.map(p => `<p><a href="${esc(p.url)}">${esc(p.name)}</a> ${esc(p.price)} (stok ${esc(p.stock)}, rating ${esc(p.rating)})</p>`).join(""));
    if (b.type === "quick_replies") add(b.items.map(t => `<button onclick="send(this.textContent)">${esc(t)}</button>`).join(" "));
  }
}
document.getElementById("go").onclick = () => { const i = document.getElementById("in"); if (i.value.trim()) send(i.value.trim()); i.value = ""; };
</script>
```
Catatan penting:
- Pakai `esc()` (atau textContent) untuk semua teks dari bot, jangan `innerHTML` mentah.
- Panggil API **langsung dari browser**. Jika lewat backend-mu, semua pengunjung tampak dari satu IP dan kena rate limit per IP.
- Live chat dengan admin: admin mengambil alih dengan
  `curl -X POST https://chat.tokomu.com/conversations/<id>/mode -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"mode":"AGENT"}'`
  (kembalikan ke bot dengan `"AI"`). Bot tidak mengirim pesan admin ke pengunjung; itu tugas sistem live chat-mu.
- Beri label UI "asisten otomatis" dan selalu sediakan tombol "Bicara dengan tim".

## 4. Cek setelah live
- `docker compose -f docker-compose.prod.yml logs -f chat-brain` untuk melihat error.
- `data/log.jsonl` mencatat pesan (email/telepon dimasker). Tiap minggu: `docker compose -f docker-compose.prod.yml exec chat-brain python -m tools.review_log`, tambahkan contoh pesan yang gagal ke `data/knowledge.yaml`, lalu reload.
- Sebelum dibuka ke pelanggan: ganti `data/knowledge.yaml` dan `data/products.json` (masih data contoh) dengan kebijakan dan katalog asli tokomu.
