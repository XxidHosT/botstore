# Panduan lama (diganti)

Panduan ini dulu untuk pemasangan mandiri dengan Caddy sendiri dan widget contoh. Untuk website **jualgame** yang sudah live
(PM2 + Caddy, widget chat sendiri), ikuti **[docs/JUALGAME.md](JUALGAME.md)**.

Kontrak API `/reply` (bila suatu saat dipakai widget lain) tidak berubah: `POST /reply {conversation_id, message}` ->
`{blocks, intent, confidence, action, handoff, silent}`; lihat README.
