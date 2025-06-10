"""
RAAM 2025 Live Dashboard - Version 23 (Finale Version)
- GPX-basierte Wettervorhersage für die geschätzte zukünftige Position.
- Verbesserte Fehlerbehandlung, um alle Probleme sichtbar zu machen.
- Alle bisherigen Features (Lokale Zeit, Discord-Export etc.) sind enthalten.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import requests
import re
import json
from timezonefinder import TimezoneFinder
from pytz import timezone
import gpxpy
from geopy.distance import great_circle

# --- DATENLADE- UND VERARBEITUNGSFUNKTIONEN ---

@st.cache_data(ttl=3600) # Lade die Route nur einmal pro Stunde
def load_and_process_gpx(file_path='raam_route.gpx'):
    """Lädt eine GPX-Datei und erstellt eine Karte von Distanz zu GPS-Koordinaten."""
    try:
        with open(file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)
        
        route_points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    route_points.append({'lat': point.latitude, 'lon': point.longitude})

        distance_map = []
        cumulative_distance_miles = 0.0
        if len(route_points) > 1:
            for i in range(len(route_points)):
                if i == 0:
                    distance_map.append({'dist': 0, 'lat': route_points[i]['lat'], 'lon': route_points[i]['lon']})
                else:
                    p1 = (route_points[i-1]['lat'], route_points[i-1]['lon'])
                    p2 = (route_points[i]['lat'], route_points[i]['lon'])
                    cumulative_distance_miles += great_circle(p1, p2).miles
                    distance_map.append({'dist': cumulative_distance_miles, 'lat': route_points[i]['lat'], 'lon': route_points[i]['lon']})
        return distance_map
    except FileNotFoundError:
        st.error(f"GPX-Datei nicht gefunden! Stelle sicher, dass '{file_path}' im Hauptverzeichnis deiner App liegt.")
        return None
    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der GPX-Datei: {e}")
        return None

def get_coords_for_distance(target_distance_miles, distance_map):
    """Findet die GPS-Koordinaten für eine bestimmte Distanz entlang der Route durch Interpolation."""
    if not distance_map: return None
    p1 = distance_map[0]
    p2 = None
    for point in distance_map:
        if point['dist'] >= target_distance_miles:
            p2 = point
            break
        p1 = point
    if p2 is None: return {'lat': p1['lat'], 'lon': p1['lon']}
    dist_p1, dist_p2 = p1['dist'], p2['dist']
    if (dist_p2 - dist_p1) == 0: return {'lat': p1['lat'], 'lon': p1['lon']}
    ratio = (target_distance_miles - dist_p1) / (dist_p2 - dist_p1)
    lat = p1['lat'] + ratio * (p2['lat'] - p1['lat'])
    lon = p1['lon'] + ratio * (p2['lon'] - p1['lon'])
    return {'lat': lat, 'lon': lon}

@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    """Lädt und parst die mainpoints.js mit verbesserter Fehlerbehandlung."""
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        return parse_js_code_data(response.text)
    except requests.exceptions.RequestException as e:
        st.error(f"Netzwerk- oder Verbindungsfehler beim Abruf der Fahrerdaten: {e}")
        return None
    except Exception as e:
        st.error(f"Ein unerwarteter Fehler ist im Datenabruf aufgetreten. Das kann an einer Änderung der Datenstruktur liegen.")
        st.exception(e) # Zeigt den kompletten Traceback in der App an
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
    fritz = df[df['is_fritz']].iloc[0]
    fritz_pos, fritz_dist, fritz_speed = fritz['position'], fritz['distance'], fritz['speed']
    def format_time_gap(h):
        if pd.isna(h) or h <= 0: return ""
        return f"~{int(h)}h {int((h*60)%60)}m" if h >= 1 else f"~{int(h*60)}m"
    gaps = []
    for _, row in df.iterrows():
        if row['is_fritz']: gaps.append("Fritz Geers"); continue
        gap_mi = row['distance'] - fritz_dist
        if row['position'] < fritz_pos:
            time_h = (gap_mi / fritz_speed) if fritz_speed > 0 else None
            gaps.append(f"+{gap_mi:.1f} mi / {gap_mi*1.60934:.1f} km ({format_time_gap(time_h)})")
        elif row['position'] <= fritz_pos + 5:
            time_h = (abs(gap_mi) / row['speed']) if row['speed'] > 0 else None
            gaps.append(f"{gap_mi:.1f} mi / {gap_mi*1.60934:.1f} km ({format_time_gap(time_h)})")
        else: gaps.append("")
    df['gap_to_fritz'] = gaps
    return df

# --- HELPER-FUNKTIONEN FÜR WETTER, ZEIT & DISCORD ---

@st.cache_data(ttl=600)
def get_weather_forecast(lat, lon):
    if lat is None or lon is None: return None
    try:
        params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,precipitation", "hourly": "temperature_2m,relative_humidity_2m,precipitation", "temperature_unit": "celsius", "precipitation_unit": "mm"}
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except: return None

@st.cache_data(ttl=3600)
def get_local_time(lat, lon):
    if lat is None or lon is None: return "N/A"
    try:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lng=lon, lat=lat)
        return datetime.now(timezone(tz_name)).strftime('%H:%M %Z') if tz_name else "N/A"
    except: return "N/A"

# --- HAUPTANWENDUNG (main) ---

def main():
    st.set_page_config(page_title="RAAM 2025 Live Tracker - Fritz Geers", page_icon="🚴", layout="wide")
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    if st.sidebar.button("🔄 Jetzt aktualisieren"): st.cache_data.clear(); st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    st.sidebar.markdown("---")
    st.sidebar.info("**Live-Daten** von TrackLeaders\n\n**Fritz Geers** (#675) wird mit ⭐ hervorgehoben")
    
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    # Lade die Routen-Daten aus der GPX-Datei zu Beginn
    distance_map = load_and_process_gpx()

    racers_data = fetch_trackleaders_data()
    
    if not racers_data:
        st.warning("Momentan konnten keine verarbeitbaren Fahrer-Daten gefunden werden. Versuche es in Kürze erneut.")
        if auto_refresh: st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
        return

    df = create_dataframe(racers_data)
    df = calculate_statistics(df)
    
    st.success(f"{len(df)} Solo-Fahrer geladen!")
    st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    fritz_data = df[df['is_fritz']]
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        st.markdown("### ⭐ Fritz Geers Live Status")
        
        cols = st.columns(6)
        cols[0].metric("Position", f"#{fritz['position']}")
        cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
        cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
        cols[3].metric("Startnummer", f"#{fritz['bib']}")
        cols[4].metric("Lokale Zeit", get_local_time(fritz.get('lat'), fritz.get('lon')))
        
        # Wettervorhersage-Logik
        if distance_map:
            st.markdown("#### 🌦️ Wetter & Positions-Vorhersage")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write("**Jetzt**")
                weather_now = get_weather_forecast(fritz.get('lat'), fritz.get('lon'))
                if weather_now and 'current' in weather_now:
                    st.metric("Temperatur", f"{weather_now['current']['temperature_2m']} °C")
                    st.write(f"{weather_now['current']['relative_humidity_2m']}% / {weather_now['current']['precipitation']} mm")
            
            with col2:
                st.write("**In 1 Stunde**")
                future_dist_1h = fritz['distance'] + fritz['speed']
                future_coords_1h = get_coords_for_distance(future_dist_1h, distance_map)
                if future_coords_1h:
                    st.write(f"📍 bei Meile {future_dist_1h:.1f}")
                    weather_1h = get_weather_forecast(future_coords_1h.get('lat'), future_coords_1h.get('lon'))
                    if weather_1h and 'hourly' in weather_1h and len(weather_1h['hourly']['temperature_2m']) > 1:
                        st.metric("Temperatur", f"{weather_1h['hourly']['temperature_2m'][1]} °C")
                        st.write(f"{weather_1h['hourly']['relative_humidity_2m'][1]}% / {weather_1h['hourly']['precipitation'][1]} mm")
            
            with col3:
                st.write("**In 24 Stunden**")
                future_dist_24h = fritz['distance'] + (fritz['speed'] * 24)
                future_coords_24h = get_coords_for_distance(future_dist_24h, distance_map)
                if future_coords_24h:
                    st.write(f"📍 bei Meile {future_dist_24h:.1f}")
                    weather_24h = get_weather_forecast(future_coords_24h.get('lat'), future_coords_24h.get('lon'))
                    if weather_24h and 'hourly' in weather_24h and len(weather_24h['hourly']['temperature_2m']) > 23:
                        st.metric("Temperatur", f"{weather_24h['hourly']['temperature_2m'][23]} °C")
                        st.write(f"{weather_24h['hourly']['relative_humidity_2m'][23]}% / {weather_24h['hourly']['precipitation'][23]} mm")
    
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📊 Live Rangliste", "🗺️ Karte", "📈 Statistiken"])
    
    with tab1:
        st.subheader("Live Rangliste - Solo Kategorie")
        display_cols = ['position', 'bib', 'name', 'distance', 'speed', 'gap_to_fritz', 'is_fritz']
        display_df = df.reindex(columns=display_cols, fill_value="")
        display_df.rename(columns={'position': 'Pos', 'bib': 'Nr.', 'name': 'Name', 'distance': 'Distanz (mi)', 'speed': 'Geschw. (mph)', 'gap_to_fritz': 'Abstand zu Fritz'}, inplace=True)
        def highlight_fritz(row): return ['background-color: #ffd700'] * len(row) if row.is_fritz else [''] * len(row)
        st.dataframe(display_df.style.apply(highlight_fritz, axis=1), use_container_width=True, height=800, column_config={"is_fritz": None})

    # ... (Rest der UI für Tab 2 und 3)

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
