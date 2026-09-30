(() => {
  const $ = (s) => document.querySelector(s);
  let token = sessionStorage.getItem("adm") || "";
  let intents = [];
  const say = (t) => { $("#msg").textContent = t || ""; };
  const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); kids.forEach(k => e.append(k)); return e; };

  async function api(path, opts = {}) {
    const r = await fetch(path, {...opts, headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json"}});
    if (r.status === 401) { sessionStorage.removeItem("adm"); token = ""; throw new Error("Token salah. Muat ulang halaman lalu masukkan lagi."); }
    if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch (e) {} throw new Error(d || ("Error " + r.status)); }
    return r.json();
  }

  async function load() {
    const [ov, ln] = await Promise.all([api("/admin/api/review"), api("/admin/api/learned")]);
    const s = ov.stats;
    $("#stats").textContent = `${s.messages} pesan | ragu/gagal ${s.weak_pct}% | eskalasi ${s.handoffs} | menunggu review ${s.waiting_review}`;
    const tb = $("#items tbody"); tb.replaceChildren();
    ov.items.forEach(it => {
      const sel = el("select", {}, ...intents.map(i => el("option", {value: i.name, textContent: i.name + (i.label ? " (" + i.label + ")" : "")})));
      if (it.guess[0]) sel.value = it.guess[0].intent;
      const guess = el("div", {}, ...it.guess.map(g => el("button", {className: "chip", textContent: `${g.intent} ${g.score}`, onclick: () => { sel.value = g.intent; }})));
      const save = el("button", {className: "pri", textContent: "Simpan", disabled: it.masked, title: it.masked ? "Berisi data pribadi (dimasker)" : "",
        onclick: async () => { try { await api("/admin/api/review/label", {method: "POST", body: JSON.stringify({text: it.text, intent: sel.value})}); say("Tersimpan. Bot langsung memakainya."); load(); } catch (e) { say(e.message); } }});
      const skip = el("button", {textContent: "Abaikan", onclick: async () => { try { await api("/admin/api/review/dismiss", {method: "POST", body: JSON.stringify({text: it.text})}); load(); } catch (e) { say(e.message); } }});
      tb.append(el("tr", {},
        el("td", {textContent: it.count + "x"}),
        el("td", {}, el("div", {textContent: it.text, className: it.masked ? "masked" : ""}), el("code", {textContent: Object.entries(it.actions).map(([k, v]) => k + " " + v).join(", ")})),
        el("td", {}, guess), el("td", {}, sel), el("td", {}, save, " ", skip)));
    });
    if (!ov.items.length) tb.append(el("tr", {}, el("td", {colSpan: 5, textContent: "Tidak ada pesan yang menunggu review."})));
    const lb = $("#learned tbody"); lb.replaceChildren();
    ln.items.forEach(x => lb.append(el("tr", {}, el("td", {textContent: x.intent}), el("td", {textContent: x.lang}), el("td", {textContent: x.text}),
      el("td", {}, el("button", {textContent: "Batalkan", onclick: async () => { try { await api("/admin/api/learned/remove", {method: "POST", body: JSON.stringify(x)}); load(); } catch (e) { say(e.message); } }})))));
    if (!ln.items.length) lb.append(el("tr", {}, el("td", {colSpan: 4, textContent: "Belum ada."})));
  }

  async function start() {
    if (!token) { token = prompt("ADMIN_TOKEN:") || ""; if (token) sessionStorage.setItem("adm", token); }
    $("#logout").hidden = !token;
    $("#logout").onclick = () => { sessionStorage.removeItem("adm"); location.reload(); };
    try { intents = (await api("/admin/api/intents")).items; await load(); } catch (e) { say(e.message); }
  }
  start();
})();
