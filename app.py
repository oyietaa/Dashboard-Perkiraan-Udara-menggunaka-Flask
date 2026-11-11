"""Website sederhana Flask: cek kualitas udara di suatu tempat.

Koordinat      : Open-Meteo Geocoding API
Kualitas udara : Open-Meteo Air Quality API

Jalankan:
    pip install -r requirements.txt
    python app.py
lalu buka http://127.0.0.1:5000
"""
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Kota pembanding untuk grafik perbandingan: nama -> (latitude, longitude)
KOTA_BANDING = {
    "Jakarta": (-6.21, 106.85),
    "Bandung": (-6.92, 107.61),
    "Surabaya": (-7.25, 112.75),
    "Medan": (3.59, 98.67),
    "Makassar": (-5.15, 119.43),
}


def kategori_aqi(aqi):
    """Ubah angka indeks kualitas udara jadi status, nama kelas CSS (warna), dan saran."""
    if aqi is None:
        return "Tidak ada data", "kosong", "Data kualitas udara belum tersedia untuk tempat ini."
    if aqi <= 50:
        return "Baik", "baik", "Udara bersih. Aman untuk beraktivitas di luar ruangan."
    if aqi <= 100:
        return "Sedang", "sedang", "Udara cukup baik. Orang yang sangat sensitif sebaiknya tidak terlalu lama beraktivitas di luar."
    if aqi <= 150:
        return "Kurang sehat", "kurang", "Anak-anak, lansia, dan penderita asma sebaiknya mengurangi aktivitas di luar ruangan."
    if aqi <= 200:
        return "Tidak sehat", "tidak-sehat", "Sebaiknya kurangi aktivitas di luar ruangan dan pakai masker jika harus keluar."
    if aqi <= 300:
        return "Sangat tidak sehat", "sangat", "Hindari aktivitas di luar ruangan. Pakai masker jika terpaksa keluar."
    return "Berbahaya", "berbahaya", "Tetap di dalam ruangan dan tutup jendela."


def nilai(x):
    """Angka kosong (None) ditampilkan sebagai tanda '-', bukan tulisan 'None'."""
    return "-" if x is None else x


def format_waktu(iso):
    """'2026-11-02T15:00' -> '02/11/2026 15:00'"""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]} {iso[11:16]}"


def format_jam(iso):
    """'2026-11-02T15:00' -> '02/11 15:00' (label sumbu grafik)"""
    return f"{iso[8:10]}/{iso[5:7]} {iso[11:16]}"


@app.route("/", methods=["GET", "POST"])
def home():
    tempat = "Yogyakarta"  # tampil pertama kali halaman dibuka
    if request.method == "POST":
        tempat = request.form.get("tempat", "").strip()

    detail, banding, grafik, error = None, [], None, None
    try:
        if not tempat:
            raise ValueError("Nama tempat belum diisi. Ketik nama kota atau daerah dulu.")

        # 1) Cari koordinat tempat yang diketik (Geocoding API)
        geo = requests.get(
            GEO_URL, params={"name": tempat, "count": 3, "language": "id"}, timeout=10
        )
        geo.raise_for_status()
        geo_data = geo.json()
        if "results" not in geo_data:
            raise ValueError(
                f"Tempat '{tempat}' tidak ditemukan. "
                "Periksa ejaannya atau coba ketik nama kota terdekat."
            )
        lokasi = geo_data["results"][0]
        nama_lengkap = ", ".join(
            x for x in [lokasi["name"], lokasi.get("admin1"), lokasi.get("country")] if x
        )

        # 2) Daftar lokasi: tempat yang dicari di urutan pertama, lalu kota pembanding
        nama = [lokasi["name"]]
        lat = [lokasi["latitude"]]
        lon = [lokasi["longitude"]]
        for k, (la, lo) in KOTA_BANDING.items():
            if k.lower() != lokasi["name"].lower():
                nama.append(k)
                lat.append(la)
                lon.append(lo)

        # 3) Ambil kualitas udara semua lokasi dalam satu panggilan API
        r = requests.get(
            API_URL,
            params={
                "latitude": ",".join(str(x) for x in lat),
                "longitude": ",".join(str(x) for x in lon),
                "current": "pm2_5,pm10,carbon_monoxide,carbon_dioxide,us_aqi",
                "hourly": "pm2_5,pm10",
                "past_days": 1,
                "forecast_days": 2,
                "timezone": "auto",
            },
            timeout=15,
        )
        r.raise_for_status()
        hasil = r.json()  # banyak koordinat -> list, satu item per lokasi

        for k, item in zip(nama, hasil):
            banding.append({"kota": k, "debu_halus": item["current"].get("pm2_5")})

        item = hasil[0]  # tempat yang dicari
        sekarang = item["current"]
        status, kelas, saran = kategori_aqi(sekarang.get("us_aqi"))
        detail = {
            "nama": nama_lengkap,
            "waktu": format_waktu(sekarang["time"]),
            "indeks": nilai(sekarang.get("us_aqi")),
            "status": status,
            "kelas": kelas,
            "saran": saran,
            "debu_halus": nilai(sekarang.get("pm2_5")),
            "debu_kasar": nilai(sekarang.get("pm10")),
            "co": nilai(sekarang.get("carbon_monoxide")),
            "co2": nilai(sekarang.get("carbon_dioxide")),
        }
        # Data untuk grafik, dikirim ke JavaScript sebagai satu paket JSON
        grafik = {
            "jam": [format_jam(t) for t in item["hourly"]["time"]],
            "debu_halus_jam": item["hourly"]["pm2_5"],
            "debu_kasar_jam": item["hourly"]["pm10"],
            "kota": [b["kota"] for b in banding],
            "debu_halus_kota": [b["debu_halus"] for b in banding],
        }
    except ValueError as e:
        error = str(e)
    except requests.exceptions.HTTPError as e:
        # HTTPError harus di atas RequestException karena HTTPError adalah turunannya
        if e.response is not None and e.response.status_code == 429:
            error = "Terlalu banyak permintaan ke server data. Tunggu sebentar, lalu coba lagi."
        else:
            error = "Server data sedang bermasalah. Coba lagi nanti."
    except requests.exceptions.RequestException:
        error = "Tidak dapat terhubung ke server data. Periksa koneksi internet, lalu coba lagi."
    except (KeyError, IndexError, TypeError):
        error = "Data dari server tidak sesuai format yang diharapkan."

    return render_template(
        "index.html", detail=detail, grafik=grafik, error=error, tempat=tempat
    )


if __name__ == "__main__":
    app.run(debug=True)