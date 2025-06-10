"""
RAAM 2025 Live Dashboard - Web Scraping Version
Extrahiert Daten direkt von der TrackLeaders Webseite
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import json

# Seiten-Konfiguration
st.set_page_config(
    page_title="RAAM 2025 Live Tracker - Fritz Geers",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .fritz-highlight {
        background-color: #ffd700;
        padding: 10px;
        border-radius: 5px;
        font-weight: bold;
    }
    .metric-container {
        padding: 10px;
        background-color: #f0f2f6;
        border-radius: 10px;
        margin: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Demo-Daten für Entwicklung
DEMO_DATA = [
    {
        'name': 'Fritz Geers',
        'bib': '001',
        'category': 'SOLO',
        'position': 3,
        'distance': 156.8,
        'speed': 12.4,
        'location': 'Flagstaff, AZ',
        'lat': 35.1983,
        'lon': -111.6513
    },
    {
        'name': 'John Smith',
        'bib': '002', 
        'category': 'SOLO',
        'position': 1,
        'distance': 189.2,
        'speed': 14.8,
        'location': 'Prescott, AZ',
        'lat': 34.5400,
        'lon': -112.4685
    },
    {
        'name': 'Maria Rodriguez',
        'bib': '003',
        'category': 'SOLO',
        'position': 2,
        'distance': 178.5,
        'speed': 13.9,
        'location': 'Flagstaff, AZ',
        'lat': 35.1983,
        'lon': -111.6513
    },
    {
        'name': 'Peter Mueller',
        'bib': '004',
        'category': 'SOLO', 
        'position': 4,
        'distance': 145.2,
        'speed': 11.8,
        'location': 'Williams, AZ',
        'lat': 35.2494,
        'lon': -112.1910
    },
    {
        'name': 'Sarah Johnson',
        'bib': '005',
        'category': 'SOLO',
        'position': 5,
        'distance': 134.7,
        'speed': 10.9,
        'location': 'Ash Fork, AZ',
        'lat': 35.2253,
        'lon': -112.4838
    }
]

@st.cache_data(ttl=300)  # Cache für 5 Minuten
def fetch_trackleaders_data():
    """Versucht Daten von TrackLeaders zu holen"""
    try:
        # Versuche die Hauptseite zu laden
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Versuche verschiedene URLs
        urls = [
            'https://trackleaders.com/raam25',
            'https://trackleaders.com/raam25f.php'
        ]
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    # Versuche JavaScript-Daten zu extrahieren
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Suche nach JavaScript mit Tracking-Daten
                    scripts = soup.find_all('script')
                    for script in scripts:
                        if script.string:
                            # Suche nach Variablen die Tracking-Daten enthalten könnten
                            patterns = [
                                r'var\s+racers\s*=\s*(\[.*?\]);',
                                r'trackData\s*=\s*(\{.*?\});',
                                r'raceData\s*:\s*(\[.*?\])',
                            ]
                            
                            for pattern in patterns:
                                match = re.search(pattern, script.string, re.DOTALL)
                                if match:
                                    try:
                                        data = json.loads(match.group(1))
                                        return process_scraped_data(data)
                                    except:
                                        continue
            except:
                continue
        
        # Wenn nichts funktioniert, nutze Demo-Daten
        st.warning("Live-Daten momentan nicht verfügbar. Zeige Demo-Daten.")
        return DEMO_DATA
        
    except Exception as e:
        st.error(f"Fehler beim Datenabruf: {str(e)}")
        return DEMO_DATA

def process_scraped_data(data):
    """Verarbeitet gescrapte Daten in einheitliches Format"""
    processed = []
    
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                processed.append({
                    'name': item.get('name', ''),
                    'bib': str(item.get('bib', item.get('number', ''))),
                    'category': item.get('category', item.get('class', 'SOLO')),
                    'position': int(item.get('position', item.get('rank', 999))),
                    'distance': float(item.get('distance', item.get('miles', 0))),
                    'speed': float(item.get('speed', item.get('mph', 0))),
                    'location': item.get('location', item.get('checkpoint', '')),
                    'lat': float(item.get('lat', item.get('latitude', 0))),
                    'lon': float(item.get('lon', item.get('longitude', 0)))
                })
    
    return processed if processed else DEMO_DATA

def create_dataframe(data):
    """Erstellt DataFrame aus den Daten"""
    df = pd.DataFrame(data)
    
    # Fritz Geers identifizieren
    df['is_fritz'] = df['name'].str.lower().str.contains('fritz|geers', na=False)
    
    # Nur Solo-Fahrer
    df = df[df['category'].str.upper() == 'SOLO']
    
    # Sortieren nach Position
    df = df.sort_values('position')
    
    return df

def main():
    # Sidebar
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    st.sidebar.markdown("---")
    
    # Refresh Button
    if st.sidebar.button("🔄 Daten aktualisieren"):
        st.cache_data.clear()
        st.rerun()
    
    # Info
    st.sidebar.markdown("---")
    st.sidebar.info(
        "**Fritz Geers** wird mit ⭐ hervorgehoben.\n\n"
        "Daten werden alle 5 Minuten aktualisiert."
    )
    
    # Hauptbereich
    st.title("🏆 Race Across America 2025 - Live Tracking")
    st.markdown(f"*Stand: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    # Daten laden
    with st.spinner("Lade Daten..."):
        data = fetch_trackleaders_data()
        df = create_dataframe(data)
    
    if df.empty:
        st.error("Keine Daten verfügbar")
        return
    
    # Fritz Geers Status
    fritz_data = df[df['is_fritz']]
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        
        st.markdown("### ⭐ Fritz Geers Status")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Position", f"#{fritz['position']}")
        with col2:
            st.metric("Distanz", f"{fritz['distance']:.1f} mi")
        with col3:
            st.metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
        with col4:
            st.metric("Standort", fritz['location'])
        with col5:
            # Rückstand berechnen
            leader = df.iloc[0]
            gap = leader['distance'] - fritz['distance']
            st.metric("Rückstand", f"{gap:.1f} mi" if gap > 0 else "Führend!")
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Rangliste", "🗺️ Karte", "📈 Statistiken"])
    
    with tab1:
        st.subheader("Aktuelle Rangliste - Solo Kategorie")
        
        # Rangliste vorbereiten
        display_df = df[['position', 'name', 'distance', 'speed', 'location', 'is_fritz']].copy()
        display_df.columns = ['Pos', 'Name', 'Distanz (mi)', 'Geschw. (mph)', 'Standort', 'is_fritz']
        
        # Fritz gelb markieren
        def highlight_fritz(row):
            if row['is_fritz']:
                return ['background-color: #ffd700'] * len(row)
            return [''] * len(row)
        
        styled_df = display_df.drop('is_fritz', axis=1).style.apply(highlight_fritz, axis=1)
        st.dataframe(styled_df, use_container_width=True, height=600)
    
    with tab2:
        st.subheader("Live Positionen")
        
        # Karte erstellen
        if 'lat' in df.columns and 'lon' in df.columns:
            # Zentrum berechnen
            center_lat = df['lat'].mean()
            center_lon = df['lon'].mean()
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=6)
            
            # RAAM Route (vereinfacht)
            route_points = [
                [33.0198, -117.0864],  # Oceanside, CA (Start)
                [33.4484, -112.0740],  # Phoenix, AZ
                [35.0844, -106.6504],  # Albuquerque, NM
                [35.4676, -97.5164],   # Oklahoma City, OK
                [38.6270, -90.1994],   # St. Louis, MO
                [39.7392, -84.1916],   # Dayton, OH
                [39.9526, -75.1652]    # Philadelphia, PA (Ziel)
            ]
            
            folium.PolyLine(route_points, color="blue", weight=3, opacity=0.6).add_to(m)
            
            # Fahrer-Positionen
            for _, racer in df.iterrows():
                if racer['lat'] != 0 and racer['lon'] != 0:
                    color = 'gold' if racer['is_fritz'] else 'red'
                    icon = 'star' if racer['is_fritz'] else 'bicycle'
                    
                    folium.Marker(
                        [racer['lat'], racer['lon']],
                        popup=f"""
                        <b>{racer['name']}</b><br>
                        Position: #{racer['position']}<br>
                        Distanz: {racer['distance']:.1f} mi<br>
                        Geschw.: {racer['speed']:.1f} mph
                        """,
                        tooltip=racer['name'],
                        icon=folium.Icon(color=color, icon=icon)
                    ).add_to(m)
            
            st_folium(m, height=600)
        else:
            st.info("Keine GPS-Daten verfügbar")
    
    with tab3:
        st.subheader("Leistungsstatistiken")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Geschwindigkeitsvergleich
            fig_speed = px.bar(
                df.head(10),
                x='name',
                y='speed',
                title='Top 10 - Aktuelle Geschwindigkeiten',
                labels={'speed': 'Geschwindigkeit (mph)', 'name': 'Fahrer'},
                color='is_fritz',
                color_discrete_map={False: 'lightblue', True: 'gold'}
            )
            fig_speed.update_layout(showlegend=False)
            fig_speed.update_xaxes(tickangle=45)
            st.plotly_chart(fig_speed, use_container_width=True)
        
        with col2:
            # Distanz-Vergleich  
            fig_dist = px.bar(
                df.head(10),
                x='distance',
                y='name',
                orientation='h',
                title='Top 10 - Zurückgelegte Distanz',
                labels={'distance': 'Distanz (Meilen)', 'name': 'Fahrer'},
                color='is_fritz',
                color_discrete_map={False: 'lightblue', True: 'gold'}
            )
            fig_dist.update_layout(showlegend=False)
            st.plotly_chart(fig_dist, use_container_width=True)
        
        # Zusammenfassung
        st.markdown("### 📊 Zusammenfassung")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Teilnehmer", len(df))
        with col2:
            st.metric("Führender", df.iloc[0]['name'])
        with col3:
            st.metric("Ø Geschwindigkeit", f"{df['speed'].mean():.1f} mph")
        with col4:
            st.metric("Max. Distanz", f"{df['distance'].max():.1f} mi")

if __name__ == "__main__":
    main()
