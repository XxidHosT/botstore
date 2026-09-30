"""Set B: pesan baru yang belum pernah dilihat saat mengembangkan. Dijalankan SEKALI untuk mengukur generalisasi.
Format sama dengan heldout.py."""

CASES = [
    # --- harga / stok / ganda ---
    ("b_stock_natural", ["min stok stardew masih ada ga"], {"has": ["tersedia"]}),
    ("b_both_cyber", ["cyberpunk ada? sama harganya"], {"has": ["299.000", "habis"]}),
    ("b_price_sih", ["elden ring berapa sih sekarang"], {"has": ["459.000"]}),
    ("b_delivery_with_product", ["kirim robux nya berapa menit"], {"intent": "delivery"}),
    ("b_two_products_price", ["berapa harga steam wallet 100k sama robux 800"], {"has": ["105.000", "149.000"]}),
    ("b_price_en_short", ["Elden Ring price"], {"has": ["459.000"]}),
    ("b_price_alias", ["minecraft java doang berapa"], {"has": ["359.000"]}),
    ("b_greet_prefix_id", ["halo kak harga minecraft berapa ya"], {"has": ["359.000"]}),
    ("b_greet_prefix_en", ["hello, how much is elden ring?"], {"has": ["459.000"]}),
    ("b_thanks_prefix", ["thanks! is cyberpunk in stock?"], {"has": ["out of stock"]}),
    ("b_buy_two", ["beli 2 elden ring bisa?"], {"has": ["Elden Ring"]}),
    ("b_voucher_ask", ["voucher steam 100rb ada?"], {"has": ["Steam Wallet"]}),
    ("b_topup", ["ada top up roblox 800?"], {"has": ["Robux"]}),
    # --- katalog berfilter ---
    ("b_game_pc", ["game pc ada apa aja"], {"has": ["Minecraft"], "no": ["Robux"]}),
    ("b_budget_400", ["budget 400rb, mending yang mana"], {"has": ["Minecraft", "Stardew"], "no": ["Elden Ring"]}),
    ("b_max_100", ["max 100 ribu"], {"has": ["Stardew"], "no": ["Steam Wallet"]}),
    ("b_above_300", ["diatas 300rb apa aja"], {"has": ["Elden Ring"], "no": ["Stardew"]}),
    ("b_best_rating", ["yang paling bagus rating nya apa"], {"has": ["Stardew"]}),
    ("b_priciest_short", ["termahal"], {"has": ["Elden Ring"]}),
    ("b_cheaper_than", ["ada yang lebih murah dari elden ring"], {"has": ["Stardew"]}),
    ("b_en_budget", ["im looking for something under 100k"], {"has": ["Stardew"], "no": ["Elden Ring"]}),
    ("b_budget_slang", ["budget gue 90rb"], {"has": ["Stardew"]}),
    ("b_cheapest_steam", ["cheapest steam key"], {"has": ["Stardew"]}),
    ("b_compare_diff", ["beda robux sama steam wallet apa"], {"has": ["149.000", "105.000"]}),
    ("b_compare_short", ["minecraft vs stardew"], {"has": ["359.000", "89.000"]}),
    # --- konteks ---
    ("b_ctx_bare_harganya", ["stok elden ring", "harganya?"], {"has": ["459.000"]}),
    ("b_ctx_and_en", ["how much is minecraft", "and stardew?"], {"has": ["89.000"]}),
    ("b_ctx_kalo_alias", ["harga minecraft", "kalo yang 800 robux?"], {"has": ["149.000"]}),
    ("b_ctx_oos_reco", ["cyberpunk ready ga? kalo ga ada rekomen yang mirip dong"], {"has": ["Stardew"]}),
    ("b_ctx_expensive_ref", ["harga elden ring", "kemahalan"], {"has": ["Stardew"], "handoff": False}),
    # --- slot ---
    ("b_slot_price", ["harga nya berapa ya kak"], {"action": "ask_slot"}),
    ("b_slot_stock", ["stok berapa"], {"action": "ask_slot"}),
    # --- intent lama, frasa baru ---
    ("b_pay_shopeepay", ["bisa bayar pakai shopeepay ga"], {"intent": "payment_methods"}),
    ("b_pay_methods", ["metode pembayaran apa aja"], {"intent": "payment_methods"}),
    ("b_license_redeem", ["gimana caranya redeem key steam"], {"intent": "license"}),
    ("b_license_invalid", ["keynya invalid terus"], {"intent": "license"}),
    ("b_refund_how", ["cara refund gimana"], {"intent": "refund"}),
    ("b_late", ["kok lama banget belum dikirim"], {"intent": ("delivery", "order_status", "complaint")}),
    ("b_greet_admin", ["halo admin, mau tanya dong"], {"intent": "greeting"}),
    ("b_thanks_helpful", ["makasih kak, sangat membantu"], {"intent": "thanks"}),
    ("b_bye", ["sampai nanti ya"], {"intent": "goodbye"}),
    # --- intent baru, frasa baru ---
    ("b_official_store", ["apakah ini toko resmi?"], {"intent": "authenticity"}),
    ("b_hours_reply", ["jam berapa admin balas"], {"intent": "hours"}),
    ("b_bot_robot", ["kamu robot?"], {"intent": "bot_identity", "handoff": False}),
    ("b_promo_pct", ["diskon 20% ga bisa ya?"], {"intent": "promo", "no_text": ["20%"]}),
    ("b_promo_ask_discount", ["kasih diskon dong 50%"], {"intent": "promo", "no_text": ["50%"]}),
    ("b_human", ["mau bicara sama manusia"], {"intent": "human", "handoff": True}),
    ("b_buy_and_promo", ["aku mau beli elden ring, ada diskon ga"], {"intent": ("promo", "find_product"), "handoff": False}),
    # --- nomor order ---
    ("b_order_inv", ["order INV20931 belum sampai"], {"handoff": True, "has": ["INV20931"]}),
    ("b_order_number_only", ["nomor pesanan 771234"], {"handoff": True, "has": ["771234"]}),
    ("b_order_noisy", ["halo min, kmrn saya beli key elden ring tp gak bisa di redeem, order INV-99321, tolong dibantu"], {"handoff": True, "has": ["INV-99321"]}),
    # --- fallback ---
    ("b_nonsense", ["gpp lah"], {"handoff": False}),
    ("b_asdf", ["asdf"], {"action": "miss1", "handoff": False}),
    ("b_offtopic_no_price", ["berapa harga bitcoin sekarang"], {"no_text": ["Rp"]}),
]
