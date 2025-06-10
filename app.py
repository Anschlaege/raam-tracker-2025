"""
RAAM 2025 Live Dashboard - Mit verbesserter Fehlerbehandlung
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime
import requests
import json
from bs4 import BeautifulSoup

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
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    return conn

def create_tables(conn):
    """Erstellt die benötigten Tabellen"""
    cursor = conn.cursor()
    
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

@st.cache_data(ttl=300)  # Cache für 5 Minuten
def fetch_live_data():
    """Holt Live-Daten von TrackLeaders mit verschiedenen Methoden"""
    
    # Debug-Informationen
    debug_info = []
    
    # Methode 1: Direkte JSON API
    urls_to_try = [
        "https://trackleaders.com/raam25f.php?format=json",
        "https://trackleaders.com/raam25.json",
        "https://trackleaders.com/api/v1/race/raam25/leaderboard",
        "https://trackleaders.com/raam25/api/leaderboard.json"
    ]
    
    for url in urls_to_try:
        try:
            debug_info.append(f"Versuche URL: {url}")
            response = requests.get(url, 
                                  timeout=10,
                                  headers={'User-Agent': 'Mozilla/5.0'})
            
            debug_info.append(f"Status Code: {response.status_code}")
            debug_info.append(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
            
            if response.status_code == 200:
                # Versuche als JSON zu parsen
                try:
                    data = response.json()
                    debug_info.append("✓ JSON erfolgreich geparst")
                    return data, debug_info
                except json.JSONDecodeError:
                    debug_info.append("✗ JSON Parse-Fehler")
                    # Vielleicht ist es HTML?
                    if 'html' in response.headers.get('content-type', '').lower():
                        debug_info.append("HTML-Antwort erhalten, versuche zu parsen...")
                        return parse_html_data(response.text), debug_info
        except Exception as e:
            debug_info.append(f"✗ Fehler: {str(e)}")
    
    # Methode 2: HTML Scraping als Fallback
    try:
        debug_info.append("\nVersuche HTML Scraping...")
        response = requests.get("https://trackleaders.com/raam25", 
                              timeout=10,
                              headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            return parse_html_data(response.text), debug_info
    except Exception as e:
        debug_info.append(f"✗ HTML Scraping Fehler: {str(e)}")
    
    return None, debug_info

def parse_html_data(html_content):
    """Parst HTML-Seite nach Tracking-Daten"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Suche nach JavaScript-Variablen mit Tracking-Daten
        scripts = soup.find_all('script')
        for script in scripts:
            text = str(script.string) if script.string else ''
            
            # Suche nach typischen Variablennamen
            import re
            patterns = [
                r'var\s+racers\s*=\s*(\[.*?\]);',
                r'var\s+trackData\s*=\s*(\{.*?\});',
                r'raceData\s*=\s*(\[.*?\]);'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        # Versuche JSON zu parsen
                        data = json.loads(match.group(1))
                        return data
                    except:
                        continue
        
        # Alternative: Suche nach Tabellendaten
        # (implementiere hier weitere Parsing-Logik wenn nötig)
        
    except Exception as e:
        st.error(f"HTML Parsing Fehler: {str(e)}")
    
    return None

def process_live_data(conn, data):
    """Verarbeitet die Live-Daten und aktualisiert die Datenbank"""
    if not data:
        return
    
    cursor = conn.cursor()
    
    # Alle vorherigen Daten löschen
    cursor.execute("DELETE FROM positions")
    cursor.execute("DELETE FROM racers")
    
    # Prüfe ob data eine Liste oder Dict ist
    if isinstance(data, dict):
        # Möglicherweise sind die Daten in einem Unterobjekt
        if 'racers' in data:
            data = data['racers']
        elif 'data' in data:
            data = data['data']
    
    if not isinstance(data, list):
        st.warning("Unerwartetes Datenformat")
        return
    
    # Neue Daten einfügen
    for racer in data:
        if isinstance(racer, dict):
            name = str(racer.get('name', ''))
            bib = str(racer.get('bib', racer.get('number', '')))
            category = str(racer.get('category', racer.get('class', 'SOLO')))
            
            # Nur Solo-Fahrer
            if 'solo' not in category.lower():
                continue
            
            # Fritz Geers identifizieren (verschiedene Schreibweisen)
            is_fritz = 0
            if any(x in name.lower() for x in ['fritz', 'geers', 'gers']):
                is_fritz = 1
                st.sidebar.success(f"Fritz gefunden: {name}")
            
            # Fahrer einfügen
            cursor.execute('''
                INSERT OR REPLACE INTO racers (bib_number, name, category, country, is_fritz_geers)
                VALUES (?, ?, ?, ?, ?)
            ''', (bib, name, category, racer.get('country', ''), is_fritz))
            
            # Position einfügen
            cursor.execute('''
                INSERT INTO positions (
                    timestamp, bib_number, latitude, longitude, distance_miles,
                    speed_mph, elevation_ft, checkpoint, rank, time_behind_leader
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                bib,
                float(racer.get('lat', racer.get('latitude', 0))) if racer.get('lat') or racer.get('latitude') else None,
                float(racer.get('lon', racer.get('lng', racer.get('longitude', 0)))) if racer.get('lon') or racer.get('lng') or racer.get('longitude') else None,
                float(racer.get('distance', racer.get('miles', 0))) if racer.get('distance') or racer.get('miles') else 0,
                float(racer.get('speed', racer.get('mph', 0))) if racer.get('speed') or racer.get('mph') else 0,
                int(racer.get('elevation', racer.get('alt', 0))) if racer.get('elevation') or racer.get('alt') else 0,
                str(racer.get('checkpoint', racer.get('location', ''))),
                int(racer.get('position', racer.get('rank', racer.get('place', 999)))) if racer.get('position') or racer.get('rank') or racer.get('place') else 999,
                str(racer.get('behind', racer.get('gap', '')))
            ))
    
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
    ORDER BY p.rank
    """
    return pd.read_sql_query(query, conn)

# Hauptanwendung
def main():
    # Datenbank initialisieren
    conn = init_connection()
    create_tables(conn)
    
    # Sidebar
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    st.sidebar.markdown("---")
    
    # Debug-Modus
    debug_mode = st.sidebar.checkbox("🔧 Debug-Modus", value=False)
    
    # Refresh Button
    if st.sidebar.button("🔄 Daten aktualisieren"):
        st.cache_data.clear()
        st.rerun()
    
    # Hauptbereich
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    # Live-Daten abrufen
    with st.spinner("Lade Live-Daten..."):
        live_data, debug_info = fetch_live_data()
    
    # Debug-Informationen anzeigen
    if debug_mode:
        with st.expander("🔧 Debug-Informationen"):
            for info in debug_info:
                st.text(info)
            
            if live_data:
                st.success("Daten erfolgreich geladen!")
                st.json(live_data[:3] if isinstance(live_data, list) else live_data)  # Erste 3 Einträge
            else:
                st.error("Keine Daten erhalten")
    
    if live_data:
        # Daten verarbeiten
        process_live_data(conn, live_data)
        
        # Daten laden
        standings_df = get_current_standings(conn)
        
        if standings_df.empty:
            st.warning("Keine Solo-Fahrer in den Daten gefunden.")
            st.info("Aktivieren Sie den Debug-Modus in der Sidebar, um die Rohdaten zu sehen.")
        else:
            st.success(f"✓ {len(standings_df)} Solo-Fahrer gefunden")
            
            # Fritz Geers Status
            fritz_data = standings_df[standings_df['is_fritz_geers'] == 1]
            if not fritz_data.empty:
                fritz = fritz_data.iloc[0]
                
                st.markdown("### ⭐ Fritz Geers Status")
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("Position", f"#{int(fritz['rank'])}" if fritz['rank'] < 999 else "N/A")
                with col2:
                    st.metric("Distanz", f"{fritz['distance_miles']:.1f} mi")
                with col3:
                    st.metric("Geschwindigkeit", f"{fritz['speed_mph']:.1f} mph")
                with col4:
                    st.metric("Höhe", f"{fritz['elevation_ft']:,} ft" if fritz['elevation_ft'] else "N/A")
                with col5:
                    st.metric("Rückstand", fritz['time_behind_leader'] or "N/A")
            else:
                st.warning("⚠️ Fritz Geers nicht gefunden. Prüfen Sie die Fahrerliste unten.")
            
            # Tabs
            tab1, tab2 = st.tabs(["📊 Rangliste", "🗺️ Karte"])
            
            with tab1:
                st.subheader("📊 Aktuelle Rangliste - Solo Kategorie")
                
                # Alle Fahrer anzeigen
                display_df = standings_df[[
                    'rank', 'name', 'bib_number', 'distance_miles', 'speed_mph', 
                    'checkpoint', 'is_fritz_geers'
                ]].copy()
                
                display_df['rank'] = display_df['rank'].apply(lambda x: x if x < 999 else 'N/A')
                
                display_df.columns = [
                    'Pos', 'Name', 'Nr.', 'Distanz (mi)', 'Geschw. (mph)', 
                    'Checkpoint', 'is_fritz'
                ]
                
                # Fritz gelb markieren
                def highlight_fritz(row):
                    if row['is_fritz'] == 1:
                        return ['background-color: #ffd700'] * len(row)
                    return [''] * len(row)
                
                styled_df = display_df.drop('is_fritz', axis=1).style.apply(highlight_fritz, axis=1)
                st.dataframe(styled_df, use_container_width=True, height=600)
            
            with tab2:
                st.subheader("🗺️ Live Positionen")
                
                # Nur Fahrer mit gültigen Koordinaten
                map_df = standings_df[
                    (standings_df['latitude'].notna()) & 
                    (standings_df['longitude'].notna()) &
                    (standings_df['latitude'] != 0)
                ]
                
                if not map_df.empty:
                    m = folium.Map(location=[39.0, -98.0], zoom_start=4)
                    
                    for _, racer in map_df.iterrows():
                        color = 'gold' if racer['is_fritz_geers'] else 'blue'
                        icon = 'star' if racer['is_fritz_geers'] else 'bicycle'
                        
                        folium.Marker(
                            [racer['latitude'], racer['longitude']],
                            popup=f"{racer['name']} - #{racer['rank']}",
                            icon=folium.Icon(color=color, icon=icon)
                        ).add_to(m)
                    
                    st_folium(m, height=500)
                else:
                    st.info("Keine GPS-Koordinaten verfügbar")
    else:
        st.error("❌ Keine Live-Daten verfügbar")
        st.info("""
        **Mögliche Gründe:**
        - Die TrackLeaders API ist temporär nicht erreichbar
        - Das Rennen hat noch nicht begonnen
        - Die URL hat sich geändert
        
        Aktivieren Sie den Debug-Modus in der Sidebar für mehr Informationen.
        """)

if __name__ == "__main__":
    main()
