# Integrasi dengan panel admin sendiri

Alur: pelanggan chat -> bot menjawab. Bila perlu manusia (`handoff`), bot **memberi tahu panelmu lewat webhook**, panel
mengambil alih dengan API, admin membalas lewat sistem chat panelmu, lalu mengembalikan ke bot.

## 1. Webhook dari bot ke panel
Set `HANDOFF_WEBHOOK_URL` dan `HANDOFF_WEBHOOK_SECRET` di `.env`. Bot mengirim `POST` JSON (timeout 3 dtk, 3x percobaan,
tidak pernah menghambat balasan ke pelanggan). Dua jenis event:

```json
{"event":"handoff","conversation_id":"abc","reason":"handoff","intent":"human","lang":"id","ts":1790000000,
 "history":[{"role":"user","text":"panggil admin dong"},{"role":"bot","text":"Aku teruskan ke tim ya..."}]}

{"event":"customer_message","conversation_id":"abc","text":"kok belum dibalas?","ts":1790000100,"history":[...]}
```
- `handoff`: percakapan baru butuh admin. Munculkan di antrean panel.
- `customer_message`: pelanggan mengetik selagi admin memegang chat. Bot tetap diam (`silent:true` ke widget), jadi
  **panelmu yang menampilkan pesan ini** ke admin.
- Email dan nomor telepon di `history`/`text` sudah dimasker (`<email>`, `<telp>`).

Verifikasi asal: header `X-Signature: sha256=<hex>` = HMAC-SHA256 dari body mentah dengan `HANDOFF_WEBHOOK_SECRET`.
```python
import hmac, hashlib
ok = hmac.compare_digest(request.headers["X-Signature"], "sha256=" + hmac.new(SECRET.encode(), raw_body, hashlib.sha256).hexdigest())
```
Tolak request yang signature-nya tidak cocok.

## 2. API dari panel ke bot (semua butuh `Authorization: Bearer $ADMIN_TOKEN`)
| Endpoint | Fungsi |
|---|---|
| `GET /conversations` | daftar percakapan yang menunggu/dipegang admin: `{items:[{conversation_id, ts, lang, last}]}` |
| `GET /conversations/{id}` | `{mode, handoff, lang, history[]}` (20 pesan terakhir) |
| `POST /conversations/{id}/mode` `{"mode":"AGENT"}` | admin mengambil alih (bot diam) |
| `POST /conversations/{id}/mode` `{"mode":"AI"}` | admin selesai, kembalikan ke bot (percakapan keluar dari antrean) |

## 3. Pesan admin ke pelanggan
Bot **tidak** mengirim pesan admin. Kirim lewat kanal chat panelmu ke widget yang sama (mis. WebSocket/polling milikmu),
lalu widget menampilkannya. Widget tetap mengirim pesan pelanggan ke `/reply`; saat mode AGENT, bot membalas `silent:true`
dan meneruskan pesannya ke webhook.

## 4. Catatan
- Panggil API admin dari **server** panelmu, bukan dari browser (token tidak boleh tampil di JavaScript).
- Simpan `ADMIN_TOKEN` dan `HANDOFF_WEBHOOK_SECRET` hanya di `.env`/secret manager.
- `GET /conversations` memindai tabel state; cukup untuk ribuan percakapan. Bila jauh lebih besar, beri indeks/kolom khusus.
