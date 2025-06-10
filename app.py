"""
RAAM 2025 Live Dashboard - Version 23 (GPX-basierte Wettervorhersage)
- Nutzt eine GPX-Datei der Route, um zukünftige Positionen zu schätzen.
- Zeigt die Wettervorhersage für diese geschätzten zukünftigen Positionen an.
- Benötigt: gpxpy, geopy, pytz, timezonefinder
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

# --- FUNKTIONEN ---

@st.cache_data(ttl=3600) # Cache die Route für eine Stunde
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

        # Berechne die kumulative Distanz für jeden Punkt in Meilen
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
        st.error(f"GPX-Datei nicht gefunden! Stelle sicher, dass 'raam_route.gpx' im Hauptverzeichnis deiner App liegt.")
        return None
    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der GPX-Datei: {e}")
        return None

def get_coords_for_distance(target_distance_miles, distance_map):
    """Findet die GPS-Koordinaten für eine bestimmte Distanz entlang der Route."""
    if not distance_map: return None

    # Finde die zwei Punkte, die die Zieldistanz umklammern
    p1 = distance_map[0]
    p2 = None
    for point in distance_map:
        if point['dist'] >= target_distance_miles:
            p2 = point
            break
        p1 = point
    
    if p2 is None: return {'lat': p1['lat'], 'lon': p1['lon']} # Am Ende der Route

    # Interpoliere zwischen p1 und p2
    dist_p1 = p1['dist']
    dist_p2 = p2['dist']
    if (dist_p2 - dist_p1) == 0: return {'lat': p1['lat'], 'lon': p1['lon']}

    ratio = (target_distance_miles - dist_p1) / (dist_p2 - dist_p1)
    lat = p1['lat'] + ratio * (p2['lat'] - p1['lat'])
    lon = p1['lon'] + ratio * (p2['lon'] - p1['lon'])
    return {'lat': lat, 'lon': lon}

# (Andere Hilfsfunktionen bleiben unverändert)
@st.cache_data(ttl=600)
def get_weather_forecast(lat, lon):
    if lat is None or lon is None: return None
    try:
        params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,precipitation","hourly": "temperature_2m,relative_humidity_2m,precipitation","temperature_unit": "celsius", "precipitation_unit": "mm"}
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        weather = {'current': data.get('current'), 'hourly': data.get('hourly')}
        return weather
    except: return None
    
@st.cache_data(ttl=600)
def get_local_time(lat, lon):
    if lat is None or lon is None: return "N/A"
    try:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lng=lon, lat=lat)
        return datetime.now(timezone(tz_name)).strftime('%H:%M %Z') if tz_name else "N/A"
    except: return "N/A"

# --- HAUPTANWENDUNG ---
def main():
    st.set_page_config(page_title="RAAM 2025 Live Tracker - Fritz Geers", page_icon="🚴", layout="wide")
    
    # Lade die Routen-Daten aus der GPX-Datei
    distance_map = load_and_process_gpx()

    # (UI und restliche Logik...)
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    if st.sidebar.button("🔄 Jetzt aktualisieren"): st.cache_data.clear(); st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    st.title("🏆 Race Across America 2025 - Live Tracking")

    racers_data = fetch_trackleaders_data()
    
    if not racers_data:
        st.warning("Momentan konnten keine verarbeitbaren Live-Daten gefunden werden."); return

    df = create_dataframe(racers_data)
    df = calculate_statistics(df)
    st.success(f"{len(df)} Solo-Fahrer geladen!")
    
    fritz_data = df[df['is_fritz']]
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        st.markdown("### ⭐ Fritz Geers Live Status")
        # (Status-Metriken...)

        # --- WETTERVORHERSAGE-LOGIK ---
        if distance_map: # Nur ausführen, wenn die GPX-Route geladen wurde
            st.markdown("#### 🌦️ Wetter & Positions-Vorhersage")
            col1, col2, col3 = st.columns(3)
            
            # JETZT
            with col1:
                st.write("**Jetzt**")
                weather_now = get_weather_forecast(fritz.get('lat'), fritz.get('lon'))
                if weather_now and weather_now.get('current'):
                    st.metric("Temperatur", f"{weather_now['current']['temperature_2m']} °C")
                    st.write(f"{weather_now['current']['relative_humidity_2m']}% / {weather_now['current']['precipitation']} mm")
                else:
                    st.write("Wetterdaten nicht verfügbar.")

            # IN 1 STUNDE
            with col2:
                st.write("**In 1 Stunde**")
                future_dist_1h = fritz['distance'] + fritz['speed']
                future_coords_1h = get_coords_for_distance(future_dist_1h, distance_map)
                st.write(f"📍 bei Meile {future_dist_1h:.1f}")
                weather_1h = get_weather_forecast(future_coords_1h.get('lat'), future_coords_1h.get('lon'))
                if weather_1h and weather_1h.get('hourly'):
                    # Nimm den ersten stündlichen Wert als Annäherung
                    st.metric("Temperatur", f"{weather_1h['hourly']['temperature_2m'][1]} °C")
                    st.write(f"{weather_1h['hourly']['relative_humidity_2m'][1]}% / {weather_1h['hourly']['precipitation'][1]} mm")
                else:
                    st.write("Vorhersage nicht verfügbar.")

            # IN 24 STUNDEN
            with col3:
                st.write("**In 24 Stunden**")
                future_dist_24h = fritz['distance'] + (fritz['speed'] * 24)
                future_coords_24h = get_coords_for_distance(future_dist_24h, distance_map)
                st.write(f"📍 bei Meile {future_dist_24h:.1f}")
                weather_24h = get_weather_forecast(future_coords_24h.get('lat'), future_coords_24h.get('lon'))
                if weather_24h and len(weather_24h.get('hourly', {}).get('temperature_2m', [])) > 23:
                    st.metric("Temperatur", f"{weather_24h['hourly']['temperature_2m'][23]} °C")
                    st.write(f"{weather_24h['hourly']['relative_humidity_2m'][23]}% / {weather_24h['hourly']['precipitation'][23]} mm")
                else:
                    st.write("Vorhersage nicht verfügbar.")

    # (Rest der UI: Tabs, Tabelle, Karte, etc. unverändert)
    # ...

if __name__ == "__main__":
    main() # Ruft die Hauptfunktion mit der gesamten Logik auf
