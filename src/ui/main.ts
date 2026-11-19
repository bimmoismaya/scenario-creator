interface Case { type?: string; priority?: string; desc?: string; steps?: string[]; expected?: string[]; platform?: string; notes?: string }
interface Section { title: string; cases?: Case[] }
interface Finding { category?: string; ref?: string; source?: string; confidence?: string; finding?: string; impact?: string; question?: string; cases?: string }
interface Preview {
  statistic?: { total?: number; type?: Counts; priority?: Counts; platform?: Counts };
  skenario?: Section[]; analisa?: Finding[]; bugs?: Record<string, unknown>[]; peringatan?: unknown[];
}
type Counts = Record<string, number>;
type Tab = "statistic" | "skenario" | "analisa" | "bugs";
interface Source { id: string; label: string; note: string; type: string; accept?: string; ph?: string; dir?: boolean }
interface JobStatus { state: string; stage?: string; queue_pos?: number; error?: string; preview?: Preview }

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const TABS: [Tab, string][] = [["statistic", "Statistic"], ["skenario", "Skenario"], ["analisa", "Analisa"], ["bugs", "Bug List"]];
let timer: number | undefined;
let preview: Preview = {};
let current: Tab = "statistic";

// Semua teks dari spec lewat node teks DOM, bukan markup mentah.
function el(tag: string, props?: Record<string, string> | null, ...kids: unknown[]): HTMLElement {
  const e = document.createElement(tag);
  if (props) for (const k in props) { if (k === "class") e.className = props[k]; else e.setAttribute(k, props[k]); }
  for (const k of kids.flat()) if (k != null) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}
const show = (id: string, on: boolean) => $(id).classList.toggle("hidden", !on);
function showErr(id: string, msg: string) { $(id).textContent = msg; show(id, !!msg); }

// Grup isian berulang: 2 baris awal, bisa tambah dan hapus (minimal 1 baris).
const SOURCES: Source[] = [
  { id: "fsd", label: "Dokumen FSD", note: "(.docx atau .pdf, maks 20 MB; minimal satu)", type: "file", accept: ".docx,.pdf" },
  { id: "swagger_url", label: "Link Swagger / API contract", note: "(opsional)", type: "url", ph: "https://..." },
  { id: "figma_url", label: "Link Figma", note: "(memakai kuota Figma MCP)", type: "url", ph: "https://www.figma.com/design/..." },
  { id: "figma_file", label: "File desain Figma", note: "(gambar apa pun, PDF, ZIP, atau RAR; maks 50 MB per file)", type: "file", accept: "image/*,.pdf,.zip,.rar" },
  { id: "git_path", label: "Folder Git lokal", note: "(opsional; pilih folder repo di server, tanpa upload)", type: "text", dir: true },
];
function sourceGroup(s: Source) {
  const root = $(s.id), rows = el("div");
  const renum = () => [...rows.children].forEach((r, i) => {
    (r.firstElementChild as HTMLInputElement).setAttribute("aria-label", `${s.label} ke-${i + 1}`);
    (r.lastElementChild as HTMLButtonElement).disabled = rows.children.length === 1;
  });
  const add = () => {
    const inp = el("input", { type: s.type, name: s.id });
    if (s.dir) { inp.setAttribute("readonly", ""); inp.setAttribute("placeholder", "Belum dipilih"); }
    if (s.accept) inp.setAttribute("accept", s.accept);
    if (s.ph) inp.setAttribute("placeholder", s.ph);
    const del = el("button", { type: "button", class: "ghost" }, "Hapus");
    del.onclick = () => { del.parentElement!.remove(); renum(); };
    const row = el("div", { class: "src-row" }, inp);
    if (s.dir) {
      const pick = el("button", { type: "button", class: "ghost" }, "Pilih folder");
      pick.onclick = () => pickFolder().then(p => { if (p) (inp as HTMLInputElement).value = p; });
      row.append(pick);
    }
    row.append(del); rows.append(row); renum();
  };
  add(); add();
  const more = el("button", { type: "button", class: "ghost src-add" }, "+ Tambah");
  more.onclick = add;
  root.append(el("div", { class: "lbl" }, s.label + " ", el("small", null, s.note)), rows, more);
}
SOURCES.forEach(sourceGroup);
const inputs = (id: string) => [...$(id).querySelectorAll("input")];
const vals = (id: string) => inputs(id).map(i => i.value.trim()).filter(Boolean);
// Folder Git: dipilih dari daftar folder di server (dibatasi GIT_ROOTS), tidak ada file yang diunggah.
interface Dirs { path: string; parent: string; repo: boolean; dirs: { name: string; path: string; repo: boolean }[] }
function pickFolder(): Promise<string> {
  const dlg = $<HTMLDialogElement>("picker");
  let cur = "", parent = "", seq = 0, res: (p: string) => void = () => {};
  const go = async (path: string) => {
    showErr("pk-err", "");
    const me = ++seq;  // respons lama yang datang terlambat diabaikan
    const r = await fetch("/api/git/dirs?path=" + encodeURIComponent(path)).catch(() => null);
    if (me !== seq) return;
    if (!r) return showErr("pk-err", "Server tidak terjangkau.");
    if (r.status === 401) { dlg.close(); res(""); return showLogin(); }
    const j = await r.json().catch(() => null) as (Dirs & { detail?: string }) | null;
    if (me !== seq) return;
    if (!r.ok || !j) return showErr("pk-err", j?.detail || "Folder tidak bisa dibuka.");
    cur = j.path; parent = j.parent;
    $("pk-path").textContent = cur || "Folder induk yang diizinkan";
    $<HTMLButtonElement>("pk-ok").disabled = !j.repo;
    $<HTMLButtonElement>("pk-up").disabled = !cur;
    const list = $("pk-list"); list.replaceChildren();
    if (!j.dirs.length) list.append(el("li", { class: "hint" }, cur ? "Tidak ada subfolder." : "GIT_ROOTS belum diisi di server."));
    for (const d of j.dirs) {
      const b = el("button", { type: "button" }, (d.repo ? "[git] " : "") + d.name);
      b.onclick = () => go(d.path);
      list.append(el("li", null, b));
    }
  };
  return new Promise(resolve => {
    res = resolve;
    $("pk-up").onclick = () => go(parent);
    $("pk-ok").onclick = () => { dlg.close(); res(cur); };
    $("pk-cancel").onclick = () => { dlg.close(); res(""); };
    dlg.oncancel = () => res("");
    dlg.showModal(); go("");
  });
}
const figmaMode = () => document.querySelector<HTMLInputElement>("input[name=figma_mode]:checked")?.value ?? "url";
function setFigmaMode(m: string) { show("figma_url_box", m === "url"); show("figma_file_box", m === "file"); }
document.querySelectorAll("input[name=figma_mode]").forEach(r => r.addEventListener("change", () => setFigmaMode(figmaMode())));
// Kuota Figma MCP dianggap habis bila Figma pernah menolak (dicatat server). Habis: link dinonaktifkan, arahkan ke upload file.
interface Quota { exhausted: boolean; reset: string }
async function loadQuota() {
  const r = await fetch("/api/figma/quota").catch(() => null);
  if (!r || !r.ok) return;
  const q = await r.json() as Quota, box = $("figma_quota"), link = $<HTMLInputElement>("mode_url");
  const reset = new Date(q.reset + "T00:00").toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" });
  link.disabled = q.exhausted;
  box.className = "quota " + (q.exhausted ? "bad" : "ok");
  box.textContent = q.exhausted
    ? `Kuota Figma MCP habis: Figma menolak permintaan terakhir. Link Figma tidak bisa dipakai sampai sekitar ${reset}. Gunakan Upload file.`
    : "Link Figma memakai kuota Figma MCP yang terbatas per bulan di akun Figma non-premium. Bila kuota habis, peringatan muncul di sini dan Anda perlu Upload file.";
  show("figma_quota", true);
  if (q.exhausted) { $<HTMLInputElement>("mode_file").checked = true; setFigmaMode("file"); }
}
const filesOf = (id: string) => inputs(id).flatMap(i => [...(i.files ?? [])]);
const fsdFiles = () => filesOf("fsd");

function showLogin() { try { sessionStorage.removeItem("in"); } catch (e) {} show("app", false); show("login", true); }
function showApp() { try { sessionStorage.setItem("in", "1"); } catch (e) {} show("login", false); show("app", true); loadQuota(); }
let signedIn = false; try { signedIn = sessionStorage.getItem("in") === "1"; } catch (e) {}
signedIn ? showApp() : showLogin();

$("loginForm").addEventListener("submit", async ev => {
  ev.preventDefault(); showErr("loginErr", "");
  const r = await fetch("/api/login", { method: "POST", body: new URLSearchParams({ password: $<HTMLInputElement>("password").value }) }).catch(() => null);
  if (!r) return showErr("loginErr", "Server tidak terjangkau.");
  if (r.ok) { $<HTMLInputElement>("password").value = ""; return showApp(); }
  showErr("loginErr", r.status === 429 ? "Terlalu banyak percobaan salah. Coba lagi 5 menit lagi." : "Password salah.");
});

function setBusy(b: boolean) { const g = $<HTMLButtonElement>("generate"); g.disabled = b; g.textContent = b ? "Sedang diproses..." : "Generate skenario"; }
const field = (id: string) => $<HTMLInputElement>(id);

$("form").addEventListener("submit", async ev => {
  ev.preventDefault(); showErr("formErr", "");
  const files = fsdFiles();
  if (!field("dev").value || !field("test").value || !field("title").value.trim()) return showErr("formErr", "Sprint dev, sprint testing, dan judul wajib diisi.");
  if (!files.length) return showErr("formErr", "Pilih minimal satu file FSD (.docx atau .pdf).");
  for (const f of files) {
    if (!/\.(docx|pdf)$/i.test(f.name)) return showErr("formErr", "Ekstensi FSD harus .docx atau .pdf: " + f.name);
    if (f.size > 20 * 1024 * 1024) return showErr("formErr", "File FSD lebih dari 20 MB: " + f.name);
  }
  const fd = new FormData();
  for (const k of ["dev", "test", "title", "environment", "scope_note", "roles"]) fd.append(k, field(k).value.trim());
  const byLink = figmaMode() === "url", figma: File[] = byLink ? [] : filesOf("figma_file");
  for (const f of figma) if (f.size > 50 * 1024 * 1024) return showErr("formErr", "File Figma lebih dari 50 MB: " + f.name);
  for (const k of byLink ? ["swagger_url", "figma_url", "git_path"] : ["swagger_url", "git_path"]) vals(k).forEach(v => fd.append(k, v));
  figma.forEach(f => fd.append("figma_file", f));
  files.forEach(f => fd.append("fsd", f));
  setBusy(true); show("result", false); show("progress", true);
  $("stage").textContent = "Mengunggah..."; $("queue").textContent = "";
  const r = await fetch("/api/generate", { method: "POST", body: fd }).catch(() => null);
  if (!r) return fail("Server tidak terjangkau.");
  if (r.status === 401) { fail(""); return showLogin(); }
  if (!r.ok) {
    const m: Record<number, string> = { 413: "File lebih dari 20 MB.", 422: "Isian belum lengkap atau jenis file salah." };
    const d = r.status === 422 ? (await r.json().catch(() => null) as { detail?: unknown } | null)?.detail : null;
    return fail(typeof d === "string" ? d : m[r.status] || "Gagal memulai job (HTTP " + r.status + ").");
  }
  const { job_id } = await r.json() as { job_id: string };
  startClock(); poll(job_id);
});

// Waktu berjalan terus bertambah agar tahap yang lama tidak terlihat macet.
let tick: number | undefined;
function startClock() {
  const t0 = Date.now(); clearInterval(tick);
  const draw = () => { const s = Math.floor((Date.now() - t0) / 1000); $("elapsed").textContent = `Berjalan ${Math.floor(s / 60)} menit ${s % 60} detik`; };
  draw(); tick = window.setInterval(draw, 1000);
}
function fail(msg: string) { loadQuota(); clearInterval(tick); clearTimeout(timer); setBusy(false); show("progress", false); showErr("formErr", msg); }

function poll(id: string) {
  clearTimeout(timer);
  fetch("/api/jobs/" + encodeURIComponent(id)).then(async r => {
    if (r.status === 401) { fail(""); return showLogin(); }
    if (!r.ok) return fail("Status job tidak bisa dibaca (HTTP " + r.status + ").");
    const j = await r.json() as JobStatus;
    if (j.state === "done") { clearInterval(tick); setBusy(false); show("progress", false); loadQuota(); return render(id, j.preview); }
    if (j.state === "failed") return fail("Job gagal: " + (j.error || "alasan tidak diketahui") + ". Hubungi admin bila berulang.");
    $("stage").textContent = j.stage || (j.state === "queued" ? "Menunggu antrian" : "Memproses");
    $("queue").textContent = j.state === "queued" && (j.queue_pos ?? 0) > 0 ? "Antrian: " + j.queue_pos + " job di depan Anda" : "";
    timer = window.setTimeout(() => poll(id), 3000);
  }).catch(() => { timer = window.setTimeout(() => poll(id), 3000); });
}

function render(id: string, p?: Preview) {
  preview = p || {}; current = "statistic";
  $<HTMLAnchorElement>("download").href = "/api/jobs/" + encodeURIComponent(id) + "/download";
  drawWarn(); show("result", true); drawTabs(); drawPanel();
  $("result").scrollIntoView({ behavior: "smooth" });
}
function drawWarn() {
  const w = $("warn"), items = (preview.peringatan || []).filter((x): x is string => typeof x === "string");
  w.replaceChildren(); show("warn", items.length > 0);
  if (items.length) w.append(el("b", null, "Peringatan mutu"), el("ul", null, ...items.map(x => el("li", null, x))));
}
function drawTabs() {
  const t = $("tabs"); t.replaceChildren();
  for (const [k, name] of TABS) {
    const n = k === "statistic" ? "" : " (" + countOf(k) + ")";
    const b = el("button", { type: "button", role: "tab", "aria-selected": String(k === current) }, name + n);
    b.onclick = () => { current = k; drawTabs(); drawPanel(); };
    t.append(b);
  }
}
const countOf = (k: Tab) => k === "skenario" ? (preview.skenario || []).reduce((a, s) => a + (s.cases || []).length, 0) : (preview[k as "analisa" | "bugs"] || []).length;
const empty = (msg: string) => el("p", { class: "hint" }, msg);

const panels: Record<Tab, () => HTMLElement> = { statistic, skenario, analisa, bugs };
function drawPanel() { $("panel").replaceChildren(panels[current]()); }

function statistic() {
  const s = preview.statistic || {};
  const box = (title: string, obj?: Counts) => el("div", { class: "stat" }, el("h3", null, title),
    ...Object.entries(obj || {}).map(([k, v]) => el("div", { class: "row" }, el("span", null, k ?? "-"), el("b", null, v))));
  return el("div", { class: "stats" },
    el("div", { class: "stat" }, el("h3", null, "Total test case"), el("div", { class: "n" }, s.total ?? 0)),
    box("Tipe", s.type), box("Prioritas", s.priority), box("Platform", s.platform));
}
function skenario() {
  const secs = preview.skenario || [];
  if (!secs.length) return empty("Tidak ada skenario.");
  const out = el("div");
  for (const s of secs) {
    out.append(el("div", { class: "sec" }, s.title));
    const rows = (s.cases || []).map((c, i) => {
      const warn = /perlu verifikasi/i.test((c.notes || "") + (c.expected || []).join(" "));
      return el("tr", null,
        el("td", null, i + 1), el("td", null, c.type), el("td", null, c.priority),
        el("td", null, c.desc, warn ? el("div", null, el("span", { class: "tag warn" }, "Perlu verifikasi")) : null),
        el("td", null, el("ol", null, (c.steps || []).map(x => el("li", null, x)))),
        el("td", null, el("ol", null, (c.expected || []).map(x => el("li", null, x)))),
        el("td", null, c.platform), el("td", null, c.notes));
    });
    out.append(el("div", { class: "tw" }, el("table", null,
      el("thead", null, el("tr", null, ["No", "Tipe", "Prio", "Deskripsi", "Langkah", "Hasil diharapkan", "Platform", "Notes"].map(h => el("th", null, h)))),
      el("tbody", null, rows))));
  }
  return out;
}
function analisa() {
  const a = preview.analisa || [];
  if (!a.length) return empty("Tidak ada temuan analisa.");
  return el("div", null, a.map(x => el("div", { class: "acard" },
    el("div", null, el("span", { class: "tag" }, x.category), " ", el("span", { class: "k" }, [x.ref, x.source, x.confidence && "keyakinan " + x.confidence].filter(Boolean).join(" | "))),
    el("p", null, x.finding),
    x.impact ? el("p", null, el("span", { class: "k" }, "Dampak: "), x.impact) : null,
    x.question ? el("p", null, el("span", { class: "k" }, "Pertanyaan: "), x.question) : null,
    x.cases ? el("p", { class: "k" }, "Case terkait: " + x.cases) : null)));
}
function bugs() {
  const b = preview.bugs || [];
  if (!b.length) return empty("Belum ada bug tercatat. Daftar ini diisi tester saat pengujian.");
  const keys = Object.keys(b[0]);
  return el("div", { class: "tw" }, el("table", null,
    el("thead", null, el("tr", null, keys.map(k => el("th", null, k)))),
    el("tbody", null, b.map(r => el("tr", null, keys.map(k => el("td", null, r[k])))))));
}
