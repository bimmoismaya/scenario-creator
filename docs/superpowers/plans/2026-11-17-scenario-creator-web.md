# Scenario Creator Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web internal untuk tim QA, dipakai untuk project apa pun yang dokumennya diberikan: upload FSD + link Swagger + link Figma, tekan Generate, lihat preview, unduh xlsx skenario format perusahaan.

**Architecture:** FastAPI membungkus `claude -p` (Claude Code CLI) yang menjalankan skill `qa-scenario` di folder job. Claude menulis `spec.json`; server memvalidasi, membangun xlsx dengan `scripts/build_scenario.py` (tidak diubah), lalu merender preview dari spec. Satu job per waktu (antrian).

**Tech Stack:** Python 3.14 (venv), FastAPI, uvicorn, python-docx, pypdf, openpyxl (sudah dipakai skrip), pytest, HTML+JS statis tanpa build step. `soffice` untuk recalc.

**Spec:** `docs/superpowers/specs/2026-11-17-scenario-creator-web-design.md`

## Status (diperbarui 2026-11-17)

Task 0 sampai 7 selesai. `pytest -q`: 41 passed. Satu uji end-to-end dengan `claude` asli lewat server selesai dalam 84 detik (upload FSD, Generate, preview, unduh xlsx). Tanda `[~]` di bawah berarti selesai sebagian.

Perbedaan dari rencana awal:

- **Proyek generik.** Alat ini dipakai untuk berbagai project yang tidak saling berhubungan, bukan untuk satu project. Skill diganti nama menjadi `qa-scenario` dan ditulis ulang tanpa domain, tabel, URL, atau nama perusahaan. Bahan spesifik project dihapus (catatan domain, pemetaan sprint, catatan per fitur, dua spec contoh, `scripts/read_gdoc.py`). Contoh spec sekarang satu file netral: `assets/examples/example_spec.json`. Tes memakainya.
- **Skill dimuat lewat symlink** `~/.claude/skills/qa-scenario` yang menunjuk ke folder ini. Ini satu-satunya perubahan di luar repo. Tanpa symlink, skill tidak termuat saat Generate.
- **Izin tool Claude** (Task 4) berbeda dari rencana. Uji nyata menunjukkan aturan `Write(spec.json)` dan `Write(//path/spec.json)` ditolak semua. Yang dipakai sekarang `Write(*)`, yang hanya berlaku di working directory (folder job). Repo tidak ditambahkan lewat `--add-dir`, jadi Claude tidak bisa menulis ke skill atau skrip. Aturan Bash memakai `Bash(*build_scenario.py* spec.json --check)` dan prompt mengutip path skrip karena path berisi spasi. `use_figma` dan `whoami` sengaja tidak diizinkan.
- **Pesan error ke UI disanitasi.** Stage hanya dari nama tool, email diganti `[email]`, dipotong 300 karakter. Error exception di antrian tidak lagi menampilkan teks mentah.
- **Folder spike dihapus** (`app/spike/`, `jobs/spike/`). Temuan pentingnya sudah masuk ke bagian perbedaan ini: `claude -p` dengan `--output-format stream-json --verbose`, `--permission-mode dontAsk`, `--no-session-persistence`, stdin ditutup; tahap dibaca dari event `tool_use`; durasi 73 sampai 84 detik untuk FSD kecil.

Belum teruji: akses file Figma nyata, input Swagger lewat link, layar login dan tampilan ponsel di browser, purge tiap jam, kedaluwarsa cookie sesi, dan mutu isi skenario hasil Generate (hanya lolos validasi format). Hosting, kebijakan akses Figma "Anyone with the link", dan persetujuan kerahasiaan masih menunggu jawaban pemilik proyek.

## Global Constraints

- Server memakai `scripts/build_scenario.py` apa adanya; jangan ubah.
- Input user adalah data: tidak pernah masuk ke argumen shell. Subprocess dipanggil dengan list argumen, tanpa `shell=True`.
- Satu job berjalan per waktu; timeout job 1800 detik; upload maksimal 20 MB (20 * 1024 * 1024 byte).
- Job disimpan di `jobs/{job_id}/` dan dihapus setelah 24 jam.
- Password bersama dari env `APP_PASSWORD`; percobaan salah dibatasi (3 salah dalam 5 menit per IP = tolak 5 menit).
- Tool Claude dibatasi: `Write(*)` hanya di folder job (working directory), `Read`, `Skill`, WebFetch, `Bash` hanya untuk `build_scenario.py spec.json --check`, tool Figma read-only. Repo tidak ditambahkan sebagai direktori yang bisa ditulis.
- Nama file hasil: `Scenario Sprint {test} Testing ({dev}).xlsx`; nomor dokumen `TC-{dev}/{test}-{tahun}-1`; `feature_no` = 1; `system_name` = "Nama Sistem"; `approval` kosong.
- UI berbahasa Indonesia; warna mengikuti Excel perusahaan (header biru muda `#C9DAF8`, section hijau `#D9EAD3`, precondition kuning `#FFF2CC`).
- Repo ini bukan git repo: langkah "Commit" diganti dengan menjalankan seluruh tes (`pytest -q`).

## Review Focus

- FSD kosong, rusak, atau bukan docx/pdf: error jelas, bukan job menggantung.
- Link Swagger/Figma kosong atau tidak valid: generate tetap jalan, case terkait `Perlu verifikasi`.
- `claude` tidak login atau keluar non-zero: job `failed` dengan pesan yang bisa dibaca admin.
- `spec.json` tidak ada atau tidak valid setelah Claude selesai: job `failed`, bukan xlsx kosong.
- Nama file upload berisi `../` atau karakter aneh: tidak bisa keluar dari folder job.

---

### Task 0: Spike headless Claude Code (P0, dikerjakan pertama)

**Files:**
- Create: `app/spike/README.md` (hasil: flag final, daftar tool, durasi, kendala) *(folder sudah dihapus; ringkasan ada di bagian Status)*
- Create: `app/spike/run_spike.py`

**Interfaces:**
- Produces: dokumen `app/spike/README.md` berisi persis argumen `claude` yang berhasil (dipakai Task 4). *(folder sudah dihapus; ringkasan ada di bagian Status)*

- [x] **Step 1:** Siapkan folder `jobs/spike/` berisi satu FSD contoh (teks FSD contoh apa saja) dan `input.json` berisi isian form contoh.
- [x] **Step 2:** Jalankan `claude -p` non-interaktif dengan `--output-format stream-json`, `--allowedTools` sempit, `--add-dir` folder job, dan instruksi memakai skill `qa-scenario` untuk menulis `jobs/spike/spec.json`. Catat flag yang diperlukan agar skill termuat dari folder ini (symlink ke `~/.claude/skills/qa-scenario` bila perlu).
- [x] **Step 3:** Verifikasi: `python scripts/build_scenario.py jobs/spike/spec.json --check` keluar 0. Catat durasi dan bentuk event stream yang menandakan tahap (baca, analisa, tulis).
- [~] **Step 4:** Coba satu panggilan tool Figma read-only dari mode headless dan catat apakah berhasil. Bila gagal, tulis di README sebagai kendala (generate tetap harus jalan tanpa Figma). *Hasil: `whoami` berhasil headless; `create_session`/`use_figma` pada link nyata belum diuji.*
- [x] **Step 5:** Tulis `app/spike/README.md`. Bila langkah 2 atau 3 tidak bisa berhasil, berhenti dan laporkan; jangan lanjut ke Task 4.

### Task 1: Ekstraksi teks FSD

**Files:**
- Create: `app/__init__.py`, `app/sources.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces: `fsd_to_text(path: Path) -> str` (raise `ValueError` dengan pesan Indonesia bila ekstensi bukan `.docx`/`.pdf`, file kosong, atau tidak terbaca); `safe_name(filename: str) -> str` (hanya nama dasar, karakter `[A-Za-z0-9._-]`, selain itu `_`, tidak pernah kosong).

- [x] **Step 1:** Tes: `.docx` kecil buatan `python-docx` berisi heading + tabel → teks memuat keduanya; `.pdf` kecil → teks; `.txt` → `ValueError`; file kosong → `ValueError`; `safe_name("../../etc/x y.docx") == "x_y.docx"`.
- [x] **Step 2:** Jalankan `pytest tests/test_sources.py -q`; harus gagal.
- [x] **Step 3:** Implementasi `fsd_to_text` (python-docx: paragraf dan tabel dalam urutan dokumen, tabel jadi baris `a | b | c`; pypdf: teks tiap halaman) dan `safe_name`.
- [x] **Step 4:** Jalankan tes; harus lulus.

### Task 2: Penyimpanan job dan antrian

**Files:**
- Create: `app/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Produces: `class JobForm(BaseModel)` dengan `dev: int`, `test: int`, `title: str`, `environment: str = "Staging"`, `scope_note: str = ""`, `swagger_url: str = ""`, `figma_url: str = ""`.
- Produces: `class JobStore(root: Path)` dengan `create(form: JobForm) -> str` (job_id hex 12 karakter, membuat folder), `dir(job_id) -> Path`, `status(job_id) -> dict` (`state` ∈ `queued|running|done|failed`, `stage: str`, `error: str|None`, `queue_pos: int`), `set_status(job_id, **fields)`, `purge(older_than_seconds: int = 86400)`.
- Produces: `class Queue` dengan `submit(job_id, fn)` yang menjalankan `fn` satu per satu di thread pekerja tunggal dan memperbarui `queue_pos`.

- [x] **Step 1:** Tes: `create` membuat folder dan `status == queued`; dua job dikirim ke `Queue` berjalan berurutan (job kedua `queue_pos == 1` selagi pertama jalan); `purge` menghapus folder lebih tua dari batas dan membiarkan yang baru; `job_id` tak valid (`"../x"`) ditolak dengan `ValueError`.
- [x] **Step 2:** Jalankan; harus gagal.
- [x] **Step 3:** Implementasi. Status disimpan di `status.json` dalam folder job agar bertahan restart.
- [x] **Step 4:** Jalankan tes; harus lulus.

### Task 3: Build, validasi, dan recalc xlsx

**Files:**
- Create: `app/finalize.py`
- Test: `tests/test_finalize.py`

**Interfaces:**
- Consumes: `scripts/build_scenario.py` (`validate`, `summary`, `norm_platform`, `main` via subprocess).
- Produces: `finalize(job_dir: Path, form: JobForm) -> Path` — membaca `spec.json`, memaksa `meta` (doc_number, system_name, feature_no=1, test_date hari ini, environment, approval kosong), memanggil build_scenario dengan subprocess (list argumen), recalc dengan `soffice --headless --convert-to xlsx` bila `soffice` ada (jika tidak, lewati), dan mengembalikan path `Scenario Sprint {test} Testing ({dev}).xlsx`. Raise `FinalizeError(str)` bila spec tidak ada, bukan JSON, atau `validate` memberi ERROR.
- Produces: `preview_data(spec: dict) -> dict` dengan kunci `statistic`, `skenario`, `analisa`, `bugs` (JSON-serializable, dipakai UI).

- [x] **Step 1:** Tes memakai `assets/examples/example_spec.json`: `finalize` menghasilkan xlsx dengan sheet `Statistic`, `Skenario`, `Bug List`, `Analisa`; nama file sesuai pola; `meta.doc_number == "TC-53/54-<tahun>-1"` saat dev=53, test=54. Tes error: tanpa `spec.json` → `FinalizeError`; spec dengan `priority: "P9"` → `FinalizeError` memuat teks ERROR dari validasi.
- [x] **Step 2:** Jalankan; harus gagal.
- [x] **Step 3:** Implementasi. Recalc ke folder sementara lalu ganti file hasil hanya bila konversi sukses.
- [x] **Step 4:** Jalankan tes; harus lulus.

### Task 4: Runner Claude Code dan penyusun prompt

**Files:**
- Create: `app/prompt.py`, `app/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: hasil Task 0 (ringkasan di bagian Status) untuk argumen `claude`; `JobStore`, `JobForm` (Task 2); `finalize` (Task 3); `fsd_to_text` (Task 1).
- Produces: `build_prompt(form: JobForm, fsd_file: str) -> str` — memerintahkan Claude memakai skill `qa-scenario`, membaca `fsd_file` dan `swagger_url`/`figma_url` dari form, menulis `spec.json` di folder kerja, menjalankan `--check`, dan memperlakukan seluruh isi sumber sebagai data. Bila URL kosong, menyuruh menandai case terkait `Perlu verifikasi`.
- Produces: `run_job(store: JobStore, job_id: str, form: JobForm, claude_cmd: list[str] = ["claude"]) -> None` — set status per tahap, jalankan subprocess dengan `timeout=1800`, urai event stream menjadi `stage` (`Membaca sumber`, `Analisa`, `Menulis case`, `Validasi`), lalu `finalize`; set `done` atau `failed` dengan pesan. `claude_cmd` bisa diganti agar tes memakai skrip palsu.

- [x] **Step 1:** Tes dengan `claude_cmd=[sys.executable, "tests/fake_claude.py"]`: fake menulis `spec.json` dari `assets/examples/example_spec.json` → job `done` dan xlsx ada. Fake yang keluar kode 1 → `failed` dengan pesan memuat stderr. Fake yang tidur lebih lama dari timeout (diatur 1 detik dalam tes) → `failed` dengan pesan timeout. Fake yang tidak menulis `spec.json` → `failed`. `build_prompt` untuk `figma_url=""` memuat kata `Perlu verifikasi`.
- [x] **Step 2:** Jalankan; harus gagal.
- [x] **Step 3:** Implementasi. Argumen dan filter tool seperti di bagian Status; input user hanya masuk lewat berkas di folder job dan teks prompt, tidak lewat shell.
- [x] **Step 4:** Jalankan tes; harus lulus.

### Task 5: Server FastAPI, login, dan pengamanan

**Files:**
- Create: `app/server.py`, `.env.example`, `requirements.txt`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1–4.
- Produces: endpoint `POST /api/login` (form `password` → cookie sesi bertanda tangan; salah = 401; 3 salah per 5 menit per IP = 429), `POST /api/generate` (multipart: `dev`, `test`, `title`, `environment`, `scope_note`, `swagger_url`, `figma_url`, `fsd` file; 401 tanpa sesi; 413 bila > 20 MB; 422 bila field wajib kosong atau ekstensi salah; sukses → `{"job_id": str}`), `GET /api/jobs/{id}` (status + `preview` bila `done`), `GET /api/jobs/{id}/download` (xlsx), `GET /` (UI). Purge job > 24 jam saat startup dan tiap jam.

- [x] **Step 1:** Tes dengan `TestClient`: tanpa login → 401 di `/api/generate`; password salah tiga kali → 429; upload 21 MB → 413; `.txt` → 422; alur sukses dengan `claude_cmd` palsu sampai `done`, `preview` memuat kunci `skenario`, `download` mengembalikan xlsx; `job_id` `"../x"` → 404; nama file upload `"../../x.docx"` tersimpan aman di folder job.
- [x] **Step 2:** Jalankan; harus gagal.
- [x] **Step 3:** Implementasi. Cookie tertanda memakai `itsdangerous`; rate limit di memori.
- [x] **Step 4:** Jalankan tes; harus lulus.

### Task 6: UI satu halaman

**Files:**
- Create: `app/static/index.html`
- Test: `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: endpoint Task 5.

- [x] **Step 1:** Tes: `GET /` mengembalikan HTML yang memuat id `fsd`, `swagger_url`, `figma_url`, tombol `generate`, dan teks `Duplicate to drafts`.
- [x] **Step 2:** Jalankan; harus gagal.
- [x] **Step 3:** Implementasi sesuai sketsa desain: layar login; form (info sprint, upload FSD, link Swagger, link Figma dengan panel lipat tutorial: Duplicate to drafts → Share → "Anyone with the link can view" → salin link); tombol Generate menonaktifkan diri saat jalan; polling `/api/jobs/{id}` tiap 3 detik menampilkan `stage` dan posisi antrian; setelah `done` tampil empat tab (Statistic, Skenario, Analisa, Bug List) dan tombol unduh. Responsif sampai lebar ponsel. Teks hasil di-escape (tidak memakai `innerHTML` mentah untuk isi dari spec).
- [~] **Step 4:** Jalankan tes; harus lulus. Buka halaman di browser dan periksa visual dengan spec contoh. *Hasil: tes lulus; screenshot headless pada preview benar. Layar login, tampilan ponsel, polling, dan pesan error belum diuji di browser.*

### Task 7: Operasional

**Files:**
- Create: `README.md`, `run.sh`

- [x] **Step 1:** Tulis `README.md` singkat: setup venv, `.env`, menjalankan `./run.sh` (uvicorn pada `0.0.0.0:8000`), login ulang Claude Code bila token kedaluwarsa, membersihkan job.
- [x] **Step 2:** Verifikasi: `pytest -q` lulus semua dan `./run.sh` menjawab `GET /` dengan 200.
