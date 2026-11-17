# Penggabungan Prompt v2 ke Skill: Rencana Fase

Sumber ide: `samples/prompt_scenario_creator_v2.md` (prompt dari tim). Tujuan: mengambil ide kualitasnya
ke skill `qa-scenario` dan pipeline web, tanpa mengganti skema `sections/cases` yang dibaca
`scripts/build_scenario.py`.

## Keputusan

- Skema spec tetap `meta / precondition / sections[].cases[] / analysis[] / bugs[]`. Prompt v2 tidak dipakai mentah.
- Eksekusi non-interaktif: tidak ada "tunggu perintah lanjut" dan tidak ada permintaan file ke user. Sumber gagal dibaca: lanjut dan tandai.
- Label sumber di awal Notes: `[FSD x.y]`, `[Swagger METHOD /path]`, `[Figma: nama frame]`, `[Usulan]`. Titik terbuka tetap memakai `Perlu verifikasi: ...`. Bentuk gabungan: `[FSD 2.1] Perlu verifikasi: <isi>. Ref: <rujukan>`.
- Angka yang tidak ada di sumber ditulis sebagai placeholder bernama `<NAMA_NILAI>`, Notes `Menunggu nilai dari SA`, dan dicatat di Analisa (kategori `Nilai hilang`).
- Ringkasan dan proporsi dihitung script, bukan model. Pelanggaran jadi peringatan `[Mutu]` di `--check`, bukan ERROR.
- Form web menambah satu field opsional: `roles` (daftar role user, teks bebas). Otomasi dan PIC tidak ditambahkan. Urutan otoritas tetap FSD > Figma > Swagger.
- Semua contoh dan checklist netral domain. Tidak ada istilah dari project tertentu.

## Fase 1 (paralel, tiga agent, file tidak beririsan)

- **A. Dokumen skill:** `SKILL.md`, `references/coverage-checklist.md`. Tambah tahap validasi input, inventaris elemen, checklist wajib per jenis elemen, checklist lintas fitur, self-review.
- **B. Aturan penulisan:** `references/writing-rules.md` baru, `references/template-format.md`, `assets/examples/example_spec.json`. Aturan 6.1-6.7, label sumber, placeholder, rubrik prioritas, contoh buruk vs baik.
- **C. Pemeriksa mutu:** `scripts/build_scenario.py`, `tests/test_build_scenario.py`. Peringatan `[Mutu]`: proporsi P0 di luar 5-20%, Negative < 30%, kata terlarang di Expected, dua kode HTTP dalam satu Expected, Notes tanpa label sumber, placeholder tanpa catatan SA, ringkasan proporsi di `summary()`.

## Fase 2 (paralel, dua agent)

- **D. Web:** `app/jobs.py`, `app/server.py`, `app/prompt.py`, `app/static/index.html`, tes terkait. Field `roles`; prompt job memuat tahap-tahap baru; UI menampilkan peringatan mutu di preview.
- **E. Backend preview:** `app/finalize.py`, `tests/test_finalize.py`. `finalize` dan `preview_data` membawa daftar peringatan `[Mutu]` dari `validate()`.

## Fase 3 (verifikasi)

- Satu reviewer read-only: konsistensi antar dokumen skill, contoh spec lolos `--check` tanpa peringatan mutu, tidak ada istilah domain tertentu.
- Satu uji end-to-end dengan `claude` asli memakai FSD contoh, lalu baca hasilnya.

## Status (2026-11-17)

Fase 1, 2, dan 3 selesai. `pytest -q`: 58 passed.

- Reviewer Fase 3 menemukan enam kelompok masalah dan semuanya sudah diperbaiki: kategori analisa disamakan (termasuk `Input gagal`), kata terlarang di dokumen dan script disamakan, pola dua kode HTTP hanya aktif bila ada konteks status/kode/http/respons, `validate()` tidak crash pada spec salah bentuk, angka proporsi disamakan (Negative minimal 30%), dan peringatan referensi FSD menerima penomoran bebas seperti `(FSD No 1.a.i)`.
- Uji end-to-end dengan `claude` asli memakai FSD PDF contoh dan role "Admin, Operator": selesai dalam 190 detik, 53 case, 14 temuan analisa. Notes berlabel sumber, placeholder bernama dipakai untuk nilai yang tidak ada di FSD, dan role dipakai untuk case hak akses.
- Belum dilakukan: `finalize()` membawa peringatan (hanya `preview_data` yang membawa), uji panel "Peringatan mutu" di browser, uji Figma dan Swagger nyata.
