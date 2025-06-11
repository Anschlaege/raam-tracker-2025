"""
RAAM 2025 Live Dashboard - Version 26 (Steigungs-Berechnung)
- Berechnet die aktuelle Steigung an Fritz' Position mithilfe der GPX-Route.
- Entfernt die sitzungsbasierte Positionsverlaufs-Statistik.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime
import requests
import re
import json
from timezonefinder import TimezoneFinder
from pytz import timezone
import gpxpy
from geopy.distance import great_circle

# --- FUNKTIONEN ---

@st.cache_data(ttl=3600)
def load_and_process_gpx(file_path='raam_route.gpx'):
    """Lädt eine GPX-Datei und extrahiert lat, lon und Höhe für jeden Punkt."""
    try:
        with open(file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)
        
        route_points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    route_points.append({'lat': point.latitude, 'lon': point.longitude, 'ele': point.elevation})

        distance_map = []
        cumulative_distance_miles = 0.0
        if len(route_points) > 1:
            for i in range(len(route_points)):
                point_data = {'dist': cumulative_distance_miles, 'lat': route_points[i]['lat'], 'lon': route_points[i]['lon'], 'ele': route_points[i]['ele']}
                if i > 0:
                    p1 = (route_points[i-1]['lat'], route_points[i-1]['lon'])
                    p2 = (route_points[i]['lat'], route_points[i]['lon'])
                    cumulative_distance_miles += great_circle(p1, p2).miles
                    point_data['dist'] = cumulative_distance_miles
                distance_map.append(point_data)
        return distance_map
    except FileNotFoundError:
        st.error(f"GPX-Datei nicht gefunden! Stelle sicher, dass '{file_path}' im Hauptverzeichnis deiner App liegt.")
        return None
    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der GPX-Datei: {e}")
        return None

def get_current_gradient(current_distance_miles, distance_map):
    """Berechnet die aktuelle Steigung an einem bestimmten Punkt der Route."""
    if not distance_map: return "N/A"
    
    # Finde die zwei Routenpunkte, zwischen denen sich der Fahrer befindet
    p1 = distance_map[0]
    p2 = None
    for point in distance_map:
        if point['dist'] >= current_distance_miles:
            p2 = point
            break
        p1 = point
    
    if p2 is None: return "0.0%" # Am Ende der Route

    # Berechne die Änderung von Höhe und Distanz zwischen den beiden Punkten
    elevation_change = p2['ele'] - p1['ele'] # In Metern
    distance_change = (p2['dist'] - p1['dist']) * 1609.34 # In Meilen, umgerechnet in Meter

    if distance_change == 0:
        return "N/A" # Keine Distanzänderung, Steigung nicht definierbar

    gradient = (elevation_change / distance_change) * 100
    return f"{gradient:+.1f}%"


# (Andere Hilfsfunktionen wie get_local_time, fetch_data etc. bleiben unverändert)
@st.cache_data(ttl=3600)
def get_local_time(lat, lon):
    if lat is None or lon is None: return "N/A"
    try:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lng=lon, lat=lat)
        return datetime.now(timezone(tz_name)).strftime('%H:%M %Z') if tz_name else "N/A"
    except: return "N/A"
    
@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        return parse_js_code_data(response.text)
    except Exception as e:
        st.error(f"Fehler im Datenabruf: {e}")
        return None

def parse_js_code_data(js_content):
    racers = []
    for block in js_content.split('markers.push('):
        try:
            status = re.search(r"\.mystatus\s*=\s*'(.*?)';", block).group(1)
            category = re.search(r"\.mycategory\s*=\s*'(.*?)';", block).group(1)
            if status.lower() != 'active' or category.lower() != 'solo': continue
            lat_lon = re.search(r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\]", block)
            tooltip = re.search(r"bindTooltip\(\"<b>\(([\w\d]+)\)\s*(.*?)<\/b>.*?<br>([\d.]+)\s*mph at route mile ([\d.]+)", block)
            if not all([lat_lon, tooltip]): continue
            racers.append({'lat': float(lat_lon.group(1)), 'lon': float(lat_lon.group(2)), 'bib': tooltip.group(1),'name': tooltip.group(2).strip(), 'speed': float(tooltip.group(3)), 'distance': float(tooltip.group(4)),'category': category, 'position': 999})
        except: continue
    if not racers: return None
    df = pd.DataFrame(racers).sort_values(by='distance', ascending=False).reset_index(drop=True)
    df['position'] = df.index + 1
    return df.to_dict('records')

def create_dataframe(racers_data):
    df = pd.DataFrame(racers_data)
    df['is_fritz'] = (df['bib'] == '675') | (df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True))
    return df.sort_values('position')

def calculate_statistics(df):
    if df.empty or not df['is_fritz'].any(): return df
    # ... (Abstandsberechnung bleibt gleich)
    return df

# --- HAUPTANWENDUNG ---
def main():
    st.set_page_config(page_title="RAAM 2025 Live Tracker - Fritz Geers", page_icon="🚴", layout="wide")
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    if st.sidebar.button("🔄 Jetzt aktualisieren"): st.cache_data.clear(); st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    st.sidebar.markdown("---")
    st.sidebar.info("**Live-Daten** von TrackLeaders\n\n**Fritz Geers** (#675) wird mit ⭐ hervorgehoben")
    
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    distance_map = load_and_process_gpx()
    racers_data = fetch_trackleaders_data()
    
    if not racers_data:
        st.warning("Momentan konnten keine verarbeitbaren Live-Daten gefunden werden."); return

    df = create_dataframe(racers_data)
    df = calculate_statistics(df)
    
    st.success(f"{len(df)} Solo-Fahrer geladen!")
    st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    fritz_data = df[df['is_fritz']]
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        
        # Berechne die neue Metrik
        current_gradient = get_current_gradient(fritz['distance'], distance_map) if distance_map else "N/A"
        
        st.markdown("### ⭐ Fritz Geers Live Status")
        cols = st.columns(6)
        cols[0].metric("Position", f"#{fritz['position']}")
        cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
        cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
        cols[3].metric("Startnummer", f"#{fritz['bib']}")
        cols[4].metric("Lokale Zeit", get_local_time(fritz.get('lat'), fritz.get('lon')))
        cols[5].metric("Steigung", current_gradient) # NEUE METRIK
        
    st.markdown("---")
    # ... Restliche UI (Tabs, Karte, etc.)
    
if __name__ == "__main__":
    main()
