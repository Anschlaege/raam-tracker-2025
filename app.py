"""
RAAM 2025 Live Dashboard - NUR ECHTE LIVE DATEN
Keine Demo-Daten, nur echte TrackLeaders Daten
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)  # Cache für 1 Minute - häufigere Updates während des Rennens
def fetch_trackleaders_data():
    """Holt Live-Daten von TrackLeaders"""
    
    # TrackLeaders verwendet ein eingebettetes iframe mit den Daten
    # Wir müssen die eingebettete Seite direkt aufrufen
    base_url = "https://trackleaders.com"
    
    # Verschiedene mögliche Endpoints basierend auf früheren RAAM Events
    endpoints = [
        f"{base_url}/raam25f.php",  # Frame-Version
        f"{base_url}/raam25i.php",  # Info-Version
        f"{base_url}/raam25m.php",  # Mobile-Version
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, headers=headers, timeout=15)
            if response.status_code == 200:
                # Parse HTML für JavaScript-Daten
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Suche nach JavaScript mit Tracking-Daten
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string:
                        # TrackLeaders speichert Daten oft in JavaScript-Variablen
                        # Muster für verschiedene Variablennamen
                        patterns = [
                            r'var\s+racers\s*=\s*(\[.*?\]);',
                            r'var\s+riders\s*=\s*(\[.*?\]);',
                            r'var\s+data\s*=\s*(\[.*?\]);',
                            r'trackData\s*=\s*(\[.*?\]);',
                            r'raceData\s*=\s*(\[.*?\]);',
                            r'var\s+markers\s*=\s*(\[.*?\]);'
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, script.string, re.DOTALL)
                            if match:
                                try:
                                    # JavaScript zu JSON konvertieren
                                    json_str = match.group(1)
                                    # Einfache JavaScript zu JSON Konvertierung
                                    json_str = re.sub(r'(\w+):', r'"\1":', json_str)  # Keys in Anführungszeichen
                                    json_str = re.sub(r"'", '"', json_str)  # Single zu Double Quotes
                                    
                                    data = json.loads(json_str)
                                    if data and len(data) > 0:
                                        return parse_trackleaders_data(data)
                                except:
                                    continue
                
                # Alternative: Suche nach Tabellendaten
                tables = soup.find_all('table', class_=['leaderboard', 'racers', 'standings'])
                if tables:
                    return parse_table_data(tables[0])
                    
        except Exception as e:
            st.sidebar.warning(f"Fehler bei {endpoint}: {str(e)}")
            continue
    
    # Wenn nichts funktioniert, zeige Fehlermeldung
    st.error("Konnte keine Live-Daten von TrackLeaders abrufen. Bitte versuchen Sie es später erneut.")
    return None

def parse_trackleaders_data(raw_data):
    """Konvertiert TrackLeaders Rohdaten in einheitliches Format"""
    racers = []
    
    for item in raw_data:
        if isinstance(item, dict):
            # Extrahiere Fahrer-Informationen mit verschiedenen möglichen Feldnamen
            racer = {
                'name': item.get('name', item.get('rider', item.get('racer', ''))),
                'bib': str(item.get('bib', item.get('number', item.get('id', '')))),
                'category': item.get('category', item.get('class', item.get('division', 'SOLO'))),
                'position': int(item.get('position', item.get('rank', item.get('place', 999)))),
                'distance': float(item.get('distance', item.get('miles', item.get('mi', 0)))),
                'speed': float(item.get('speed', item.get('mph', item.get('velocity', 0)))),
                'location': item.get('location', item.get('checkpoint', item.get('loc', ''))),
                'lat': float(item.get('lat', item.get('latitude', 0))),
                'lon': float(item.get('lon', item.get('lng', item.get('longitude', 0)))),
                'time_behind': item.get('behind', item.get('gap', item.get('time_back', ''))),
                'elapsed_time': item.get('elapsed', item.get('time', '')),
                'last_update': item.get('timestamp', item.get('last_seen', ''))
            }
            
            # Nur Solo-Fahrer
            if 'solo' in racer['category'].lower():
                racers.append(racer)
    
    return racers

def parse_table_data(table):
    """Parst HTML-Tabelle falls JavaScript-Daten nicht verfügbar"""
    racers = []
    rows = table.find_all('tr')[1:]  # Skip header
    
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 4:
            racer = {
                'position': int(cols[0].text.strip()) if cols[0].text.strip().isdigit() else 999,
                'name': cols[1].text.strip(),
                'distance': float(cols[2].text.strip()) if cols[2].text.strip().replace('.','').isdigit() else 0,
                'location': cols[3].text.strip() if len(cols) > 3 else '',
                'bib': '',
                'category': 'SOLO',
                'speed': 0,
                'lat': 0,
                'lon': 0,
                'time_behind': '',
                'elapsed_time': '',
                'last_update': ''
            }
            racers.append(racer)
    
    return racers

def create_dataframe(racers_data):
    """Erstellt und bereitet DataFrame vor"""
    if not racers_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(racers_data)
    
    # Fritz Geers identifizieren - verschiedene Schreibweisen berücksichtigen
    df['is_fritz'] = df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True)
    
    # Nach Position sortieren
    df = df.sort_values('position')
    
    # Zeitstempel hinzufügen
    df['data_timestamp'] = datetime.now()
    
    return df

def calculate_statistics(df):
    """Berechnet zusätzliche Statistiken"""
    if df.empty:
        return df
    
    # Führender
    leader = df.iloc[0] if not df.empty else None
    
    # Rückstand zum Führenden berechnen
    if leader is not None and 'distance' in df.columns:
        df['gap_miles'] = leader['distance'] - df['distance']
        df['gap_miles'] = df['gap_miles'].apply(lambda x: f"+{x:.1f}" if x > 0 else "Leader")
    
    return df

# Hauptanwendung
def main():
    # Sidebar
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    st.sidebar.markdown("---")
    
    # Refresh Button
    if st.sidebar.button("🔄 Jetzt aktualisieren"):
        st.cache_data.clear()
        st.rerun()
    
    # Auto-Refresh
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    
    # Info
    st.sidebar.markdown("---")
    st.sidebar.info(
        "**Live-Daten** von TrackLeaders\n\n"
        "**Fritz Geers** wird mit ⭐ hervorgehoben"
    )
    
    # Hauptbereich
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    # Lade Live-Daten
    with st.spinner("Lade Live-Daten von TrackLeaders..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        
        # Zeitstempel
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        if df.empty:
            st.warning("Keine Solo-Fahrer in den Live-Daten gefunden.")
        else:
            # Fritz Geers Status
            fritz_data = df[df['is_fritz']]
            
            if not fritz_data.empty:
                fritz = fritz_data.iloc[0]
                
                st.markdown("### ⭐ Fritz Geers Live Status")
                
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.metric("Position", f"#{fritz['position']}" if fritz['position'] < 999 else "N/A")
                
                with col2:
                    st.metric("Distanz", f"{fritz['distance']:.1f} mi")
                
                with col3:
                    st.metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph" if fritz['speed'] > 0 else "N/A")
                
                with col4:
                    st.metric("Standort", fritz['location'] if fritz['location'] else "Unterwegs")
                
                with col5:
                    st.metric("Rückstand", fritz.get('gap_miles', 'N/A'))
                
                with col6:
                    st.metric("Zeit", fritz['elapsed_time'] if fritz['elapsed_time'] else "N/A")
            else:
                st.warning("⚠️ Fritz Geers wurde in den Live-Daten nicht gefunden. Überprüfen Sie die Schreibweise in der Fahrerliste.")
            
            st.markdown("---")
            
            # Tabs
            tab1, tab2, tab3, tab4 = st.tabs([
                "📊 Live Rangliste", 
                "🗺️ Karte", 
                "📈 Statistiken",
                "📡 Rohdaten"
            ])
            
            with tab1:
                st.subheader("Live Rangliste - Solo Kategorie")
                
                # Rangliste
                display_cols = ['position', 'name', 'distance', 'speed', 'location', 'gap_miles', 'elapsed_time', 'is_fritz']
                display_df = df[display_cols].copy()
                
                display_df.columns = ['Pos', 'Name', 'Distanz (mi)', 'Geschw. (mph)', 'Standort', 'Rückstand', 'Zeit', 'is_fritz']
                
                # Fritz gelb markieren
                def highlight_fritz(row):
                    if row['is_fritz']:
                        return ['background-color: #ffd700'] * len(row)
                    return [''] * len(row)
                
                styled_df = display_df.drop('is_fritz', axis=1).style.apply(highlight_fritz, axis=1)
                
                st.dataframe(styled_df, use_container_width=True, height=600)
                
                # Download
                csv = display_df.drop('is_fritz', axis=1).to_csv(index=False)
                st.download_button(
                    "📥 Download CSV",
                    csv,
                    f"raam_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv"
                )
            
            with tab2:
                st.subheader("Live Positionen auf der Karte")
                
                # Nur Fahrer mit GPS-Koordinaten
                map_df = df[(df['lat'] != 0) & (df['lon'] != 0)]
                
                if not map_df.empty:
                    # Karte zentrieren
                    center_lat = 38.0  # USA Mitte
                    center_lon = -97.0
                    
                    m = folium.Map(location=[center_lat, center_lon], zoom_start=4)
                    
                    # RAAM 2025 Route
                    route_points = [
                        [33.0198, -117.0870],  # Oceanside, CA (Start)
                        [33.4484, -112.0740],  # Phoenix, AZ
                        [34.0522, -106.2437],  # Socorro, NM  
                        [35.0844, -106.6504],  # Albuquerque, NM
                        [35.2828, -101.8338],  # Amarillo, TX
                        [35.4676, -97.5164],   # Oklahoma City, OK
                        [37.6872, -97.3301],   # Wichita, KS
                        [38.8403, -94.6302],   # Kansas City, MO
                        [38.6270, -90.1994],   # St. Louis, MO
                        [39.7684, -86.1581],   # Indianapolis, IN
                        [39.9612, -82.9988],   # Columbus, OH
                        [40.4406, -79.9959],   # Pittsburgh, PA
                        [39.9526, -75.1652],   # Philadelphia, PA
                        [39.7618, -75.4095]    # Middletown, DE (Ziel)
                    ]
                    
                    # Route zeichnen
                    folium.PolyLine(
                        route_points, 
                        color="blue", 
                        weight=3, 
                        opacity=0.7,
                        popup="RAAM 2025 Route"
                    ).add_to(m)
                    
                    # Start und Ziel markieren
                    folium.Marker(
                        route_points[0],
                        popup="START: Oceanside, CA",
                        icon=folium.Icon(color='green', icon='play')
                    ).add_to(m)
                    
                    folium.Marker(
                        route_points[-1],
                        popup="ZIEL: Middletown, DE",
                        icon=folium.Icon(color='red', icon='stop')
                    ).add_to(m)
                    
                    # Fahrer-Positionen
                    for _, racer in map_df.iterrows():
                        color = 'gold' if racer['is_fritz'] else 'blue'
                        icon = 'star' if racer['is_fritz'] else 'bicycle'
                        size = 12 if racer['is_fritz'] else 10
                        
                        popup_html = f"""
                        <div style='font-size: 14px;'>
                        <b>{'⭐ ' if racer['is_fritz'] else ''}{racer['name']}</b><br>
                        Position: #{racer['position']}<br>
                        Distanz: {racer['distance']:.1f} mi<br>
                        Geschw.: {racer['speed']:.1f} mph<br>
                        Standort: {racer['location']}<br>
                        Letztes Update: {racer.get('last_update', 'N/A')}
                        </div>
                        """
                        
                        folium.Marker(
                            [racer['lat'], racer['lon']],
                            popup=folium.Popup(popup_html, max_width=300),
                            tooltip=f"{racer['name']} (#{racer['position']})",
                            icon=folium.Icon(color=color, icon=icon)
                        ).add_to(m)
                    
                    st_folium(m, height=600, width=None, returned_objects=[])
                else:
                    st.info("Keine GPS-Koordinaten in den Live-Daten verfügbar.")
            
            with tab3:
                st.subheader("Live Statistiken")
                
                # Zusammenfassung
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Aktive Fahrer", len(df))
                with col2:
                    st.metric("Führender", df.iloc[0]['name'] if not df.empty else "N/A")
                with col3:
                    avg_speed = df[df['speed'] > 0]['speed'].mean()
                    st.metric("Ø Geschwindigkeit", f"{avg_speed:.1f} mph" if avg_speed > 0 else "N/A")
                with col4:
                    max_dist = df['distance'].max()
                    st.metric("Führung", f"{max_dist:.1f} mi")
                
                st.markdown("---")
                
                # Visualisierungen
                col1, col2 = st.columns(2)
                
                with col1:
                    # Top 10 Geschwindigkeiten
                    top10 = df.nsmallest(10, 'position')
                    fig_speed = px.bar(
                        top10,
                        x='name',
                        y='speed',
                        color='is_fritz',
                        color_discrete_map={False: 'lightblue', True: 'gold'},
                        title='Top 10 - Aktuelle Geschwindigkeiten',
                        labels={'speed': 'Geschwindigkeit (mph)', 'name': ''}
                    )
                    fig_speed.update_layout(showlegend=False, xaxis_tickangle=-45)
                    st.plotly_chart(fig_speed, use_container_width=True)
                
                with col2:
                    # Top 10 Distanzen
                    fig_dist = px.bar(
                        top10,
                        y='name',
                        x='distance',
                        orientation='h',
                        color='is_fritz',
                        color_discrete_map={False: 'lightblue', True: 'gold'},
                        title='Top 10 - Zurückgelegte Distanz',
                        labels={'distance': 'Distanz (Meilen)', 'name': ''}
                    )
                    fig_dist.update_layout(showlegend=False)
                    st.plotly_chart(fig_dist, use_container_width=True)
            
            with tab4:
                st.subheader("Rohdaten von TrackLeaders")
                st.caption("Für Debugging und Analyse")
                
                # Zeige DataFrame
                st.dataframe(df, use_container_width=True)
                
                # JSON Export
                json_data = df.to_dict('records')
                json_str = json.dumps(json_data, indent=2, default=str)
                
                st.download_button(
                    "📥 Download JSON",
                    json_str,
                    f"raam_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    "application/json"
                )
    
    # Auto-Refresh mit Meta-Tag
    if auto_refresh:
        st.markdown(
            '<meta http-equiv="refresh" content="60">',
            unsafe_allow_html=True
        )
        st.sidebar.info("🔄 Nächstes Update in 60 Sekunden...")

if __name__ == "__main__":
    main()
