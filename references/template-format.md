# Format Template Skenario

`scripts/build_scenario.py`
sudah mereproduksi format ini; dokumen ini menjelaskan *isi* yang harus ditulis.

## Penamaan file dan dokumen

| Item | Pola | Contoh |
|---|---|---|
| Nama file | `Scenario Sprint {sprint_testing} Testing ({sprint_dev}).xlsx` | `Scenario Sprint 54 Testing (53).xlsx` |
| Document Number (Statistic!C2) | `TC-{sprint_dev}/{sprint_testing}-{tahun}-{urutan}` | `TC-53/54-2026-1` |
| Test Date (Statistic!C3) | tanggal, format tampil `mmmm yyyy` | November 2026 |
| Bug ID (Bug List) | `BUG-{sprint_dev}-{nn}` | `BUG-53-01` |

Pola nama file dan nomor dokumen disimpulkan dari satu contoh. Kalau user punya konvensi lain, ikuti user.

## Sheet

1. **Statistic** — metadata + rumus (Total Scenario, Pass, Failed, Pending, Blocker beserta persentase).
   Rumus menghitung dari `Skenario!J:J`, jadi nilai Status harus persis: `Pending`, `Pass`, `Failed`, `Blocker`.
   Catatan: di file contoh asli, baris A9 berlabel "Pending" padahal menghitung "Pass". Template di
   `assets/` sudah diperbaiki menjadi "Pass".
2. **Skenario** — isi utama.
3. **Bug List** — header + dropdown (Environment, Prioritas P0–P3, Severity, Reporter, Assign To, Status).
4. **Analisa** (opsional, tambahan skill) — log diskrepansi FSD/Figma/API Contract. Tidak ada di template
   asli; bisa dimatikan dengan `--no-analysis` bila tim tidak menghendaki sheet tambahan.

## Layout sheet Skenario

| Baris | Isi |
|---|---|
| 1 | C1 = nomor fitur, D1:E1 (merge, bold, kuning) = judul fitur, F1 (hijau) = cakupan, mis. `API/Backend/Frontend` |
| 2 | Header kolom (biru muda, bold) |
| 3 | Precondition, B3:J3 di-merge, kuning |
| 4.. | Baris section (hijau, A:M) diikuti baris case |

Kolom: `ID | Type Case | Test Method | Priority | Test Case Description | Step To Reproduce |
Expected Result | Actual Result | Platform | Status | Bug ID (Refer To) | Attachment | Notes`

## Aturan pengisian kolom

- **ID**: berurutan 1..n di seluruh file (script yang memberi nomor).
- **Type Case**: `Positive` atau `Negative`. Boundary/edge yang menguji penolakan, error, atau data
  yang seharusnya tidak muncul = `Negative`.
- **Test Method**: `Manual` (default), `Automated`, `Load`.
- **Priority** (definisi kerja yang dipakai skill ini; konfirmasi ke QA Lead bila tim punya definisi resmi):
  - `P0` — alur inti AC, kebenaran data/perhitungan, perubahan DB, keamanan/akses. Gagal = fitur tidak bisa rilis.
  - `P1` — alur sekunder, validasi, error handling, konsistensi lintas layer.
  - `P2` — fungsi pendukung: filter, search, pagination, validasi sekunder, empty state.
  - `P3` — kosmetik, copy/wording, layout, edge UX berdampak rendah.
  Rubrik lengkap dan target proporsi: `writing-rules.md`.
- **Test Case Description**: diawali tag area dalam kurung siku, lalu kalimat singkat.
  Contoh: `[API Get Products] Produk non-aktif tidak ikut terhitung`. Satu case = satu verifikasi
  (lihat `writing-rules.md`).
- **Step To Reproduce** & **Expected Result**: list bernomor. Di spec ditulis sebagai array; script yang
  menomori. Satu langkah = satu aksi yang bisa diulang orang lain. Expected harus bisa diverifikasi
  (nilai, kolom DB, kode HTTP, teks), bukan "berjalan dengan baik".
- **Actual Result**: kosong saat skenario baru.
- **Platform**: gabungan atom berikut dengan ` / `:
  `Mobile Apps` (aplikasi mobile), `PWA`, `Website` (Web Admin), `API`, `Backend`
  (log, cron, storage, proses server), `Database`. Contoh: `API / Database`.
- **Status**: skenario baru = `Pending`.
- **Notes**: wajib diisi; diawali label sumber: `[FSD x.y]`, `[Swagger METHOD /path]`,
  `[Figma: nama frame]`, atau `[Usulan]` (best practice tanpa sumber, tambahkan `Perlu konfirmasi SA`).
  Titik terbuka/asumsi: `[FSD 2.1] Perlu verifikasi: <konflik/asumsi>. Ref: <FSD No x.y / Figma node / API Contract section>`.
  Expected berisi placeholder `<NAMA_NILAI>`: Notes memuat `Menunggu nilai dari SA`. Aturan lengkap: `writing-rules.md`.

## Section

Judul section: `<Area> (<ref FSD>)`, contoh `API Pencarian (F-01 No 1.2)`.
Section tanpa ref FSD hanya untuk `Regresi`, `Lintas Layer`, `Non-Fungsional`, atau `Umum`.

## Precondition

Satu blok teks, diawali `Precondition:` lalu butir `- `. Minimal memuat: environment & perangkat,
build/versi aplikasi, user uji (per role/akses), data uji yang harus disiapkan, tabel DB yang perlu
akses, tool (Postman/proxy/log), dan acuan dokumen (FSD, Figma node, API Contract section).

## Skema JSON spec (input `build_scenario.py`)

```json
{
  "meta": {
    "system_name": "Nama Sistem",
    "doc_number": "TC-53/54-2026-1",
    "test_date": "2026-11-10",
    "test_description": "Pencarian produk dengan filter kategori",
    "environment": "Staging",
    "feature_no": 1,
    "feature_title": "Pencarian Produk",
    "scope": "API/Backend/Frontend",
    "approval": {"technical_lead": "...", "qa_lead": "...", "system_analyst": "..."}
  },
  "precondition": "Precondition:\n- ...",
  "sections": [
    {"title": "Halaman Produk (F-01 No 1.1)",
     "cases": [
       {"type": "Positive", "priority": "P0", "method": "Manual",
        "desc": "[Halaman Produk] Daftar produk tampil dengan pagination",
        "steps": ["Login sebagai Staff.", "Buka menu Produk."],
        "expected": ["Daftar produk aktif tampil, 10 baris per halaman."],
        "platform": "Mobile Apps", "status": "Pending", "notes": ""}
     ]}
  ],
  "analysis": [
    {"category": "Diskrepansi", "ref": "F-02 No 2.1 vs 1.2", "source": "FSD",
     "finding": "...", "impact": "...", "confidence": "High",
     "question": "...", "cases": "12, 13"}
  ],
  "bugs": []
}
```

Kategori Analisa yang dipakai: `Gap`, `Ambigu`, `Konflik` (sumber bertentangan; catat kedua versi),
`Nilai hilang` (placeholder `<NAMA_NILAI>` yang menunggu SA), `Diskrepansi`, `Input gagal`, `Risiko`, `Typo FSD`, `Ambigu`, `Gap`.

Jalankan `python scripts/build_scenario.py spec.json --check` dulu: script menolak nilai di luar
dropdown, platform tak dikenal, steps/expected kosong, dan memberi peringatan untuk deskripsi duplikat
serta section tanpa ref FSD. Ringkasan jumlah per type/priority/platform dicetak; pakai untuk
memeriksa keseimbangan cakupan sebelum file dibuat.
