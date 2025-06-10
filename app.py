"""
RAAM 2025 Live Dashboard - Version 17 (Finale, funktionierende Version)
- Verwendet einen robusten, mehrstufigen Parser, der auf die exakte Datenstruktur zugeschnitten ist.
- Filtert korrekt nur aktive Solo-Fahrer.
- Inklusive Wetterdaten und Discord-Export.
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

# --- FUNKTIONEN ---

@st.cache_data(ttl=600)
def get_weather_data(lat, lon):
    """Ruft aktuelle Wetterdaten für eine gegebene Position von der Open-Meteo API ab."""
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    try:
        api_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,precipitation",
            "temperature_unit": "celsius", "precipitation_unit": "mm"
        }
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        current = data.get('current', {})
        return {
            'temperature': current.get('temperature_2m'),
            'humidity': current.get('relative_humidity_2m'),
            'precipitation': current.get('precipitation')
        }
    except Exception:
        return None

def send_to_discord(webhook_url, df):
    """Formatiert eine Übersicht rund um Fritz und sendet sie an einen Discord-Webhook."""
    if df.empty:
        return {"status": "error", "message": "DataFrame ist leer."}

    fritz_index_list = df[df['is_fritz']].index.tolist()
    if not fritz_index_list:
        display_df = df.head(10)
        title = "RAAM 2025 - Top 10 Update"
    else:
        fritz_pos_index = fritz_index_list[0]
        start_index = max(0, fritz_pos_index - 3)
        end_index = min(len(df), fritz_pos_index + 6)
        display_df = df.iloc[start_index:end_index]
        title = "RAAM 2025 - Update rund um Fritz Geers"

    message_content = f"```\n{title}\n" + "-" * (len(title)) + "\n"
    export_cols = ['position', 'name', 'distance', 'speed', 'gap_to_fritz']
    message_content += display_df[export_cols].to_string(index=False) + "\n```"

    payload = {"content": message_content, "username": "RAAM Live Tracker", "avatar_url": "https://i.imgur.com/4M34hi2.png"}
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        return {"status": "success"} if 200 <= response.status_code < 300 else {"status": "error", "message": f"Discord-Fehler: {response.status_code}"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Netzwerkfehler: {e}"}

@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    """Lädt und parst die mainpoints.js Datei."""
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        return parse_js_code_data(response.text)
    except Exception:
        return None

def parse_js_code_data(js_content):
    """Parst den rohen JavaScript-Inhalt."""
    racers = []
    racer_blocks = js_content.split('markers.push(')
    for block in racer_blocks:
        try:
            status = re.search(r"\.mystatus\s*=\s*'(.*?)';", block).group(1)
            category = re.search(r"\.mycategory\s*=\s*'(.*?)';", block).group(1)
            
            if status.lower() != 'active' or category.lower() != 'solo':
                continue

            lat_lon = re.search(r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\]", block)
            tooltip = re.search(r"bindTooltip\(\"<b>\(([\w\d]+)\)\s*(.*?)<\/b>.*?<br>([\d.]+)\s*mph at route mile ([\d.]+)", block)
            if not all([lat_lon, tooltip]): continue
            
            racers.append({
                'lat': float(lat_lon.group(1)), 'lon': float(lat_lon.group(2)), 'bib': tooltip.group(1),
                'name': tooltip.group(2).strip(), 'speed': float(tooltip.group(3)), 'distance': float(tooltip.group(4)),
                'category': category
            })
        except (AttributeError, ValueError, IndexError):
            continue
            
    if not racers: return None
    df = pd.DataFrame(racers).sort_values(by='distance', ascending=False).reset_index(drop=True)
    df['position'] = df.index + 1
    return df.to_dict('records')

def create_dataframe(racers_data):
    """Erstellt den DataFrame und identifiziert Fritz."""
    df = pd.DataFrame(racers_data)
    df['is_fritz'] = (df['bib'] == '675') | (df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True))
    return df.sort_values('position')

def calculate_statistics(df):
    """Berechnet alle Abstände."""
    if 'is_fritz' not in df.columns or not df['is_fritz'].any():
        return df
        
    fritz = df[df['is_fritz']].iloc[0]
    fritz_pos, fritz_dist, fritz_speed = fritz['position'], fritz['distance'], fritz['speed']

    def format_time_gap(h):
        if pd.isna(h) or h <= 0: return ""
        return f"~{int(h)}h {int((h*60)%60)}m" if h >= 1 else f"~{int(h*60)}m"

    gaps = []
    for _, row in df.iterrows():
        if row['is_fritz']:
            gaps.append("Fritz Geers")
            continue
        gap_mi = row['distance'] - fritz_dist
        if row['position'] < fritz_pos:
            time_h = (gap_mi / fritz_speed) if fritz_speed > 0 else None
            gaps.append(f"+{gap_mi:.1f} mi / {gap_mi*1.60934:.1f} km ({format_time_gap(time_h)})")
        elif row['position'] <= fritz_pos + 5:
            gap_mi_abs = abs(gap_mi)
            time_h = (gap_mi_abs / row['speed']) if row['speed'] > 0 else None
            gaps.append(f"{gap_mi:.1f} mi / {gap_mi*1.60934:.1f} km ({format_time_gap(time_h)})")
        else:
            gaps.append("")
    df['gap_to_fritz'] = gaps
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
    
    racers_data = fetch_trackleaders_data()
    
    if not racers_data:
        st.warning("Momentan konnten keine verarbeitbaren Live-Daten gefunden werden. Versuche es in Kürze erneut.")
        return

    df = create_dataframe(racers_data)
    df = calculate_statistics(df)
    
    st.success(f"{len(df)} Solo-Fahrer erfolgreich geladen!")
    st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    # Discord-Button in der Sidebar
    try:
        webhook_url = st.secrets["DISCORD_WEBHOOK_URL"]
        st.sidebar.markdown("---")
        st.sidebar.header("Export")
        if st.sidebar.button("Update an Discord senden"):
            with st.spinner("Sende an Discord..."):
                result = send_to_discord(webhook_url, df)
                if result.get("status") == "success": st.sidebar.success("Erfolgreich gesendet!")
                else: st.sidebar.error(result.get("message", "Unbekannter Fehler"))
    except KeyError: pass # Secret nicht konfiguriert
        
    fritz_data = df[df['is_fritz']]
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        st.markdown("### ⭐ Fritz Geers Live Status")
        
        cols = st.columns(5)
        cols[0].metric("Position", f"#{fritz['position']}")
        cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
        cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
        cols[3].metric("Startnummer", f"#{fritz['bib']}")
        
        weather_data = get_weather_data(fritz.get('lat'), fritz.get('lon'))
        if weather_data and all(weather_data.values()):
            st.markdown("#### 🌦️ Wetter an seiner Position")
            w_cols = st.columns(3)
            w_cols[0].metric("Temperatur", f"{weather_data['temperature']} °C")
            w_cols[1].metric("Luftfeuchtigkeit", f"{weather_data['humidity']}%")
            w_cols[2].metric("Niederschlag (1h)", f"{weather_data['precipitation']} mm")
            
    st.markdown("---")
    tab1, tab2 = st.tabs(["📊 Live Rangliste", "🗺️ Karte"])
    
    with tab1:
        display_df = df.rename(columns={'position': 'Pos', 'bib': 'Nr.', 'name': 'Name', 'distance': 'Distanz (mi)', 'speed': 'Geschw. (mph)', 'gap_to_fritz': 'Abstand zu Fritz'})
        def highlight_fritz(row): return ['background-color: #ffd700'] * len(row) if row.is_fritz else [''] * len(row)
        st.dataframe(display_df.style.apply(highlight_fritz, axis=1), use_container_width=True, height=800, column_config={"is_fritz": None})

    with tab2:
        map_df = df[df['lat'] != 0]
        if not map_df.empty:
            m = folium.Map(location=[map_df['lat'].mean(), map_df['lon'].mean()], zoom_start=5)
            for _, r in map_df.iterrows():
                folium.Marker([r['lat'], r['lon']], 
                              popup=f"<b>{r['name']}</b><br>Pos: #{r['position']}<br>Dist: {r['distance']:.1f} mi",
                              tooltip=f"#{r['position']} {r['name']}",
                              icon=folium.Icon(color='gold' if r['is_fritz'] else 'blue', icon='star' if r['is_fritz'] else 'bicycle', prefix='fa')).add_to(m)
            st_folium(m, height=600, width=None)

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
