from flask import Flask, render_template, request
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely import wkt
import plotly.express as px
import plotly.graph_objects as go

app = Flask(__name__, static_folder='static')

def process_data(jenis_umkm):
    # Membaca file CSV
    file_path = 'data/data_merged.csv'  # Pastikan lokasi file benar
    data_merged = pd.read_csv(file_path)

    # Memilih dataset berdasarkan jenis UMKM
    if jenis_umkm == "sembako":
        UMKM = data_merged[['PROVINSI', 'KAB_KOTA', 'KECAMATAN', 'DESA', 'JUMLAH_PENDUDUK', 
                            'TAMAT_SD', 'JUMLAH_KK', 'KEPADATAN', 'geometry']]
        weights = {
            'BOBOT_JUMLAH_PENDUDUK': 0.3,
            'BOBOT_TAMAT_SD': 0.2,
            'BOBOT_JUMLAH_KK': 0.25,
            'BOBOT_KEPADATAN': 0.25
        }
    elif jenis_umkm == "kuliner_nonis":
        UMKM = data_merged[['PROVINSI', 'KAB_KOTA', 'KECAMATAN', 'DESA', 'JUMLAH_PENDUDUK', 
                            'KEPADATAN', 'KRISTEN', 'KATOLIK', 'HINDU', 'BUDHA', 'KONGHUCU', 'geometry']]
        weights = {
            'BOBOT_JUMLAH_PENDUDUK': 0.1,
            'BOBOT_KEPADATAN': 0.1,
            'BOBOT_KRISTEN': 0.2,
            'BOBOT_KATOLIK': 0.2,
            'BOBOT_HINDU': 0.2,
            'BOBOT_BUDHA': 0.1,
            'BOBOT_KONGHUCU': 0.1
        }
    else:
        return pd.DataFrame()  # Mengembalikan DataFrame kosong jika jenis UMKM tidak valid

    # Konversi kolom 'geometry' menjadi objek geometri
    UMKM['geometry'] = UMKM['geometry'].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(UMKM, geometry='geometry')
    gdf.set_crs(epsg=4326, inplace=True)

    # Menghitung kuartil untuk semua kolom numerik
    numerical_columns = gdf.select_dtypes(include=['number']).columns

    # Fungsi untuk melabeli berdasarkan kuartil
    def label_potensi(x, q1, q2, q3):
        if x <= q1:
            return '1'  # KURANG
        elif x <= q2:
            return '2'  # CUKUP
        elif x <= q3:
            return '3'  # BANYAK
        else:
            return '4'  # SANGAT BANYAK

    # Melabeli setiap kolom numerik
    for col in numerical_columns:
        Q1, Q2, Q3 = gdf[col].quantile([0.25, 0.5, 0.75])
        gdf[f'BOBOT_{col}'] = gdf[col].apply(label_potensi, args=(Q1, Q2, Q3))

    # Matriks keputusan menggunakan bobot yang sesuai dengan jenis UMKM
    criteria_columns = list(weights.keys())
    decision_matrix = gdf[criteria_columns].apply(pd.to_numeric)
    normalized_matrix = decision_matrix / np.sqrt((decision_matrix**2).sum())
    weighted_matrix = normalized_matrix * np.array(list(weights.values()))
    gdf['Total_Score'] = weighted_matrix.sum(axis=1)

    # Membuat label rekomendasi berdasarkan total skor
    Q1 = gdf['Total_Score'].quantile(0.25)
    Q2 = gdf['Total_Score'].quantile(0.5)
    Q3 = gdf['Total_Score'].quantile(0.75)

    def label_recommendation(x):
        if x <= Q1:
            return 'TIDAK REKOMENDASI'
        elif x <= Q2:
            return 'KURANG REKOMENDASI'
        elif x <= Q3:
            return 'CUKUP REKOMENDASI'
        else:
            return 'DIREKOMENDASIKAN'

    gdf['REKOMENDASI'] = gdf['Total_Score'].apply(label_recommendation)
    return gdf


def create_choropleth(data):
    # Skema warna kustom untuk kategori
    color_map = {
        'TIDAK REKOMENDASI': 'red',
        'KURANG REKOMENDASI': 'yellow',
        'CUKUP REKOMENDASI': 'green',
        'DIREKOMENDASIKAN': 'darkgreen'
    }

    # Membuat peta dengan latar belakang Mapbox
    fig = go.Figure(go.Choroplethmapbox(
        geojson=data.geometry.__geo_interface__,  # GeoJSON dari geometrinya
        locations=data.index,   # Lokasi unik
        z=data['REKOMENDASI'].apply(lambda x: {'TIDAK REKOMENDASI': 1, 'KURANG REKOMENDASI': 2, 'CUKUP REKOMENDASI': 3, 'DIREKOMENDASIKAN': 4}[x]),  # Mapping the categories to numbers
        hoverinfo='location+z+text',  # Informasi hover
        hovertext=data['DESA'],  # Teks untuk hover
        coloraxis="coloraxis",  # Menggunakan coloraxis untuk menghubungkan dengan color scale
        showscale=True,  # Menampilkan color scale
    ))

    # Menambahkan layout Mapbox dan pengaturan peta
    fig.update_layout(
        mapbox_style="carto-positron",  # Mapbox Style, bisa diganti dengan 'streets', 'outdoors', dll.
        mapbox_center={"lat": -7.5, "lon": 108.3},  # Pusatkan peta pada koordinat yang diinginkan
        mapbox_zoom=10,  # Zoom level
        margin={"r":0,"t":0,"l":0,"b":0},  # Menyesuaikan margin
        title="Peta Rekomendasi UMKM"
    )

    # Menambahkan coloraxis untuk warna kustom
    fig.update_layout(
        coloraxis_colorscale=[[0, 'red'], [0.33, 'yellow'], [0.66, 'green'], [1, 'darkgreen']],  # Menghubungkan warna dengan kategori
        coloraxis_colorbar_title="Kategori Rekomendasi"
    )

    # Ekspor peta ke HTML
    return fig.to_html(full_html=False)



@app.route('/', methods=['GET', 'POST'])
def index():
    recommendations = []
    map_html = ""
    
    if request.method == 'POST':
        jenis_umkm = request.form['jenisUmkm']
        data = process_data(jenis_umkm)
        recommendations = data[['PROVINSI', 'KAB_KOTA', 'KECAMATAN', 'DESA', 'Total_Score', 'REKOMENDASI']].to_dict(orient='records')
        map_html = create_choropleth(data)
    
    return render_template('index.html', recommendations=recommendations, map_html=map_html)

if __name__ == '__main__':
    app.run(debug=True)
