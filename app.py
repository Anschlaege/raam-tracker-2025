"""
RAAM 2025 Live Dashboard - Version 19 (Wetter-Integration)
- Ruft Live-Wetterdaten für Fritz Geers' aktuelle Position ab und zeigt sie an.
- Nutzt die Open-Meteo API (kein API-Schlüssel erforderlich).
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime
import requests
import re

# --- NEUE FUNKTION FÜR WETTERDATEN ---
@st.cache_data(ttl=600) # Cache für 10 Minuten, da sich das Wetter nicht sekündlich ändert
def get_weather_data(lat, lon):
    """Ruft aktuelle Wetterdaten für eine gegebene Position von der Open-Meteo API ab."""
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    try:
        api_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,precipitation",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm"
        }
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status() # Löst einen Fehler bei 4xx/5xx Status-Codes aus
        data = response.json()
        
        current_weather = data.get('current', {})
        return {
            'temperature': current_weather.get('temperature_2m'),
            'humidity': current_weather.get('relative_humidity_2m'),
            'precipitation': current_weather.get('precipitation')
        }
    except Exception:
        # Wenn der Wetterdienst ausfällt, soll die App trotzdem weiterlaufen.
        return None

# Seiten-Konfiguration
st.set_page_config(
    page_title="RAAM 2025 Live Tracker - Fritz Geers",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown("""<style>.stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 5px; }</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        js_content = response.text
        pattern = re.compile(
            r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\].*?"
            r"bindTooltip\(\"<b>\(([\w\d]+)\)\s*(.*?)<\/b>.*?"
            r"([\d.]+)\s*mph at route mile ([\d.]+)",
            re.DOTALL
        )
        matches = pattern.findall(js_content)
        if not matches: return None
        return parse_js_code_data(matches)
    except Exception:
        return None

def parse_js_code_data(js_content):
    racers = []
    racer_blocks = js_content.split('markers.push(')
    for block in racer_blocks:
        try:
            status = re.search(r"\.mystatus\s*=\s*'(.*?)';", block).group(1)
            category = re.search(r"\.mycategory\s*=\s*'(.*?)';", block).group(1)
            if status != 'Active' or category != 'Solo': continue
            lat_lon = re.search(r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\]", block)
            tooltip = re.search(r"bindTooltip\(\"<b>\(([\w\d]+)\)\s*(.*?)<\/b>.*?<br>([\d.]+)\s*mph at route mile ([\d.]+)", block)
            if not all([lat_lon, tooltip]): continue
            racers.append({
                'lat': float(lat_lon.group(1)), 'lon': float(lat_lon.group(2)), 'bib': tooltip.group(1),
                'name': tooltip.group(2).strip(), 'speed': float(tooltip.group(3)), 'distance': float(tooltip.group(4)),
                'category': category, 'position': 999
            })
        except (AttributeError, ValueError, IndexError):
            continue
    if not racers: return None
    df = pd.DataFrame(racers).sort_values(by='distance', ascending=False).reset_index(drop=True)
    df['position'] = df.index + 1
    return df.to_dict('records')

def create_dataframe(racers_data):
    if not racers_data: return pd.DataFrame()
    df = pd.DataFrame(racers_data)
    df['is_fritz'] = (df['bib'] == '675') | (df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True))
    df = df.sort_values('position')
    return df

def calculate_statistics(df):
    if df.empty: return df
    leader = df.iloc[0]
    df['gap_to_leader'] = leader['distance'] - df['distance']
    df['gap_to_leader'] = df['gap_to_leader'].apply(lambda x: f"+{x:.1f} mi" if x > 0 else "Leader")
    fritz_data_list = df[df['is_fritz']].to_dict('records')
    if not fritz_data_list:
        df['gap_to_fritz'] = ""
        return df
    fritz = fritz_data_list[0]
    fritz_pos, fritz_dist, fritz_speed = fritz['position'], fritz['distance'], fritz['speed']
    def format_time_gap(h):
        if pd.isna(h) or h <= 0: return ""
        return f"~{int(h)}h {int((h*60)%60)}m" if h >= 1 else f"~{int(h*60)}m"
    def calculate_gap_to_fritz(row):
        if row['is_fritz']: return "Fritz Geers"
        if row['position'] < fritz_pos:
            gap_mi = row['distance'] - fritz_dist
            time_h = (gap_mi / fritz_speed) if fritz_speed > 0 else None
            return f"+{gap_mi:.1f} mi / {gap_mi*1.60934:.1f} km ({format_time_gap(time_h)})"
        elif row['position'] <= fritz_pos + 5:
            gap_mi = fritz_dist - row['distance']
            time_h = (gap_mi / row['speed']) if row['speed'] > 0 else None
            return f"-{gap_mi:.1f} mi / -{gap_mi*1.60934:.1f} km ({format_time_gap(time_h)})"
        return ""
    df['gap_to_fritz'] = df.apply(calculate_gap_to_fritz, axis=1)
    return df

def main():
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Jetzt aktualisieren"): st.cache_data.clear(); st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (60 Sek)", value=True)
    st.sidebar.markdown("---")
    st.sidebar.info("**Live-Daten** von TrackLeaders\n\n**Fritz Geers** (#675) wird mit ⭐ hervorgehoben")
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    with st.spinner("Lade und analysiere Live-Daten..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        st.success(f"{len(racers_data)} Solo-Fahrer erfolgreich aus Live-Daten extrahiert!")
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        fritz_data = df[df['is_fritz']]
        if not fritz_data.empty:
            fritz = fritz_data.iloc[0]
            st.markdown("### ⭐ Fritz Geers Live Status")
            cols = st.columns(5)
            cols[0].metric("Position", f"#{fritz['position']}")
            cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
            cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
            cols[3].metric("Startnummer", f"#{fritz['bib']}")
            cols[4].metric("Rückstand (Führender)", fritz.get('gap_to_leader', 'N/A'))
            
            # --- NEUER WETTER-ABSCHNITT ---
            with st.spinner("Lade aktuelle Wetterdaten..."):
                 weather_data = get_weather_data(fritz.get('lat'), fritz.get('lon'))
            
            if weather_data and all(weather_data.values()):
                st.markdown("#### 🌦️ Wetter an seiner Position")
                w_cols = st.columns(3)
                w_cols[0].metric("Temperatur", f"{weather_data['temperature']} °C")
                w_cols[1].metric("Luftfeuchtigkeit", f"{weather_data['humidity']}%")
                w_cols[2].metric("Niederschlag (1h)", f"{weather_data['precipitation']} mm")
            # --- ENDE WETTER-ABSCHNITT ---

        else:
            st.warning("⚠️ Fritz Geers (#675) wurde in den Live-Daten nicht gefunden.")
        
        st.markdown("---")
        tab1, tab2, tab3 = st.tabs(["📊 Live Rangliste", "🗺️ Karte", "📈 Statistiken"])
        
        with tab1:
            #... (Tabellen-Code unverändert)
            pass

        with tab2:
            #... (Karten-Code unverändert)
            pass

        with tab3:
            #... (Statistik-Code unverändert)
            pass
    else:
        st.warning("Es konnten keine verarbeitbaren Daten gefunden werden.")

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
