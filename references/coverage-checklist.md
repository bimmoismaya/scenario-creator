# Checklist Cakupan Skenario

Pakai checklist ini per Acceptance Criteria (AC). Tidak semua butir relevan untuk setiap AC; yang
dilewati harus karena memang tidak berlaku, bukan karena terlupa.

## 1. Analisa sumber (lakukan sebelum menulis case)

Bandingkan tiga sumber untuk tiap AC dan catat setiap selisih di `analysis` spec:

- **FSD vs FSD**: istilah/angka yang berbeda antar AC (mis. `>=` di satu AC, `>` di AC lain), salah
  salin dari AC lain (nama endpoint, nama halaman), bagian "Out of Scope" yang bertentangan dengan isi dokumen.
- **FSD vs Figma**: label, urutan elemen, empty state, popup copy, elemen yang ada di satu sumber saja
  (mis. FSD bilang kamera saja, Figma menampilkan tombol Upload).
- **FSD vs API Contract**: nama field, tipe, wajib/tidak, format item (`string` vs objek),
  content-type, batas ukuran file, pesan response.
- **Gap**: perilaku yang tidak didefinisikan di mana pun (input kosong, batas waktu, akses tanpa izin,
  data legacy, versi aplikasi lama). Tetap tulis case-nya; Expected = perilaku yang paling aman dan
  tandai Notes `Perlu verifikasi`.
- **Risiko bisnis**: efek samping lintas fitur (mis. submit satu fitur ikut mengubah data fitur lain).

- **Konflik**: sumber bertentangan. Expected mengikuti sumber paling otoritatif (FSD > Figma > Swagger);
  catat kedua versi.
- **Nilai hilang**: ambang, batas, toleransi, interval, ukuran maksimum, atau format pesan yang
  dibutuhkan tapi tidak ada di sumber. Case memakai placeholder `<NAMA_NILAI>`.
- **Butir bermasalah**: butir FSD kosong, ambigu, atau tidak bermakna. Jangan jadi case; catat sebagai
  pertanyaan.

Kategori `analysis`: `Diskrepansi`, `Ambigu`, `Gap`, `Risiko`, `Typo FSD`, `Konflik`, `Nilai hilang`, `Input gagal`. Confidence:
`High` (tertulis jelas di dua sumber yang bertentangan), `Medium` (inferensi kuat), `Low` (dugaan).

## 2. Checklist wajib per jenis elemen

Turunkan case dari inventaris elemen. Lewati butir hanya bila memang tidak relevan, dan sebutkan
alasannya di laporan.

| Elemen | Case wajib |
| --- | --- |
| Field form | nilai valid; kosong (wajib diisi); format salah; batas bawah/atas; di luar batas; tipe data salah; spasi/karakter khusus; simpan lalu reload (persistensi); batal di konfirmasi |
| Tabel / list | kolom dan urutannya; empty state; pagination; search ada hasil dan tanpa hasil; filter tunggal; kombinasi filter; reset filter; export (ada data dan tanpa data); detail baris |
| Card / angka | nilai sesuai sumber data; nilai 0; nilai maksimum atau melebihi kapasitas; berubah setelah aksi; klik navigasi |
| Tombol aksi | sukses; gagal; status loading; klik ganda (hanya satu request); tombol nonaktif saat proses |
| Endpoint API | sukses (kode dan pesan sesuai contract); field wajib hilang (satu case per field); tipe salah; ID tidak ada; duplikat; tanpa token (401); role tidak berhak (403); file terlalu besar atau tipe tidak didukung; rate limit bila didefinisikan |
| Event / async | terjadi di atas ambang; tidak terjadi di bawah ambang; transisi status dan kembali; gagal kirim; konsistensi lintas layer |
| Perhitungan | hitung manual dengan contoh angka dan satuan; nilai 0; pembulatan; konversi satuan ditulis eksplisit |

## 3. Checklist lintas fitur (sekali per modul)

- **Auth dan role**: akses tanpa login; akses per role dari daftar role yang diberikan; session timeout.
- **Ketahanan koneksi**: saat backend atau sistem tujuan tidak terjangkau, data di-queue dan dikirim
  ulang setelah pulih, atau hilang?
- **Restart service**: konfigurasi dan session kembali seperti semula?
- **Data sensitif**: password, PIN, token tidak tampil di log, payload, maupun UI.
- **Lintas layer**: data yang sama konsisten di UI, API, database, dan sistem tujuan.
- **Responsif**: tampilan lebar 375px bila aplikasi web.
- **Retensi**: lama penyimpanan log atau data, bila didefinisikan.

## 4. Frontend — Mobile Apps

- Navigasi masuk/keluar halaman, tombol back fisik dan back aplikasi, popup konfirmasi.
- Tampilan sesuai Figma: label, urutan, empty state, loading, error state, teks panjang.
- Input: wajib/tidak, format (desimal, koma/titik), batas, tombol submit disabled/enabled.
- Kamera: izin (diberikan/ditolak/MDM), preview, retake, hapus, rasio/crop, kompresi, aplikasi ke background.
- Hitungan yang ditampilkan = response API (cocokkan angka, bukan hanya "muncul").
- Pemanggilan ulang API saat kembali ke halaman (cek di proxy/log).
- Klik ganda, jaringan putus/timeout, session/token kedaluwarsa.

## 5. Frontend — Website / PWA

- Filter (default, kombinasi, reset), kolom baru, mapping nilai enum ke label, sorting, pagination.
- Download: isi file, jumlah sheet/tab, filter terbawa, data cocok DB, file kosong.
- Lazy-load (request baru hanya saat expand).
- Kontrol akses: tombol tersembunyi untuk role tanpa izin **dan** request langsung ke endpoint ditolak.
- Regresi tampilan halaman existing.

## 6. API (per endpoint di API Contract)

- Happy path: status code, `success`, `message`, struktur dan tipe tiap field sama dengan contract.
- Auth: tanpa token, token invalid/kedaluwarsa → 401.
- Method salah → 405 (P2).
- Validasi body: field wajib hilang, tipe salah, array kosong, nilai di luar enum → 422 (atau perilaku
  yang ditetapkan tim; tandai verifikasi bila contract tidak menyebut).
- Multipart: content-type, file hilang, ukuran > batas, tipe file salah, ekstensi palsu.
- Payload dimanipulasi klien (jumlah tidak sama dengan jumlah item, data milik pengguna lain).
- Idempotensi/duplikasi: submit dua kali, item duplikat dalam array.
- Konsistensi naming field (typo di contract dicatat sebagai diskrepansi).
- Volume besar (ratusan–ribuan item) — response time dan timeout.

## 7. Backend / Database

- Migrasi: kolom baru (tipe, enum, nullable, default), backfill data lama, rollback.
- Insert: tiap kolom yang disebut FSD dicek nilainya (id format, FK, quantity, category enum, created_by, timestamps).
- Update: baris yang tepat (mis. kondisi `WHERE`, soft-delete `deleted_at IS NULL`), kolom yang berubah, kolom
  yang tidak boleh berubah.
- Perhitungan: rumus (selisih, total, agregasi), pembulatan desimal,
  batas 0.
- Atomicity: kegagalan di tengah (upload storage gagal, DB error) tidak meninggalkan data setengah jadi.
- Storage: path S3 sesuai pola, file benar-benar ada, nama unik, akses tidak publik.
- Log: isi log (user, id, tipe, jumlah) dan baris log terpisah bila diminta.
- Efek ke query fitur lain (data baru memengaruhi report/list lain).

## 8. Lintas layer

- Angka yang sama di Mobile, Web, API, dan DB untuk data yang sama.
- Alur end-to-end: aksi di aplikasi mobile → data DB → tampil di Web.

## 9. Regresi

- Ambil perilaku existing yang bersinggungan dengan fitur baru dari dokumen yang diberikan.
- Fitur existing yang berbagi tabel/endpoint (v1 API, scan lain, report).
- Aplikasi versi lama vs backend baru (perubahan content-type, field wajib baru).
- Klien lain yang memakai endpoint yang sama.

## Keseimbangan

Target kasar: Negative ≥ 30% dari total; setiap AC punya minimal satu case P0; setiap tabel yang
disentuh FSD punya minimal satu case Database. Ini pedoman, bukan kuota — jangan menambah case kosong
demi angka.
