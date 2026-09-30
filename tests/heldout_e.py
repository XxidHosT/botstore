"""Set E: dijalankan sekali, tanpa tuning sesudahnya. Format sama dengan heldout.py."""

CASES = [
    ("e_price_short", ["stardew brp"], {"has": ["89.000"]}),
    ("e_stock_en", ["got any robux left?"], {"has": ["in stock"]}),
    ("e_range_id", ["ada apa aja di kisaran 100 sampai 160 ribu"], {"has": ["Robux"], "no": ["Elden"]}),
    ("e_qty_x", ["minecraft x2 berapa"], {"has": ["718.000"]}),
    ("e_unknown", ["ada fortnite v-bucks ga"], {"action": "not_found"}),
    ("e_howbuy_short", ["caranya beli gimana kak"], {"intent": "how_to_buy"}),
    ("e_pay_gopay", ["shopeepay bisa?"], {"intent": "payment_methods"}),
    ("e_deliv", ["berapa lama key nya dikirim"], {"intent": "delivery"}),
    ("e_license", ["key nya invalid nih"], {"intent": "license"}),
    ("e_human_en", ["let me talk to a real person"], {"handoff": True}),
    ("e_complaint", ["pelayanan lambat banget kecewa"], {"handoff": True}),
    ("e_promo", ["ada kode promo ga"], {"intent": "promo"}),
    ("e_bot", ["are you a bot?"], {"intent": "bot_identity", "handoff": False}),
    ("e_greet_slang", ["halo min"], {"intent": "greeting"}),
    ("e_cheaper_ctx", ["minecraft berapa", "yang lebih murah ada?"], {"has": ["Stardew"]}),
    ("e_oos_en", ["is cyberpunk available"], {"has": ["out of stock"]}),
]
