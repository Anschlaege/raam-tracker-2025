"""
RAAM 2025 Live Dashboard - Streamlit Cloud Version
Optimiert für Cloud-Hosting
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import requests
import json
import time
import os
from typing import Dict, List, Optional

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
    .stAlert {
        margin-top: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Datenbank initialisieren
@st.cache_resource
def init_database():
    """Initialisiert die SQLite Datenbank"""
    conn = sqlite3.connect('raam_data.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Tabellen erstellen
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS racers (
            bib_number TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            country TEXT,
            is_fritz_geers BOOLEAN DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            bib_number TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            distance_miles REAL,
            speed_mph REAL,
            elevation_ft INTEGER,
            checkpoint TEXT,
            rank INTEGER,
            time_behind_leader TEXT,
            FOREIGN KEY (bib_number) REFERENCES racers(bib_number)
        )
    ''')
    
    conn.commit()
    return conn

# TrackLeaders API Funktionen
def fetch_trackleaders_data():
    """Holt Daten von TrackLeaders"""
    # Für 2025 anpassen
    endpoints = [
        "https://trackleaders.com/raam24f.php?format=json",  # Testdaten von 2024
        # "https://trackleaders.com/raam25f.php?format=json",  # Für 2025
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, timeout=10)
            if response.status_code == 200:
                return response.json()
        except:
            continue
    
    # Fallback: Demo-Daten
    return create_demo_data()

def create_demo_data():
    """Erstellt Demo-Daten für die Präsentation"""
    demo_racers = [
        {
            'name': 'Fritz Geers',
            'bib': '001',
            'category': 'SOLO',
            'country': 'GER',
            'lat': 39.5,
            'lon': -98.5,
            'distance': 523.4,
            'speed': 15.3,
            'elevation': 4567,
            'checkpoint': 'Great Bend, KS',
            'rank': 3,
            'behind': '+1:23:45'
        },
        {
            'name': 'John Smith',
            'bib': '002',
            'category': 'SOLO',
            'country': 'USA',
            'lat': 39.8,
            'lon': -99.2,
            'distance': 567.8,
            'speed': 16.7,
            'elevation': 4890,
            'checkpoint': 'Dodge City, KS',
            'rank': 1,
            'behind': ''
        },
        {
            'name': 'Maria Garcia',
            'bib': '003',
            'category': 'SOLO',
            'country': 'ESP',
            'lat': 39.3,
            'lon': -98.1,
            'distance': 512.1,
            'speed': 14.9,
            'elevation': 4321,
            'checkpoint': 'Great Bend, KS',
            'rank': 4,
            'behind': '+2:15:30'
        },
        {
            'name': 'Peter Mueller',
            'bib': '004',
            'category': 'SOLO',
            'country': 'GER',
            'lat': 39.7,
            'lon': -99.0,
            'distance': 545.2,
            'speed': 15.8,
            'elevation': 4765,
            'checkpoint': 'Dodge City, KS',
            'rank': 2,
            'behind': '+0:45:20'
        },
        {
            'name': 'Sarah Johnson',
            'bib': '005',
            'category': 'SOLO',
            'country': 'USA',
            'lat': 39.2,
            'lon': -97.8,
            'distance': 498.7,
            'speed': 14.2,
            'elevation': 4123,
            'checkpoint': 'McPherson, KS',
            'rank': 5,
            'behind': '+3:02:15'
        }
    ]
    return demo_racers

# Datenbank-Funktionen
def update_database(conn, data):
    """Aktualisiert die Datenbank mit neuen Daten"""
    cursor = conn.cursor()
    
    for racer in data:
        if racer.get('category', '').upper() != 'SOLO':
            continue
            
        # Fahrer einfügen/aktualisieren
        is_fritz = 1 if 'geers' in racer['name'].lower() or 'fritz' in racer['name'].lower() else 0
        cursor.execute('''
            INSERT OR REPLACE INTO racers (bib_number, name, category, country, is_fritz_geers)
            VALUES (?, ?, ?, ?, ?)
        ''', (racer['bib'], racer['name'], racer['category'], racer.get('country', ''), is_fritz))
        
        # Position einfügen
        cursor.execute('''
            INSERT INTO positions (
                timestamp, bib_number, latitude, longitude, distance_miles,
                speed_mph, elevation_ft, checkpoint, rank, time_behind_leader
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(),
            racer['bib'],
            racer.get('lat'),
            racer.get('lon'),
            racer.get('distance'),
            racer.get('speed'),
            racer.get('elevation'),
            racer.get('checkpoint'),
            racer.get('rank'),
            racer.get('behind')
        ))
    
    conn.commit()

def get_current_standings(conn):
    """Holt aktuelle Rangliste aus der Datenbank"""
    query = """
    SELECT 
        r.name,
        r.bib_number,
        r.country,
        r.is_fritz_geers,
        p.rank,
        p.distance_miles,
        p.speed_mph,
        p.elevation_ft,
        p.checkpoint,
        p.time_behind_leader,
        p.latitude,
        p.longitude,
        p.timestamp
    FROM racers r
    JOIN positions p ON r.bib_number = p.bib_number
    WHERE p.timestamp = (
        SELECT MAX(timestamp) FROM positions WHERE bib_number = r.bib_number
    )
    AND r.category = 'SOLO'
    ORDER BY p.rank
    """
    return pd.read_sql_query(query, conn)

# Hauptanwendung
def main():
    # Datenbank initialisieren
    conn = init_database()
    
    # Sidebar
    st.sidebar.title("🚴 RAAM 2025 Tracker")
    st.sidebar.markdown("---")
    
    # Auto-Refresh
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    if auto_refresh:
        st.empty()  # Placeholder für Timer
    
    # Daten aktualisieren Button
    if st.sidebar.button("🔄 Daten jetzt aktualisieren"):
        with st.spinner("Lade aktuelle Daten..."):
            data = fetch_trackleaders_data()
            update_database(conn, data)
            st.sidebar.success("Daten aktualisiert!")
            st.rerun()
    
    # Info
    st.sidebar.markdown("---")
    st.sidebar.info(
        "**Fritz Geers** wird mit ⭐ und goldenem Hintergrund hervorgehoben.\n\n"
        "Daten werden automatisch alle 60 Sekunden aktualisiert."
    )
    
    # Hauptbereich
    st.title("🏆 Race Across America 2025 - Live Tracking")
    st.markdown(f"*Letzte Aktualisierung: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    # Daten laden
    standings_df = get_current_standings(conn)
    
    if standings_df.empty:
        st.warning("Keine Daten verfügbar. Klicken Sie auf 'Daten jetzt aktualisieren'.")
        # Initial-Daten laden
        data = fetch_trackleaders_data()
        update_database(conn, data)
        st.rerun()
    
    # Fritz Geers Status
    fritz_data = standings_df[standings_df['is_fritz_geers'] == 1]
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        
        st.markdown("### ⭐ Fritz Geers Status")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Position", f"#{int(fritz['rank'])}")
        with col2:
            st.metric("Distanz", f"{fritz['distance_miles']:.1f} mi")
        with col3:
            st.metric("Geschwindigkeit", f"{fritz['speed_mph']:.1f} mph")
        with col4:
            st.metric("Höhe", f"{fritz['elevation_ft']:,} ft")
        with col5:
            st.metric("Rückstand", fritz['time_behind_leader'] or "Führend!")
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🗺️ Live Karte", 
        "📊 Rangliste", 
        "📈 Statistiken",
        "ℹ️ Info"
    ])
    
    with tab1:
        st.subheader("Live Positionen aller Solo-Fahrer")
        
        # Karte
        m = folium.Map(location=[39.0, -98.0], zoom_start=4)
        
        # Route (vereinfacht)
        route_points = [
            [34.0522, -118.2437],  # Los Angeles
            [39.7392, -104.9903],  # Denver
            [39.0997, -94.5786],   # Kansas City
            [38.6270, -90.1994],   # St. Louis
            [39.2904, -76.6122]    # Baltimore
        ]
        
        folium.PolyLine(route_points, color="blue", weight=3, opacity=0.8).add_to(m)
        
        # Fahrer-Positionen
        for _, racer in standings_df.iterrows():
            if pd.notna(racer['latitude']) and pd.notna(racer['longitude']):
                # Fritz hervorheben
                if racer['is_fritz_geers'] == 1:
                    icon_color = 'gold'
                    icon = 'star'
                    prefix = '⭐ '
                else:
                    icon_color = 'blue'
                    icon = 'bicycle'
                    prefix = ''
                
                popup_text = f"""
                <b>{prefix}{racer['name']}</b><br>
                Position: #{int(racer['rank'])}<br>
                Distanz: {racer['distance_miles']:.1f} mi<br>
                Geschw.: {racer['speed_mph']:.1f} mph<br>
                Checkpoint: {racer['checkpoint'] or 'Unterwegs'}
                """
                
                folium.Marker(
                    [racer['latitude'], racer['longitude']],
                    popup=popup_text,
                    tooltip=f"{prefix}{racer['name']} (#{int(racer['rank'])})",
                    icon=folium.Icon(color=icon_color, icon=icon)
                ).add_to(m)
        
        st_folium(m, height=600, width=None)
    
    with tab2:
        st.subheader("📊 Aktuelle Rangliste - Solo Kategorie")
        
        # Rangliste
        display_df = standings_df[[
            'rank', 'name', 'country', 'distance_miles', 'speed_mph', 
            'elevation_ft', 'checkpoint', 'time_behind_leader', 'is_fritz_geers'
        ]].copy()
        
        display_df.columns = [
            'Pos', 'Name', 'Land', 'Distanz (mi)', 'Geschw. (mph)', 
            'Höhe (ft)', 'Checkpoint', 'Rückstand', 'is_fritz'
        ]
        
        # Fritz gelb markieren
        def highlight_fritz(row):
            if row['is_fritz'] == 1:
                return ['background-color: #ffd700'] * len(row)
            return [''] * len(row)
        
        styled_df = display_df.drop('is_fritz', axis=1).style.apply(highlight_fritz, axis=1)
        st.dataframe(styled_df, use_container_width=True, height=600)
        
        # Download
        csv = display_df.drop('is_fritz', axis=1).to_csv(index=False)
        st.download_button(
            label="📥 Rangliste herunterladen",
            data=csv,
            file_name=f"raam_rangliste_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    with tab3:
        st.subheader("📈 Leistungsstatistiken")
        
        # Geschwindigkeitsvergleich
        fig_speed = px.bar(
            standings_df,
            x='name',
            y='speed_mph',
            title='Aktuelle Geschwindigkeiten',
            labels={'speed_mph': 'Geschwindigkeit (mph)', 'name': 'Fahrer'},
            color='is_fritz_geers',
            color_discrete_map={0: 'lightblue', 1: 'gold'}
        )
        fig_speed.update_layout(showlegend=False)
        st.plotly_chart(fig_speed, use_container_width=True)
        
        # Distanz-Vergleich
        fig_dist = px.bar(
            standings_df.sort_values('distance_miles', ascending=True),
            x='distance_miles',
            y='name',
            orientation='h',
            title='Zurückgelegte Distanz',
            labels={'distance_miles': 'Distanz (Meilen)', 'name': 'Fahrer'},
            color='is_fritz_geers',
            color_discrete_map={0: 'lightblue', 1: 'gold'}
        )
        fig_dist.update_layout(showlegend=False)
        st.plotly_chart(fig_dist, use_container_width=True)
    
    with tab4:
        st.subheader("ℹ️ Über diesen Tracker")
        
        st.markdown("""
        ### Race Across America 2025
        
        Das **Race Across America (RAAM)** ist eines der härtesten Radrennen der Welt:
        - 🚴 **Distanz**: ~3.000 Meilen (4.800 km) 
        - 🏔️ **Höhenmeter**: ~52.000 m
        - ⏱️ **Zeitlimit**: 12 Tage
        - 🛣️ **Route**: Kalifornien → Maryland
        
        ### Fritz Geers
        Dieser Tracker folgt besonders **Fritz Geers** aus Deutschland, 
        markiert mit ⭐ und goldenem Hintergrund.
        
        ### Datenquelle
        Live-Daten von [TrackLeaders.com](https://trackleaders.com)
        
        ### Hinweis
        Dies ist aktuell eine Demo mit Beispieldaten. 
        Die echten Live-Daten sind ab Juni 2025 während des Rennens verfügbar.
        """)
    
    # Auto-Refresh
    if auto_refresh:
        time.sleep(60)
        st.rerun()

if __name__ == "__main__":
    main()
