# Scenario Creator Web: desain

Tanggal: 2026-11-17. Status: menunggu persetujuan. Revisi: pendekatan diganti dari A (Claude API) ke B (Claude Code CLI) atas permintaan user.

## Maksud

Tim QA saat ini membuat file skenario sprint lewat chat dengan skill `qa-scenario`
(`SKILL.md`). Hasilnya bagus tetapi hanya bisa dijalankan oleh orang yang memakai Claude Code dengan
skill itu. Web ini membuat proses yang sama bisa dipakai seluruh tim QA lewat browser: isi form,
tekan Generate, lihat preview, unduh xlsx format perusahaan.

Nilai utama tetap analisa. Skenario yang hanya menyalin FSD tidak menangkap bug di celah antara FSD,
API Contract, dan Figma, jadi hasil harus memuat sheet Analisa berisi konflik antar sumber.

## Tujuan

- Satu halaman dengan form input, tombol Generate, progres, dan preview hasil.
- Input: info sprint, upload FSD, link Swagger/OpenAPI, link Figma.
- Output: file `Scenario Sprint {test} Testing ({dev}).xlsx` persis seperti keluaran `build_scenario.py`
  (Statistic, Skenario, Bug List, Analisa), plus preview di browser.
- Panduan untuk user cara menyiapkan link Figma yang bisa dibaca.
- Dipakai tim QA saja, dibagikan lewat link, dengan satu password bersama.

## Bukan tujuan (versi 1)

- Tidak ada akun per user, riwayat, atau database. Job disimpan sementara lalu dihapus.
- Tidak mengedit case di browser. Perubahan dilakukan dengan generate ulang.
- Tidak membaca FSD master Google Doc atau API Contract Google Doc. FSD lewat upload, API lewat Swagger.
- Tidak membuat bug list otomatis. Sheet Bug List dibuat kosong dengan dropdown.
- Tidak menjalankan eksekusi test.
- Tidak melayani banyak generate sekaligus (lihat batasan B).

## Anti-tujuan

- Hasil yang tampak lengkap tetapi isinya mengarang nilai (pesan error, kode HTTP, nama kolom) yang
  tidak ada di sumber. Aturan skill tetap berlaku: tandai `Perlu verifikasi`, jangan menebak.
- Menyatakan cakupan "lengkap". Hasil harus menyebut apa yang tidak tercakup.
- Orang tanpa password bisa menjalankan Claude Code di mesin ini.
- Isi form (nama file, link, teks) dipakai sebagai instruksi atau perintah shell. Semua input user
  adalah data, bukan perintah.

## Pendekatan yang dipertimbangkan

| | Cara | Catatan |
|---|---|---|
| A | Server memanggil Claude API dengan instruksi dari skill. | Cocok untuk multi-user, tapi butuh API key berbayar per pemakaian dan Figma token terpisah. Ditolak user. |
| **B (dipilih)** | Server menjalankan Claude Code CLI (`claude -p`) di mesin ini dengan skill `qa-scenario` dan MCP Figma. | Paling setia ke skill, tanpa API key terpisah. Batasan: hanya jalan selama mesin menyala dan login Claude Code aktif, satu generate per waktu, memakai kuota langganan Claude pemilik mesin. |
| C | UI hanya membangun xlsx dari spec JSON yang sudah jadi. | Tidak ada analisa. Ditolak. |

Dipilih oleh user: **B**.

## Keputusan

Dari user:
- Web multi-akses, dibagikan ke tim QA saja.
- Upload dipisah sesuai kebutuhan script. FSD diupload. API Contract lewat link Swagger. Figma lewat link.
- Tombol Generate, lalu preview hasil.
- Tutorial Figma: Duplicate to drafts, lalu ambil link dari duplikat agar seluruh datanya bisa dibaca.
- Pendekatan B.

Keputusan saya (boleh dikoreksi):
- **Stack**: Python (FastAPI) dengan satu halaman HTML statis. Server hanya membungkus: menyimpan
  upload, menjalankan `claude -p` sebagai subprocess, membaca hasilnya, lalu menjalankan
  `build_scenario.py`. Paket dipasang dalam venv karena Python 3.14 di mesin ini belum punya paket
  selain `requests`.
- **Info sprint** (field form): sprint dev, sprint testing, judul fitur, environment (default Staging),
  opsional catatan cakupan. Dipakai untuk nama file dan nomor dokumen `TC-{dev}/{test}-{tahun}-1`.
  Tanggal uji = hari generate. Approval dikosongkan.
- **Menjalankan Claude Code**: tiap job dapat folder kerja sendiri berisi FSD yang diupload dan file
  input berisi isian form. Prompt menyuruh Claude mengikuti skill: baca sumber, analisa, tulis spec
  JSON ke folder job, validasi dengan `build_scenario.py --check`. Mode non-interaktif, daftar tool
  dibatasi (baca/tulis di folder job, jalankan skrip skill, WebFetch untuk Swagger, tool Figma
  read-only). Tidak ada akses shell bebas. Spec JSON adalah keluaran yang diharapkan server, bukan
  xlsx, supaya preview dan build dikendalikan server.
- **Skill**: skill dibaca dari folder ini (atau dipasang/di-symlink ke lokasi skill Claude Code).
  Perubahan skill langsung berlaku. Skill saat ini menyebut Google Drive dan jalur `/mnt/user-data`,
  `/home/claude`; builder perlu menyesuaikan prompt job agar memakai FSD upload dan folder job,
  tanpa mengubah file skill untuk pemakaian chat.
- **Figma**: dibaca lewat MCP Figma yang sudah terhubung di Claude Code pemilik mesin. Akun itu harus
  bisa melihat file yang dilink. Tutorial di UI menyuruh user: Duplicate to drafts, Share, ubah akses
  ke "Anyone with the link can view", salin link. Bila Figma tidak terbaca, generate tetap jalan tanpa
  Figma dan case terkait ditandai `Perlu verifikasi`, dan UI menunjukkan itu.
- **Swagger**: user menempel URL OpenAPI/Swagger JSON. Claude membacanya lewat WebFetch. Asumsi: URL
  bisa dijangkau dari mesin ini. Belum dikonfirmasi user.
- **FSD upload**: `.docx` atau `.pdf`. `pandoc` tidak terpasang di mesin ini, jadi konversi ke teks
  (library Python atau cara lain) diserahkan ke builder.
- **Antrian**: satu job berjalan per waktu, job lain menunggu dan UI menampilkan posisi antrian.
  Dibuat begitu agar kuota langganan dan sesi Claude Code tidak bertabrakan.
- **Password bersama** dari environment variable, dicek di server. Batas ukuran upload.
- **Preview**: dirender dari spec JSON. Tab Statistic, Skenario, Analisa, Bug List. Tombol unduh xlsx.
- **Rumus Statistic**: LibreOffice terpasang (`/usr/bin/soffice`), jadi server bisa recalc xlsx
  headless setelah build, seperti langkah 4 skill. Bila `soffice` tidak ada, lewati. Excel tetap
  menghitung ulang saat file dibuka.
- **Progres**: server menampilkan tahap kasar (menunggu antrian, membaca sumber, analisa, menulis
  case, validasi, build) berdasarkan keluaran stream Claude Code, tanpa janji persentase.
- **Penyimpanan**: file upload dan hasil di folder sementara, dihapus setelah 24 jam. Tidak ada
  database. Isi FSD, Swagger, dan Figma diproses oleh Claude (Anthropic), dan itu harus diketahui tim.

## Keputusan tambahan dari hasil tinjauan (pilihan saya, boleh dikoreksi)

- **Regresi**: di luar cakupan versi 1. Tidak ada upload FSD regresi. Hasil harus menulis "regresi
  tidak dicakup" di laporan ringkasan, dan section regresi hanya berisi case yang bisa diturunkan dari
  FSD yang diupload.
- **Catatan fitur per project**: tidak ada. Setiap job berdiri sendiri; project yang dibaca berbeda-beda dan tidak saling berhubungan.
- **Field meta**: `feature_no` = 1 (satu fitur per file), akhiran nomor dokumen `-1`,
  `system_name` = "Nama Sistem" (placeholder, tidak terikat project), `scope` ditentukan Claude dari sumber, `approval` dikosongkan.
- **Batas**: upload maksimal 20 MB, satu generate maksimal 30 menit lalu dibatalkan dengan pesan jelas.
  Tidak ada plafon biaya karena memakai langganan, tetapi antrian satu job per waktu membatasi beban.
- **Password**: pembatasan percobaan sederhana (jeda setelah beberapa kali salah). Penghapusan 24 jam
  mencakup upload dan hasil.
- **SSRF**: Swagger dibaca oleh Claude lewat WebFetch dengan tool lain dibatasi. Server tidak
  mengunduh URL dari user sendiri.

## Struktur yang diusulkan

```
app/
  server.py        # FastAPI: /login, /generate, /jobs/{id}, /jobs/{id}/download
  runner.py        # antrian, subprocess claude -p, parsing progres, validasi, build
  prompt.py        # menyusun prompt job dari isian form
  static/index.html
scripts/           # tidak diubah
```

## Diserahkan ke builder

- Cara memanggil `claude -p` (flag, format stream, izin tool, penanganan timeout dan error login).
- Konversi docx/pdf ke teks, format penyimpanan job, mekanisme progres (polling atau SSE).
- Desain visual: ikuti gaya Excel perusahaan (header biru muda, section hijau, precondition kuning).
- Cara menjalankan (uvicorn) dan `.env.example`.
- Pengujian: validasi spec contoh di `assets/examples/` lewat jalur build, plus tes runner dengan
  `claude` yang di-mock.

## Risiko yang perlu diketahui

- Mesin ini harus menyala dan Claude Code harus tetap login. Bila token login kedaluwarsa, Generate
  gagal sampai pemilik mesin login ulang.
- Satu generate memakai kuota langganan Claude pemilik mesin, dan bisa memakan beberapa menit.
- Kualitas hasil bergantung pada kelengkapan FSD, Swagger, dan Figma. Hasil tetap perlu ditinjau QA.
- Server menjalankan Claude Code atas nama input user. Pembatasan tool dan perlakuan input sebagai
  data (lihat anti-tujuan) wajib dipertahankan, kalau tidak ini menjadi celah eksekusi perintah.
