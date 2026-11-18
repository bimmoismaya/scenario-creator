"use strict";
const $ = (id) => document.getElementById(id);
const TABS = [["statistic", "Statistic"], ["skenario", "Skenario"], ["analisa", "Analisa"], ["bugs", "Bug List"]];
let timer;
let preview = {};
let current = "statistic";
// Semua teks dari spec lewat node teks DOM, bukan markup mentah.
function el(tag, props, ...kids) {
    const e = document.createElement(tag);
    if (props)
        for (const k in props) {
            if (k === "class")
                e.className = props[k];
            else
                e.setAttribute(k, props[k]);
        }
    for (const k of kids.flat())
        if (k != null)
            e.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return e;
}
const show = (id, on) => $(id).classList.toggle("hidden", !on);
function showErr(id, msg) { $(id).textContent = msg; show(id, !!msg); }
// Grup isian berulang: 2 baris awal, bisa tambah dan hapus (minimal 1 baris).
const SOURCES = [
    { id: "fsd", label: "Dokumen FSD", note: "(.docx atau .pdf, maks 20 MB; minimal satu)", type: "file", accept: ".docx,.pdf" },
    { id: "swagger_url", label: "Link Swagger / API contract", note: "(opsional)", type: "url", ph: "https://..." },
    { id: "figma_url", label: "Link Figma", note: "(opsional)", type: "url", ph: "https://www.figma.com/design/..." },
    { id: "git_path", label: "Folder Git lokal", note: "(opsional; path absolut di mesin server, dibaca langsung, tidak diunggah)", type: "text", ph: "/home/user/git/proyek" },
];
function sourceGroup(s) {
    const root = $(s.id), rows = el("div");
    const renum = () => [...rows.children].forEach((r, i) => {
        r.firstElementChild.setAttribute("aria-label", `${s.label} ke-${i + 1}`);
        r.lastElementChild.disabled = rows.children.length === 1;
    });
    const add = () => {
        const inp = el("input", { type: s.type, name: s.id });
        if (s.accept)
            inp.setAttribute("accept", s.accept);
        if (s.ph)
            inp.setAttribute("placeholder", s.ph);
        const del = el("button", { type: "button", class: "ghost" }, "Hapus");
        del.onclick = () => { del.parentElement.remove(); renum(); };
        rows.append(el("div", { class: "src-row" }, inp, del));
        renum();
    };
    add();
    add();
    const more = el("button", { type: "button", class: "ghost src-add" }, "+ Tambah");
    more.onclick = add;
    root.append(el("div", { class: "lbl" }, s.label + " ", el("small", null, s.note)), rows, more);
}
SOURCES.forEach(sourceGroup);
const inputs = (id) => [...$(id).querySelectorAll("input")];
const vals = (id) => inputs(id).map(i => i.value.trim()).filter(Boolean);
const fsdFiles = () => inputs("fsd").flatMap(i => [...(i.files ?? [])]);
function showLogin() { try {
    sessionStorage.removeItem("in");
}
catch (e) { } show("app", false); show("login", true); }
function showApp() { try {
    sessionStorage.setItem("in", "1");
}
catch (e) { } show("login", false); show("app", true); }
let signedIn = false;
try {
    signedIn = sessionStorage.getItem("in") === "1";
}
catch (e) { }
signedIn ? showApp() : showLogin();
$("loginForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    showErr("loginErr", "");
    const r = await fetch("/api/login", { method: "POST", body: new URLSearchParams({ password: $("password").value }) }).catch(() => null);
    if (!r)
        return showErr("loginErr", "Server tidak terjangkau.");
    if (r.ok) {
        $("password").value = "";
        return showApp();
    }
    showErr("loginErr", r.status === 429 ? "Terlalu banyak percobaan salah. Coba lagi 5 menit lagi." : "Password salah.");
});
function setBusy(b) { const g = $("generate"); g.disabled = b; g.textContent = b ? "Sedang diproses..." : "Generate skenario"; }
const field = (id) => $(id);
$("form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    showErr("formErr", "");
    const files = fsdFiles();
    if (!field("dev").value || !field("test").value || !field("title").value.trim())
        return showErr("formErr", "Sprint dev, sprint testing, dan judul wajib diisi.");
    if (!files.length)
        return showErr("formErr", "Pilih minimal satu file FSD (.docx atau .pdf).");
    for (const f of files) {
        if (!/\.(docx|pdf)$/i.test(f.name))
            return showErr("formErr", "Ekstensi FSD harus .docx atau .pdf: " + f.name);
        if (f.size > 20 * 1024 * 1024)
            return showErr("formErr", "File FSD lebih dari 20 MB: " + f.name);
    }
    const fd = new FormData();
    for (const k of ["dev", "test", "title", "environment", "scope_note", "roles"])
        fd.append(k, field(k).value.trim());
    for (const k of ["swagger_url", "figma_url", "git_path"])
        vals(k).forEach(v => fd.append(k, v));
    files.forEach(f => fd.append("fsd", f));
    setBusy(true);
    show("result", false);
    show("progress", true);
    $("stage").textContent = "Mengunggah...";
    $("queue").textContent = "";
    const r = await fetch("/api/generate", { method: "POST", body: fd }).catch(() => null);
    if (!r)
        return fail("Server tidak terjangkau.");
    if (r.status === 401) {
        fail("");
        return showLogin();
    }
    if (!r.ok) {
        const m = { 413: "File lebih dari 20 MB.", 422: "Isian belum lengkap atau jenis file salah." };
        const d = r.status === 422 ? (await r.json().catch(() => null))?.detail : null;
        return fail(typeof d === "string" ? d : m[r.status] || "Gagal memulai job (HTTP " + r.status + ").");
    }
    const { job_id } = await r.json();
    poll(job_id);
});
function fail(msg) { clearTimeout(timer); setBusy(false); show("progress", false); showErr("formErr", msg); }
function poll(id) {
    clearTimeout(timer);
    fetch("/api/jobs/" + encodeURIComponent(id)).then(async (r) => {
        if (r.status === 401) {
            fail("");
            return showLogin();
        }
        if (!r.ok)
            return fail("Status job tidak bisa dibaca (HTTP " + r.status + ").");
        const j = await r.json();
        if (j.state === "done") {
            setBusy(false);
            show("progress", false);
            return render(id, j.preview);
        }
        if (j.state === "failed")
            return fail("Job gagal: " + (j.error || "alasan tidak diketahui") + ". Hubungi admin bila berulang.");
        $("stage").textContent = j.stage || (j.state === "queued" ? "Menunggu antrian" : "Memproses");
        $("queue").textContent = j.state === "queued" && (j.queue_pos ?? 0) > 0 ? "Antrian: " + j.queue_pos + " job di depan Anda" : "";
        timer = window.setTimeout(() => poll(id), 3000);
    }).catch(() => { timer = window.setTimeout(() => poll(id), 3000); });
}
function render(id, p) {
    preview = p || {};
    current = "statistic";
    $("download").href = "/api/jobs/" + encodeURIComponent(id) + "/download";
    drawWarn();
    show("result", true);
    drawTabs();
    drawPanel();
    $("result").scrollIntoView({ behavior: "smooth" });
}
function drawWarn() {
    const w = $("warn"), items = (preview.peringatan || []).filter((x) => typeof x === "string");
    w.replaceChildren();
    show("warn", items.length > 0);
    if (items.length)
        w.append(el("b", null, "Peringatan mutu"), el("ul", null, ...items.map(x => el("li", null, x))));
}
function drawTabs() {
    const t = $("tabs");
    t.replaceChildren();
    for (const [k, name] of TABS) {
        const n = k === "statistic" ? "" : " (" + countOf(k) + ")";
        const b = el("button", { type: "button", role: "tab", "aria-selected": String(k === current) }, name + n);
        b.onclick = () => { current = k; drawTabs(); drawPanel(); };
        t.append(b);
    }
}
const countOf = (k) => k === "skenario" ? (preview.skenario || []).reduce((a, s) => a + (s.cases || []).length, 0) : (preview[k] || []).length;
const empty = (msg) => el("p", { class: "hint" }, msg);
const panels = { statistic, skenario, analisa, bugs };
function drawPanel() { $("panel").replaceChildren(panels[current]()); }
function statistic() {
    const s = preview.statistic || {};
    const box = (title, obj) => el("div", { class: "stat" }, el("h3", null, title), ...Object.entries(obj || {}).map(([k, v]) => el("div", { class: "row" }, el("span", null, k ?? "-"), el("b", null, v))));
    return el("div", { class: "stats" }, el("div", { class: "stat" }, el("h3", null, "Total test case"), el("div", { class: "n" }, s.total ?? 0)), box("Tipe", s.type), box("Prioritas", s.priority), box("Platform", s.platform));
}
function skenario() {
    const secs = preview.skenario || [];
    if (!secs.length)
        return empty("Tidak ada skenario.");
    const out = el("div");
    for (const s of secs) {
        out.append(el("div", { class: "sec" }, s.title));
        const rows = (s.cases || []).map((c, i) => {
            const warn = /perlu verifikasi/i.test((c.notes || "") + (c.expected || []).join(" "));
            return el("tr", null, el("td", null, i + 1), el("td", null, c.type), el("td", null, c.priority), el("td", null, c.desc, warn ? el("div", null, el("span", { class: "tag warn" }, "Perlu verifikasi")) : null), el("td", null, el("ol", null, (c.steps || []).map(x => el("li", null, x)))), el("td", null, el("ol", null, (c.expected || []).map(x => el("li", null, x)))), el("td", null, c.platform), el("td", null, c.notes));
        });
        out.append(el("div", { class: "tw" }, el("table", null, el("thead", null, el("tr", null, ["No", "Tipe", "Prio", "Deskripsi", "Langkah", "Hasil diharapkan", "Platform", "Notes"].map(h => el("th", null, h)))), el("tbody", null, rows))));
    }
    return out;
}
function analisa() {
    const a = preview.analisa || [];
    if (!a.length)
        return empty("Tidak ada temuan analisa.");
    return el("div", null, a.map(x => el("div", { class: "acard" }, el("div", null, el("span", { class: "tag" }, x.category), " ", el("span", { class: "k" }, [x.ref, x.source, x.confidence && "keyakinan " + x.confidence].filter(Boolean).join(" | "))), el("p", null, x.finding), x.impact ? el("p", null, el("span", { class: "k" }, "Dampak: "), x.impact) : null, x.question ? el("p", null, el("span", { class: "k" }, "Pertanyaan: "), x.question) : null, x.cases ? el("p", { class: "k" }, "Case terkait: " + x.cases) : null)));
}
function bugs() {
    const b = preview.bugs || [];
    if (!b.length)
        return empty("Belum ada bug tercatat. Daftar ini diisi tester saat pengujian.");
    const keys = Object.keys(b[0]);
    return el("div", { class: "tw" }, el("table", null, el("thead", null, el("tr", null, keys.map(k => el("th", null, k)))), el("tbody", null, b.map(r => el("tr", null, keys.map(k => el("td", null, r[k])))))));
}
