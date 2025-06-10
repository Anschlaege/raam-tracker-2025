"""
RAAM 2025 Live Dashboard - Version 19 (Wetter-Diagnose)
- Enthält detaillierte Log-Ausgaben in der App, um den Wetter-Abruf zu debuggen.
- Robustere Anzeigelogik für Wetterdaten.
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

@st.cache_data(ttl=600) # Cache für 10 Minuten
def get_weather_data(lat, lon):
    """Ruft aktuelle Wetterdaten ab und gibt detailliertes Feedback in die App aus."""
    st.info(f"🌦️ Starte Wetter-Abruf für Lat: {lat}, Lon: {lon}")
    if lat is None or lon is None or (lat == 0 and lon == 0):
        st.warning("Wetter-Abruf übersprungen: Ungültige oder fehlende GPS-Koordinaten.")
        return None
    try:
        api_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,precipitation",
            "temperature_unit": "celsius", "precipitation_unit": "mm"
        }
        # Erstelle die volle URL für Debugging-Zwecke
        full_url = requests.Request('GET', api_url, params=params).prepare().url
        st.info(f"Rufe Wetter-API auf: {full_url}")

        response = requests.get(api_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        st.success("Antwort von Wetter-API erhalten!")
        st.json(data) # ZEIGE DIE KOMPLETTE ANTWORT ZUR ANALYSE AN

        current = data.get('current', {})
        return {
            'temperature': current.get('temperature_2m'),
            'humidity': current.get('relative_humidity_2m'),
            'precipitation': current.get('precipitation')
        }
    except requests.exceptions.HTTPError as e:
        st.error(f"Wetter-API HTTP-Fehler: Status {e.response.status_code}. Die API ist möglicherweise nicht erreichbar.")
        return None
    except Exception as e:
        st.error(f"Allgemeiner Fehler im Wetter-Abruf: {e}")
        return None

# (Die anderen Funktionen von fetch_trackleaders_data bis calculate_statistics bleiben unverändert)
@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        return parse_js_code_data(response.text)
    except Exception: return None

def parse_js_code_data(js_content):
    racers = []
    racer_blocks = js_content.split('markers.push(')
    for block in racer_blocks:
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
    if df.empty or 'is_fritz' not in df.columns or not df['is_fritz'].any(): return df
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

# --- HAUPTANWENDUNG ---
def main():
    st.set_page_config(page_title="RAAM 2025 Live Tracker - Fritz Geers", page_icon="🚴", layout="wide")
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    if st.sidebar.button("🔄 Jetzt aktualisieren"): st.cache_data.clear(); st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    racers_data = fetch_trackleaders_data()
    if not racers_data:
        st.warning("Keine verarbeitbaren Fahrer-Daten gefunden. Die Seite wird automatisch neu geladen.")
        if auto_refresh: st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
        return

    df = create_dataframe(racers_data)
    df = calculate_statistics(df)
    
    st.success(f"{len(df)} Solo-Fahrer geladen!")
    
    fritz_data = df[df['is_fritz']]
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        st.markdown("### ⭐ Fritz Geers Live Status")
        # ... (Anzeige für Fritz' Status) ...
        
        # --- WETTER-ABRUF UND ANZEIGE MIT DIAGNOSE ---
        weather_data = get_weather_data(fritz.get('lat'), fritz.get('lon'))
        
        if weather_data:
            st.markdown("#### 🌦️ Wetter an seiner Position")
            w_cols = st.columns(3)
            temp = weather_data.get('temperature')
            hum = weather_data.get('humidity')
            precip = weather_data.get('precipitation')
            w_cols[0].metric("Temperatur", f"{temp} °C" if temp is not None else "N/A")
            w_cols[1].metric("Luftfeuchtigkeit", f"{hum}%" if hum is not None else "N/A")
            w_cols[2].metric("Niederschlag (1h)", f"{precip} mm" if precip is not None else "N/A")
        else:
            st.info("Keine Wetterdaten verfügbar (siehe Log-Meldungen oben).")
            
    # ... (Restliche UI mit Tabs, etc.)
            
    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
