"""
RAAM 2025 Live Dashboard - Echte Live-Daten
Verfolgt alle Solo-Fahrer mit Fokus auf Fritz Geers
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
    """Holt Live-Daten von TrackLeaders"""
    try:
        response = requests.get('https://trackleaders.com/raam25f.php?format=json', timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Fehler beim Abrufen der Daten: Status {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Verbindungsfehler: {str(e)}")
        return None

def process_live_data(conn, data):
    """Verarbeitet die Live-Daten und aktualisiert die Datenbank"""
    if not data:
        return
    
    cursor = conn.cursor()
    
    # Alle vorherigen Daten löschen für frische Updates
    cursor.execute("DELETE FROM positions")
    cursor.execute("DELETE FROM racers")
    
    # Neue Daten einfügen
    for racer in data:
        if isinstance(racer, dict):
            # Fahrer-Informationen extrahieren
            name = racer.get('name', '')
            bib = racer.get('bib', '')
            category = racer.get('category', 'SOLO')
            
            # Nur Solo-Fahrer
            if category.upper() != 'SOLO':
                continue
            
            # Fritz Geers identifizieren
            is_fritz = 1 if ('geers' in name.lower() or 'fritz' in name.lower()) else 0
            
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
                float(racer.get('lat', 0)) if racer.get('lat') else None,
                float(racer.get('lon', 0)) if racer.get('lon') else None,
                float(racer.get('distance', 0)) if racer.get('distance') else 0,
                float(racer.get('speed', 0)) if racer.get('speed') else 0,
                int(racer.get('elevation', 0)) if racer.get('elevation') else 0,
                racer.get('checkpoint', ''),
                int(racer.get('position', 999)) if racer.get('position') else 999,
                racer.get('behind', '')
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
    WHERE r.category = 'SOLO'
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
    
    # Refresh Button
    if st.sidebar.button("🔄 Daten aktualisieren"):
        st.cache_data.clear()
        st.rerun()
    
    # Auto-Refresh
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (alle 5 Min)", value=True)
    
    # Info
    st.sidebar.markdown("---")
    st.sidebar.info(
        "**Fritz Geers** wird mit ⭐ und goldenem Hintergrund hervorgehoben.\n\n"
        "Live-Daten von TrackLeaders.com"
    )
    
    # Hauptbereich
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    # Live-Daten abrufen
    with st.spinner("Lade Live-Daten..."):
        live_data = fetch_live_data()
        
    if live_data:
        # Daten verarbeiten
        process_live_data(conn, live_data)
        
        # Aktualisierungszeit anzeigen
        st.markdown(f"*Letzte Aktualisierung: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        # Daten laden
        standings_df = get_current_standings(conn)
        
        if standings_df.empty:
            st.warning("Keine Solo-Fahrer in den Live-Daten gefunden.")
        else:
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
                st.warning("Fritz Geers nicht in den Daten gefunden. Prüfen Sie die Schreibweise in den Live-Daten.")
            
            st.markdown("---")
            
            # Tabs
            tab1, tab2, tab3, tab4 = st.tabs([
                "🗺️ Live Karte", 
                "📊 Rangliste", 
                "📈 Statistiken",
                "📊 Rohdaten"
            ])
            
            with tab1:
                st.subheader("Live Positionen aller Solo-Fahrer")
                
                # Karte erstellen
                # Zentrum der USA
                m = folium.Map(location=[39.0, -98.0], zoom_start=4)
                
                # RAAM Route (grobe Annäherung)
                route_points = [
                    [33.4484, -112.0740],  # Phoenix, AZ (Start)
                    [35.0844, -106.6504],  # Albuquerque, NM
                    [35.4676, -97.5164],   # Oklahoma City, OK
                    [38.6270, -90.1994],   # St. Louis, MO
                    [39.7684, -86.1581],   # Indianapolis, IN
                    [40.4406, -79.9959],   # Pittsburgh, PA
                    [39.2904, -76.6122]    # Baltimore, MD (Ziel)
                ]
                
                folium.PolyLine(route_points, color="blue", weight=3, opacity=0.6).add_to(m)
                
                # Fahrer-Positionen
                for _, racer in standings_df.iterrows():
                    if pd.notna(racer['latitude']) and pd.notna(racer['longitude']) and racer['latitude'] != 0:
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
                    'checkpoint', 'time_behind_leader', 'is_fritz_geers'
                ]].copy()
                
                # Sortieren und ungültige Ränge ans Ende
                display_df = display_df.sort_values('rank')
                display_df['rank'] = display_df['rank'].apply(lambda x: x if x < 999 else 'N/A')
                
                display_df.columns = [
                    'Pos', 'Name', 'Land', 'Distanz (mi)', 'Geschw. (mph)', 
                    'Checkpoint', 'Rückstand', 'is_fritz'
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
                    label="📥 Rangliste herunterladen (CSV)",
                    data=csv,
                    file_name=f"raam_rangliste_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with tab3:
                st.subheader("📈 Leistungsstatistiken")
                
                # Nur Fahrer mit gültigen Positionen für Statistiken
                valid_df = standings_df[standings_df['rank'] < 999]
                
                if not valid_df.empty:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Geschwindigkeitsvergleich
                        fig_speed = px.bar(
                            valid_df.head(10),  # Top 10
                            x='name',
                            y='speed_mph',
                            title='Top 10 - Aktuelle Geschwindigkeiten',
                            labels={'speed_mph': 'Geschwindigkeit (mph)', 'name': 'Fahrer'},
                            color='is_fritz_geers',
                            color_discrete_map={0: 'lightblue', 1: 'gold'}
                        )
                        fig_speed.update_layout(showlegend=False, height=400)
                        fig_speed.update_xaxes(tickangle=45)
                        st.plotly_chart(fig_speed, use_container_width=True)
                    
                    with col2:
                        # Distanz-Vergleich
                        fig_dist = px.bar(
                            valid_df.head(10).sort_values('distance_miles', ascending=True),
                            x='distance_miles',
                            y='name',
                            orientation='h',
                            title='Top 10 - Zurückgelegte Distanz',
                            labels={'distance_miles': 'Distanz (Meilen)', 'name': 'Fahrer'},
                            color='is_fritz_geers',
                            color_discrete_map={0: 'lightblue', 1: 'gold'}
                        )
                        fig_dist.update_layout(showlegend=False, height=400)
                        st.plotly_chart(fig_dist, use_container_width=True)
                    
                    # Gesamtstatistiken
                    st.markdown("### 📊 Gesamtstatistiken")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Fahrer im Rennen", len(valid_df))
                    with col2:
                        st.metric("Ø Geschwindigkeit", f"{valid_df['speed_mph'].mean():.1f} mph")
                    with col3:
                        st.metric("Führender", valid_df.iloc[0]['name'] if not valid_df.empty else "N/A")
                    with col4:
                        st.metric("Ø Distanz", f"{valid_df['distance_miles'].mean():.1f} mi")
                else:
                    st.info("Noch keine gültigen Positionsdaten verfügbar.")
            
            with tab4:
                st.subheader("📊 Rohdaten")
                st.caption("Direkter Einblick in die API-Daten")
                
                # Rohdaten anzeigen
                if live_data:
                    # Als DataFrame für bessere Darstellung
                    raw_df = pd.DataFrame(live_data)
                    st.dataframe(raw_df, use_container_width=True, height=400)
                    
                    # JSON Download
                    json_str = json.dumps(live_data, indent=2)
                    st.download_button(
                        label="📥 Rohdaten herunterladen (JSON)",
                        data=json_str,
                        file_name=f"raam_raw_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
    else:
        st.error("Keine Live-Daten verfügbar. Bitte versuchen Sie es später erneut.")
    
    # Auto-Refresh
    if auto_refresh:
        st.markdown("---")
        st.info("🔄 Auto-Refresh ist aktiviert. Die Seite aktualisiert sich alle 5 Minuten.")
        st.markdown("<meta http-equiv='refresh' content='300'>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
