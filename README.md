# Scenario Creator

Web internal untuk QA: upload FSD, tempel link Swagger dan Figma, tekan Generate, lihat preview, lalu unduh
xlsx skenario testing. Isinya dibuat oleh Claude Code lewat skill `qa-scenario` (folder ini sendiri).

Alat ini tidak terikat satu project. Setiap Generate berdiri sendiri dan hanya membaca dokumen yang diberikan.

## Yang dibutuhkan

| Kebutuhan | Keterangan |
|---|---|
| Linux atau macOS | Diuji di Linux. Windows: pakai WSL. |
| Python 3.11 atau lebih baru | Diuji di 3.14. Cek dengan `python3 --version`. |
| Claude Code CLI | Harus sudah login. Cek dengan `claude --version`. |
| LibreOffice (`soffice`) | Opsional. Dipakai menghitung ulang rumus di sheet Statistic. Tanpa ini, Excel tetap menghitung saat file dibuka. |
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

## Menjalankan

```
./run.sh
```

Buka `http://localhost:8000` dan login dengan `APP_PASSWORD`. Server mendengarkan di semua antarmuka
(`0.0.0.0:8000`), jadi QA lain di jaringan yang sama membuka `http://<ip-mesin>:8000`. Untuk berhenti: Ctrl+C.

Dokumen besar bisa memakan belasan menit, terutama dengan Opus.

## Memakai

1. Isi info sprint (dev, testing, nama dokumen/fitur) dan upload FSD (`.docx` atau `.pdf`, maksimal 20 MB).
2. Opsional: link Swagger/OpenAPI, link Figma, daftar role user, dan batasan scope. Kosongkan batasan scope untuk
   mengerjakan seluruh dokumen.
3. Tekan Generate, tunggu sampai selesai, periksa preview dan panel peringatan mutu, lalu unduh xlsx.

Figma sering tidak bisa dibaca AI bila file privat. Gunakan **Duplicate to drafts**, ubah akses duplikat menjadi
"Anyone with the link can view", lalu tempel link duplikat itu. Panduan yang sama ada di halaman web.

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
- **Hasil sementara:** disimpan di `JOBS_DIR` dan dihapus otomatis setelah 24 jam (saat start dan tiap jam).
  Bersihkan manual dengan `rm -rf jobs/*`.
- **Privasi:** isi FSD, Swagger, dan Figma diproses oleh Claude (Anthropic) lewat akun yang login di mesin server.
- **Tes:** `.venv/bin/python -m pytest -q`.

## Struktur

- `app/`: server FastAPI, runner `claude`, dan UI satu halaman (`app/static/index.html`).
- `scripts/build_scenario.py`: spec JSON menjadi xlsx dan pemeriksa mutu (`--check`).
- `SKILL.md`, `references/`, `assets/`: skill `qa-scenario` yang dibaca Claude saat Generate.
- `docs/`: desain dan rencana pengerjaan.
