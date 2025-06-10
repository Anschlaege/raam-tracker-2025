"""
RAAM 2025 Live Dashboard - Streamlit Cloud Version
Mit automatischer Datenbank-Initialisierung
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime
import requests
import os

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
</style>
""", unsafe_allow_html=True)

# Datenbank-Funktionen
@st.cache_resource
def init_connection():
    """Erstellt eine neue SQLite Datenbank-Verbindung"""
    conn = sqlite3.connect(':memory:', check_same_thread=False)  # In-Memory DB für Streamlit Cloud
    return conn

def create_tables(conn):
    """Erstellt die benötigten Tabellen"""
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

def insert_demo_data(conn):
    """Fügt Demo-Daten ein"""
    cursor = conn.cursor()
    
    # Demo-Fahrer
    racers = [
        ('001', 'Fritz Geers', 'SOLO', 'GER', 1),
        ('002', 'John Smith', 'SOLO', 'USA', 0),
        ('003', 'Maria Garcia', 'SOLO', 'ESP', 0),
        ('004', 'Peter Mueller', 'SOLO', 'GER', 0),
        ('005', 'Sarah Johnson', 'SOLO', 'USA', 0)
    ]
    
    cursor.executemany(
        'INSERT OR REPLACE INTO racers VALUES (?, ?, ?, ?, ?)', 
        racers
    )
    
    # Demo-Positionen
    positions = [
        (datetime.now(), '001', 39.5, -98.5, 523.4, 15.3, 4567, 'Great Bend, KS', 3, '+1:23:45'),
        (datetime.now(), '002', 39.8, -99.2, 567.8, 16.7, 4890, 'Dodge City, KS', 1, ''),
        (datetime.now(), '003', 39.3, -98.1, 512.1, 14.9, 4321, 'Great Bend, KS', 4, '+2:15:30'),
        (datetime.now(), '004', 39.7, -99.0, 545.2, 15.8, 4765, 'Dodge City, KS', 2, '+0:45:20'),
        (datetime.now(), '005', 39.2, -97.8, 498.7, 14.2, 4123, 'McPherson, KS', 5, '+3:02:15')
    ]
    
    for pos in positions:
        cursor.execute('''
            INSERT INTO positions 
            (timestamp, bib_number, latitude, longitude, distance_miles, 
             speed_mph, elevation_ft, checkpoint, rank, time_behind_leader)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', pos)
    
    conn.commit()

def get_current_standings(conn):
    """Holt aktuelle Rangliste"""
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
    conn = init_connection()
    create_tables(conn)
    
    # Prüfen ob Daten vorhanden sind
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM racers")
    if cursor.fetchone()[0] == 0:
        insert_demo_data(conn)
    
    # Sidebar
    st.sidebar.title("🚴 RAAM 2025 Tracker")
    st.sidebar.markdown("---")
    
    # Info
    st.sidebar.info(
        "**Fritz Geers** wird mit ⭐ und goldenem Hintergrund hervorgehoben.\n\n"
        "Dies ist eine Demo mit Beispieldaten. Die echten Live-Daten sind ab Juni 2025 verfügbar."
    )
    
    # Hauptbereich
    st.title("🏆 Race Across America 2025 - Live Tracking")
    st.markdown(f"*Stand: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    # Daten laden
    try:
        standings_df = get_current_standings(conn)
        
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
            
            # Karte erstellen
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
            
            st_folium(m, height=600)
        
        with tab2:
            st.subheader("📊 Aktuelle Rangliste - Solo Kategorie")
            
            # Rangliste vorbereiten
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
            
            # CSV Download
            csv = display_df.drop('is_fritz', axis=1).to_csv(index=False)
            st.download_button(
                label="📥 Rangliste herunterladen",
                data=csv,
                file_name=f"raam_rangliste_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        with tab3:
            st.subheader("📈 Leistungsstatistiken")
            
            col1, col2 = st.columns(2)
            
            with col1:
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
                fig_speed.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig_speed, use_container_width=True)
            
            with col2:
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
                fig_dist.update_layout(showlegend=False, height=400)
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
            
            ### Status
            🔴 **Demo-Modus**: Sie sehen aktuell Beispieldaten.
            
            🟢 **Ab Juni 2025**: Live-Daten während des Rennens verfügbar.
            
            ### Links
            - [Offizielle RAAM Website](https://www.raceacrossamerica.org)
            - [TrackLeaders](https://trackleaders.com)
            """)
            
            # GitHub Link
            st.markdown("---")
            st.markdown("[📂 Code auf GitHub](https://github.com/IhrUsername/raam-tracker-2025)")
    
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {str(e)}")
        st.info("Die Datenbank wird neu initialisiert...")
        insert_demo_data(conn)
        st.rerun()

if __name__ == "__main__":
    main()
