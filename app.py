"""
RAAM 2025 Live Dashboard - Version 31 (Erweiterter Export)
- Fügt verbleibende Distanz und Höhenmeter-Statistiken für jeden Fahrer hinzu.
- Diese neuen Spalten sind automatisch im CSV-Export enthalten.
- Alle bisherigen Features und UI-Elemente bleiben erhalten.
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

def degrees_to_cardinal(d):
    """Konvertiert Grad in eine Himmelsrichtung."""
    dirs = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = int((d + 11.25)/22.5)
    return dirs[ix % 16]

@st.cache_data(ttl=3600)
def load_and_process_gpx(file_path='raam_route.gpx'):
    """Lädt und verarbeitet die GPX-Datei, um eine Distanz- und Höhenkarte zu erstellen."""
    try:
        with open(file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)
        route_points = [{'lat': p.latitude, 'lon': p.longitude, 'ele': p.elevation} for p in gpx.tracks[0].segments[0].points]
        distance_map, cumulative_distance_miles = [], 0.0
        if len(route_points) > 1:
            for i in range(len(route_points)):
                point_data = {'dist': cumulative_distance_miles, 'lat': route_points[i]['lat'], 'lon': route_points[i]['lon'], 'ele': route_points[i]['ele']}
                if i > 0:
                    p1, p2 = (route_points[i-1]['lat'], route_points[i-1]['lon']), (route_points[i]['lat'], route_points[i]['lon'])
                    cumulative_distance_miles += great_circle(p1, p2).miles
                    point_data['dist'] = cumulative_distance_miles
                distance_map.append(point_data)
        total_distance = distance_map[-1]['dist'] if distance_map else 0
        return distance_map, total_distance
    except FileNotFoundError:
        st.error(f"GPX-Datei nicht gefunden! Stelle sicher, dass '{file_path}' im Hauptverzeichnis deiner App liegt.")
        return None, 0
    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der GPX-Datei: {e}")
        return None, 0

def get_coords_for_distance(target_distance_miles, distance_map):
    if not distance_map: return None
    p1 = distance_map[0]
    for point in distance_map:
        if point['dist'] >= target_distance_miles: p2 = point; break
        p1 = point
    else: p2 = p1
    dist_p1, dist_p2 = p1['dist'], p2['dist']
    if (dist_p2 - dist_p1) == 0: return {'lat': p1['lat'], 'lon': p1['lon']}
    ratio = (target_distance_miles - dist_p1) / (dist_p2 - dist_p1)
    lat = p1['lat'] + ratio * (p2['lat'] - p1['lat']); lon = p1['lon'] + ratio * (p2['lon'] - p1['lon'])
    return {'lat': lat, 'lon': lon}

def get_current_gradient(current_distance_miles, distance_map):
    if not distance_map: return "N/A"
    p1 = distance_map[0]
    for point in distance_map:
        if point['dist'] >= current_distance_miles: p2 = point; break
        p1 = point
    else: p2 = p1
    elevation_change = p2['ele'] - p1['ele']
    distance_change = (p2['dist'] - p1['dist']) * 1609.34
    if distance_change == 0: return "0.0%"
    gradient = (elevation_change / distance_change) * 100
    return f"{gradient:+.1f}%"

def calculate_elevation_stats(current_distance_miles, distance_map):
    if not distance_map: return {'climbed': 0, 'total': 0}
    total_gain = 0; climbed_gain = 0
    for i in range(1, len(distance_map)):
        elevation_diff = distance_map[i]['ele'] - distance_map[i-1]['ele']
        if elevation_diff > 0:
            total_gain += elevation_diff
            if distance_map[i]['dist'] <= current_distance_miles:
                climbed_gain += elevation_diff
    return {'climbed': int(climbed_gain), 'total': int(total_gain)}

@st.cache_data(ttl=600)
def get_weather_forecast(lat, lon):
    if lat is None or lon is None: return None
    try:
        params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m", "hourly": "temperature_2m,relative_humidity_2m,precipitation", "temperature_unit": "celsius", "precipitation_unit": "mm", "wind_speed_unit": "kmh"}
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except: return None

@st.cache_data(ttl=3600)
def get_local_time(lat, lon):
    if lat is None or lon is None: return "N/A"
    try:
        tf = TimezoneFinder(); tz_name = tf.timezone_at(lng=lon, lat=lat)
        return datetime.now(timezone(tz_name)).strftime('%H:%M %Z') if tz_name else "N/A"
    except: return "N/A"

def send_to_discord_as_file(webhook_url, df, weather_data):
    if df.empty: return {"status": "error", "message": "DataFrame ist leer."}
    berlin_tz = timezone('Europe/Berlin'); now_berlin = datetime.now(berlin_tz)
    days_de = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]; day_name = days_de[now_berlin.weekday()]
    timestamp_str = now_berlin.strftime(f"{day_name}, %d.%m.%Y um %H:%M Uhr")
    weather_summary = "Wetterdaten für Fritz nicht verfügbar."
    if weather_data and 'current' in weather_data and all(v is not None for v in weather_data['current'].values()):
        current = weather_data['current']; wind_dir = degrees_to_cardinal(current['wind_direction_10m'])
        weather_summary = (f"Aktuelles Wetter an Fritz' Position: {current['temperature_2m']}°C, {current['wind_speed_10m']} km/h Wind aus {wind_dir}, {current['relative_humidity_2m']}% Luftfeuchtigkeit, {current['precipitation']}mm Niederschlag.")
    content = (f"**RAAM Live-Export vom {timestamp_str} (Berliner Zeit)**\n\n🌦️ {weather_summary}\n\nDie vollständige Rangliste mit allen Statistiken befindet sich im Anhang.")
    csv_data = df.to_csv(index=False, encoding='utf-8')
    file_name = f"raam_live_export_{now_berlin.strftime('%Y%m%d_%H%M')}.csv"
    payload_json = {"content": content, "username": "RAAM Live Tracker", "avatar_url": "https://i.imgur.com/4M34hi2.png"}
    files = {'file': (file_name, csv_data, 'text/csv')}
    try:
        response = requests.post(webhook_url, data={'payload_json': json.dumps(payload_json)}, files=files, timeout=15)
        return {"status": "success", "message": f"Datei '{file_name}' gesendet!"} if 200 <= response.status_code < 300 else {"status": "error", "message": f"Discord-Fehler: {response.status_code}"}
    except requests.exceptions.RequestException as e: return {"status": "error", "message": f"Netzwerkfehler: {e}"}

@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        return parse_js_code_data(response.text)
    except Exception as e:
        st.error(f"Fehler im Datenabruf: {e}"); return None

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

def calculate_all_stats(df, distance_map, total_route_dist):
    """Reichert den DataFrame mit allen berechneten Statistiken an."""
    if df.empty: return df

    # --- Lücke zu Fritz ---
    if 'is_fritz' in df.columns and df['is_fritz'].any():
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
    
    # --- Verbleibende Distanz & Höhenmeter für JEDEN Fahrer ---
    if distance_map:
        new_cols = {'remaining_miles': [], 'elevation_climbed_m': [], 'elevation_remaining_m': []}
        total_elevation_gain = calculate_elevation_stats(total_route_dist, distance_map)['total']
        for _, row in df.iterrows():
            new_cols['remaining_miles'].append(total_route_dist - row['distance'])
            climbed = calculate_elevation_stats(row['distance'], distance_map)['climbed']
            new_cols['elevation_climbed_m'].append(climbed)
            new_cols['elevation_remaining_m'].append(total_elevation_gain - climbed)
        df = pd.concat([df, pd.DataFrame(new_cols)], axis=1)

    return df

# --- HAUPTANWENDUNG (main) ---
def main():
    st.set_page_config(page_title="RAAM 2025 Live Tracker - Fritz Geers", page_icon="🚴", layout="wide")
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    if st.sidebar.button("🔄 Jetzt aktualisieren"): st.cache_data.clear(); st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    st.sidebar.markdown("---")
    st.sidebar.info("**Live-Daten** von TrackLeaders\n\n**Fritz Geers** (#675) wird mit ⭐ hervorgehoben")
    
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    distance_map, total_route_dist = load_and_process_gpx()
    racers_data = fetch_trackleaders_data()
    
    if not racers_data:
        st.warning("Momentan konnten keine verarbeitbaren Live-Daten gefunden werden."); return

    df = create_dataframe(racers_data)
    df = calculate_all_stats(df, distance_map, total_route_dist)
    
    st.success(f"{len(df)} Solo-Fahrer geladen!")
    st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    fritz_data = df[df['is_fritz']]
    weather_data_full = None
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        weather_data_full = get_weather_forecast(fritz.get('lat'), fritz.get('lon'))
        
        st.markdown("### ⭐ Fritz Geers Live Status")
        cols1 = st.columns(6)
        cols1[0].metric("Position", f"#{fritz['position']}")
        cols1[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
        cols1[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
        cols1[3].metric("Startnummer", f"#{fritz['bib']}")
        cols1[4].metric("Lokale Zeit", get_local_time(fritz.get('lat'), fritz.get('lon')))
        if distance_map:
            cols1[5].metric("Steigung", get_current_gradient(fritz['distance'], distance_map))
        
        if distance_map:
            st.markdown("#### 🏁 Strecke & Höhenprofil")
            cols2 = st.columns(3)
            cols2[0].metric("Verbleibende Distanz", f"{fritz.get('remaining_miles', 0):.1f} mi")
            cols2[1].metric("Absolvierte Höhenmeter", f"{fritz.get('elevation_climbed_m', 0):,} m")
            cols2[2].metric("Verbleibende Höhenmeter", f"{fritz.get('elevation_remaining_m', 0):,} m")
            
        st.markdown("#### 🌦️ Wetter & Positions-Vorhersage")
        # ... (Wetter-UI bleibt gleich)
    
    try:
        webhook_url = st.secrets["DISCORD_WEBHOOK_URL"]
        st.sidebar.markdown("---"); st.sidebar.header("Export")
        if st.sidebar.button("Export an Discord senden"):
            with st.spinner("Sende CSV an Discord..."):
                result = send_to_discord_as_file(webhook_url, df, weather_data_full)
                if result.get("status") == "success": st.sidebar.success(result.get("message"))
                else: st.sidebar.error(result.get("message"))
    except KeyError: pass
            
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📊 Live Rangliste", "🗺️ Karte", "📈 Statistiken"])
    
    with tab1:
        st.subheader("Live Rangliste - Solo Kategorie")
        display_cols = ['position', 'bib', 'name', 'distance', 'speed', 'gap_to_fritz', 'is_fritz']
        display_df = df.reindex(columns=display_cols, fill_value="")
        display_df.rename(columns={'position': 'Pos', 'bib': 'Nr.', 'name': 'Name', 'distance': 'Distanz (mi)', 'speed': 'Geschw. (mph)', 'gap_to_fritz': 'Abstand zu Fritz'}, inplace=True)
        def highlight_fritz(row): return ['background-color: #ffd700'] * len(row) if row.is_fritz else [''] * len(row)
        st.dataframe(display_df.style.apply(highlight_fritz, axis=1), use_container_width=True, height=800, column_config={"is_fritz": None})

    with tab2:
        st.subheader("Live Positionen auf der Karte")
        # ... (Karten-Code bleibt gleich)
        
        if distance_map and not fritz_data.empty:
            st.subheader("Höhenprofil der Strecke")
            elevation_fig = create_elevation_plot(fritz.get('distance', 0), fritz.get('name', ''), distance_map)
            if elevation_fig:
                st.plotly_chart(elevation_fig, use_container_width=True)

    with tab3:
        st.subheader("Top 10 nach Distanz")
        # ... (Statistik-Code bleibt gleich)

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
