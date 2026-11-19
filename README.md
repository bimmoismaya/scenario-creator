# Scenario Creator

Web internal untuk QA: upload FSD, tempel link Swagger dan Figma, pilih folder repo Git di server, tekan Generate,
lihat preview, lalu unduh xlsx skenario testing. Isinya dibuat oleh Claude Code lewat skill `qa-scenario` (folder ini sendiri).

Alat ini tidak terikat satu project. Setiap Generate berdiri sendiri dan hanya membaca dokumen yang diberikan.

## Yang dibutuhkan

| Kebutuhan | Keterangan |
|---|---|
| Linux, macOS, atau Windows 10/11 | Diuji di Linux. Windows asli didukung lewat `run.bat` (lihat bagian Windows), belum diuji langsung. WSL juga bisa dan memakai langkah Linux. |
| Python 3.11 atau lebih baru | Diuji di 3.14. Cek dengan `python3 --version`. |
| Claude Code CLI | Harus sudah login. Cek dengan `claude --version`. Di Windows pakai versi native (`claude.exe`), bukan versi npm (`claude.cmd`), dan pasang Git for Windows. |
| LibreOffice (`soffice`) | Opsional. Dipakai menghitung ulang rumus di sheet Statistic. Tanpa ini, Excel tetap menghitung saat file dibuka. Isi `RECALC=0` di `.env` untuk melewatinya walau terpasang (job lebih cepat). |
| Konektor Figma di akun Claude | Opsional. Tanpa ini, Generate tetap jalan dan case yang butuh desain ditandai `Perlu verifikasi`. |

Web ini menjalankan `claude` memakai login Claude Code di mesin yang menjalankannya. Pemakaian dihitung ke akun
itu, dan hanya satu Generate berjalan per waktu.

## Memasang

1. **Ambil kode**
   ```
   git clone <url-repo> scenario-creator
   cd scenario-creator
   ```

2. **Pasang dependensi Python**
   ```
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

> **Windows:** gunakan perintah di bagian [Memasang di Windows](#memasang-di-windows) untuk langkah 2, 3, dan 5, dan
> `run.bat` untuk menjalankan. Selebihnya sama.

3. **Pasang skill ke Claude Code.** Tanpa langkah ini, Claude tidak menemukan skill `qa-scenario` saat Generate.
   ```
   mkdir -p ~/.claude/skills
   ln -s "$(pwd)" ~/.claude/skills/qa-scenario
   ```
   Cek: `ls ~/.claude/skills/qa-scenario/SKILL.md` harus menampilkan file.

4. **Login Claude Code** (sekali saja). Jalankan `claude`, ikuti login, lalu keluar. Kalau memakai Figma,
   sambungkan konektor Figma di pengaturan akun Claude Anda.

5. **Buat file konfigurasi**
   ```
   cp .env.example .env
   ```
   Buka `.env` dan isi:
   - `APP_PASSWORD`: password login web. Anda yang menentukan, lalu dibagikan ke tim QA.
   - `APP_SECRET`: string acak untuk menandatangani sesi. Buat dengan
     `.venv/bin/python -c "import secrets; print(secrets.token_hex(32))"`.
   - `CLAUDE_MODEL`: model yang dipakai Generate. Default `opus` (lebih rinci, lebih lama). Isi `sonnet` untuk
     lebih cepat dan hemat.
   - `JOBS_DIR`: folder hasil sementara. Default `jobs`.
   - `GIT_ROOTS`: folder induk repo Git di mesin server yang boleh dipilih di form (pisahkan dengan `:`). Repo dibaca
     langsung dari disk, tanpa upload, dan hanya baca. Kosong: sumber Git ditolak.

   Jangan commit atau bagikan `.env`. Server menolak start kalau `APP_PASSWORD` kosong.

6. **Cek terpasang benar**
   ```
   .venv/bin/python -m pytest -q
   ```
   Semua tes harus lulus.

## Memasang di Windows

Jalankan di Command Prompt dari folder proyek. Prasyarat: Python 3.11+ (centang "Add to PATH" saat memasang),
Git for Windows (dipakai Claude Code untuk menjalankan perintah), dan Claude Code versi native yang sudah login.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
mkdir "%USERPROFILE%\.claude\skills"
mklink /J "%USERPROFILE%\.claude\skills\qa-scenario" "%CD%"
copy .env.example .env
```

- `mklink /J` membuat junction (tidak butuh hak admin). Cek: `dir "%USERPROFILE%\.claude\skills\qa-scenario\SKILL.md"`.
- Isi `.env` dengan Notepad. `APP_SECRET`: `.venv\Scripts\python -c "import secrets; print(secrets.token_hex(32))"`.
- `GIT_ROOTS` di Windows dipisah dengan `;` dan memakai path lengkap, mis. `GIT_ROOTS=C:\Users\Anda\git;D:\repo`.
- Tes: `.venv\Scripts\python -m pytest -q`.
- Jalankan dengan `run.bat` (atau `.venv\Scripts\python -X utf8 run.py`). Boleh juga `python run.py` di Linux dan macOS.
- Jika Windows Firewall bertanya saat server pertama kali jalan, izinkan akses jaringan privat agar QA lain bisa membuka
  `http://<ip-mesin>:8000`.
- Windows belum diuji langsung oleh pembuat; bila ada kendala, laporkan pesan error-nya.

## Menjalankan

```
./run.sh
```

Di Windows: `run.bat`. `run.py` bisa dipakai di semua sistem.

Buka `http://localhost:8000` dan login dengan `APP_PASSWORD`. Server mendengarkan di semua antarmuka
(`0.0.0.0:8000`), jadi QA lain di jaringan yang sama membuka `http://<ip-mesin>:8000`. Untuk berhenti: Ctrl+C.

Dokumen besar bisa memakan belasan menit, terutama dengan Opus.

## Memakai (tutorial)

1. **Login.** Buka web, masukkan `APP_PASSWORD`. Tiga kali salah mengunci login 5 menit.
2. **Info sprint (wajib).** Isi sprint dev, sprint testing, dan nama dokumen/fitur (hanya label). Environment
   default `Staging`. Role user dan batasan scope opsional. Kosongkan batasan scope untuk mengerjakan seluruh dokumen.
3. **Sumber.** Hanya FSD yang wajib. Tiap sumber boleh sampai 10 isian (tombol **+ Tambah**).
   - **FSD:** `.docx` atau `.pdf`, maksimal 20 MB per file. Lebih dari satu FSD dianggap satu fitur.
   - **Swagger / API contract:** tempel link. Hanya host dari link ini yang boleh dibuka Claude.
   - **Figma:** pilih **Link Figma** (memakai kuota Figma MCP) atau **Upload file** (gambar apa pun, PDF, ZIP, atau RAR; tidak memakai kuota). Lihat panduan Figma di bawah.
   - **Folder Git lokal:** klik **Pilih folder**, telusuri daftar folder di server, masuk ke repo (ditandai `[git]`),
     lalu **Pilih folder ini**. Tombol hanya aktif di folder repo (berisi `.git`). Tidak ada file yang diunggah:
     Claude membaca repo langsung dari disk, hanya baca. File rahasia (`.env*`, `*.pem`, `*.key`, `id_rsa*`) tidak
     bisa dibaca. Daftar hanya menampilkan folder di bawah `GIT_ROOTS`.
   - Tanpa Swagger, Figma, atau folder Git, Generate tetap jalan; case terkait ditandai `Perlu verifikasi`.
4. **Generate.** Tekan **Generate skenario** dan biarkan halaman terbuka. Kartu progres menampilkan tahap
   (Membaca FSD, Menelusuri kode repo, Membaca Swagger/Figma, Menulis case, Memvalidasi spec), hitungan langkah,
   dan waktu berjalan. Dokumen besar dengan Opus bisa belasan menit; hanya satu job berjalan per waktu, job lain antre.
5. **Hasil.** Periksa panel peringatan mutu dan tab **Statistic**, **Skenario**, **Analisa**, **Bug List**.
   Tekan **Unduh Excel** untuk mengambil xlsx.

**Kuota Figma MCP.** Akun Figma non-premium hanya punya kuota terbatas per bulan (mis. 20 panggilan). Aplikasi tidak
menghitung sisanya. Bila Figma menolak panggilan dengan error kuota/limit, kuota dianggap habis: banner merah muncul,
Link Figma dinonaktifkan, dan Generate dengan link ditolak sampai awal bulan depan. Pakai Upload file. Error biasa
(file privat, link salah) tidak dianggap kuota habis. Admin bisa memulihkan lebih awal dengan menghapus
`jobs/figma_quota.json`.

**Upload file Figma.** Maks 100 gambar/halaman PDF per Generate, 50 MB per file. File RAR butuh `unrar`, `7z`, atau
`bsdtar` terpasang di server (ZIP tidak butuh apa-apa). ZIP/RAR yang diberi password ditolak.

**Figma.** Figma sering tidak bisa dibaca AI bila file privat. Gunakan **Duplicate to drafts**, ubah akses duplikat
menjadi "Anyone with the link can view", lalu tempel link duplikat itu. Panduan yang sama ada di halaman web.

**Pesan yang sering muncul**

| Pesan | Artinya |
|---|---|
| Sprint dev, sprint testing, dan judul wajib diisi | Isian info sprint belum lengkap |
| Pilih minimal satu file FSD | FSD belum dipilih |
| Pilih folder repo Git (berisi .git) | Folder yang dipilih bukan repo, atau folder induknya |
| Folder Git di luar GIT_ROOTS | Folder tidak di bawah `GIT_ROOTS` di server |
| Repo ini berisi folder hasil (JOBS_DIR) | Folder `jobs` ada di dalam repo yang dipilih (mis. memilih repo Scenario Creator itu sendiri). Pilih repo lain atau pindahkan `JOBS_DIR` ke luar repo |
| GIT_ROOTS belum diisi di server | Admin belum mengisi `GIT_ROOTS` di `.env`; sumber Git ditolak |

**Repo harus ada di server.** Yang dipilih adalah folder di mesin server, bukan di laptop Anda. QA yang membuka web
dari laptop lain perlu repo itu di-`git clone` ke bawah `GIT_ROOTS` di server (minta admin).

## Memperbarui

```
git pull
.venv/bin/pip install -r requirements.txt
```

Restart `./run.sh`. Symlink skill tidak perlu dibuat ulang karena menunjuk ke folder yang sama.

## Operasional

- **Job gagal dengan pesan login:** token Claude Code kedaluwarsa. Jalankan `claude` di mesin server, login
  ulang, lalu Generate lagi.
- **Job gagal karena skill tidak ditemukan:** ulangi langkah 3 di bagian Memasang.
- **Windows, job gagal dengan pesan "versi npm (.cmd)":** pasang Claude Code versi native (`claude.exe`), pastikan
  `where claude` menunjuk ke `.exe`, lalu restart `run.bat`.
- **Hasil sementara:** disimpan di `JOBS_DIR` dan dihapus otomatis setelah 24 jam (saat start dan tiap jam).
  Bersihkan manual dengan `rm -rf jobs/*`.
- **Privasi:** isi FSD, Swagger, dan Figma diproses oleh Claude (Anthropic) lewat akun yang login di mesin server.
- **Tes:** `.venv/bin/python -m pytest -q`.
- **Keamanan Claude saat Generate:** hanya boleh menulis di folder job; repo hanya dibaca; `WebFetch` hanya ke host
  Swagger yang diisi; `.env` dan kunci di repo tidak bisa dibaca. Symlink di dalam repo yang menunjuk ke luar
  `GIT_ROOTS` tidak diblokir, jadi pilih `GIT_ROOTS` yang hanya berisi repo tepercaya.
- **Mengubah UI:** edit `src/ui/main.ts`, lalu `npm install` (sekali) dan `npm run build` untuk memperbarui
  `app/static/main.js`. Commit keduanya.

## Struktur

- `run.sh`, `run.bat`, `run.py`: menjalankan server (Linux/macOS, Windows, dan semua sistem).
- `app/`: server FastAPI, runner `claude`, dan UI satu halaman (`app/static/index.html`).
- `scripts/build_scenario.py`: spec JSON menjadi xlsx dan pemeriksa mutu (`--check`).
- `SKILL.md`, `references/`, `assets/`: skill `qa-scenario` yang dibaca Claude saat Generate.
- `docs/`: desain dan rencana pengerjaan.
