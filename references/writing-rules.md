# Aturan Penulisan Skenario

Berlaku untuk semua domain. Kolom dan skema ada di `template-format.md`; cakupan ada di `coverage-checklist.md`.
Prinsip: jujur lebih penting daripada lengkap. Celah sumber dicatat di Analisa, tidak ditebak.

## 1. Satu skenario, satu verifikasi
Jangan gabungkan beberapa aksi atau status dalam satu case. Login, logout, tambah data, ubah data = case terpisah.

## 2. Expected deterministik dan terukur
- Dilarang: "wajar", "mendekati", "sesuai kesepakatan", "kondisi tertentu", "melewati batas" tanpa angka, "dan lain-lain", "dll", "dengan benar".
- Dilarang dua kemungkinan benar: "400/404", "OFF/Stopped", "ditolak atau file kosong".
- Nilai tidak ada di sumber: tulis placeholder bernama `<NAMA_NILAI>` (mis. `<BATAS_UKURAN_FILE_MB>`), Notes `Menunggu nilai dari SA`, dan catat di Analisa kategori `Nilai hilang`. Jangan menebak angka.
- Ada rumus: tulis lengkap dengan satuan dan contoh hitung, mis. `Total = harga satuan x jumlah; 15.000 x 3 = 45.000 (Rp)`.

## 3. Label sumber di awal Notes
Satu atau lebih label per case:
- `[FSD x.y]`
- `[Swagger METHOD /path]`
- `[Figma: nama frame]`
- `[Usulan]` untuk best practice QA tanpa sumber; tambahkan `Perlu konfirmasi SA`.

Titik terbuka digabung dalam satu bentuk: `[FSD 2.1] Perlu verifikasi: <isi>. Ref: <rujukan>`.
Teks UI, pesan, kode HTTP, nama kolom, dan nilai default ditulis persis hanya bila ada di sumber. Jika tidak, tulis deskripsi umum ("muncul pesan validasi format") dan beri `[Usulan]`.

## 4. Precondition dan data uji
- Per modul: role user, kondisi perangkat/sistem, data awal (mis. "3 item terdaftar, 2 aktif").
- Expected berangka ("2 / 3") wajib punya data awal yang menghasilkannya di precondition atau langkah.
- Langkah yang butuh manipulasi infrastruktur (matikan service, kosongkan data di backend): tulis caranya atau tandai `Butuh bantuan Dev` di Notes.

## 5. Step to Reproduce
Bernomor, satu aksi per langkah, memakai nama menu/tombol sesuai sumber, dengan nilai input konkret ("isi Nama dengan `Budi Test`", bukan "isi data valid").

## 6. Butir sumber bermasalah
Butir FSD yang kosong, ambigu, atau tidak bermakna tidak dijadikan case. Masukkan ke Analisa sebagai pertanyaan.

## 7. Konflik antar sumber
Ikuti urutan FSD > Figma > Swagger untuk Expected, lalu catat kedua versi di Analisa kategori `Konflik`. Jangan memilih diam-diam.

## Rubrik prioritas

| Prioritas | Definisi | Target |
|---|---|---|
| P0 | Gagal = rilis diblokir: data hilang/rusak, data salah terkirim ke sistem lain, celah keamanan/auth, alur inti tidak jalan | 10-15% |
| P1 | Fungsi utama salah tapi ada workaround, atau dampak ke banyak user | 30-40% |
| P2 | Fungsi pendukung: filter, search, pagination, validasi sekunder, empty state | 35-45% |
| P3 | Kosmetik, responsif, teks, kenyamanan | 5-15% |

Negative minimal 30% dari total. P0 di luar 5-20%: tinjau ulang (kedua pemeriksaan proporsi hanya berlaku bila total case >= 10) dan jelaskan alasannya. Script `build_scenario.py --check` menghitung proporsi ini dan melaporkannya sebagai peringatan `[Mutu]` (bukan ERROR).

## Contoh buruk vs baik

Bentuk spec: `type / priority / desc / steps / expected / platform / notes`.

Buruk: gabungan, tidak terukur, tanpa sumber.
```json
{"type": "Positive", "priority": "P0",
 "desc": "[Log Aktivitas] Login, logout, tambah data, ubah data tercatat",
 "steps": ["Lakukan semua aksi."],
 "expected": ["Setiap aksi tercatat dengan benar."],
 "platform": "Website", "notes": ""}
```

Baik: dipecah, terukur, bersumber.
```json
{"type": "Positive", "priority": "P1",
 "desc": "[Log Aktivitas] Login berhasil tercatat",
 "steps": ["Logout jika sedang login.", "Login dengan user `qa_admin` dan password valid.", "Buka menu Log Aktivitas.", "Filter Aksi = Login."],
 "expected": ["Ada 1 entri baru: Aksi Login, Status Berhasil, User `qa_admin`, Waktu dalam 1 menit dari waktu login.", "Password tidak tampil di kolom mana pun."],
 "platform": "Website",
 "notes": "[FSD 2.3] Perlu verifikasi: format Waktu belum didefinisikan. Ref: FSD 2.3"}
```

Buruk: dua kemungkinan benar, kode tanpa sumber.
```json
{"type": "Negative", "priority": "P1",
 "desc": "[API Tambah Data] Kode duplikat ditolak",
 "steps": ["Kirim POST dengan kode yang sudah ada."],
 "expected": ["Respons 409/400 dengan pesan kode sudah ada."],
 "platform": "API", "notes": ""}
```

Baik:
```json
{"type": "Negative", "priority": "P1",
 "desc": "[API Tambah Data] Kode duplikat ditolak",
 "steps": ["Kirim POST /items dengan kode `ABC-001` yang sudah ada."],
 "expected": ["Respons ditolak dengan status `<KODE_HTTP_DUPLIKAT>`.", "Tidak ada data baru tersimpan."],
 "platform": "API",
 "notes": "[Usulan] Menunggu nilai dari SA. Swagger tidak mendefinisikan respons duplikat; perlu konfirmasi 409 atau 400."}
```
