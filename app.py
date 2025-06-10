"""
RAAM 2025 Live Dashboard - Version 20 (Finale Version)
- UI-Anzeige für Tabs wiederhergestellt.
- Datum und Uhrzeit zur Discord-Benachrichtigung hinzugefügt.
- Alle Features kombiniert.
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

# --- FUNKTIONEN ---

@st.cache_data(ttl=600)
def get_local_time(lat, lon):
    """Ermittelt die lokale Zeitzone und Uhrzeit für eine gegebene Position."""
    if lat is None or lon is None: return "N/A"
    try:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lng=lon, lat=lat)
        if tz_name:
            local_tz = timezone(tz_name)
            local_time = datetime.now(local_tz)
            return local_time.strftime('%H:%M %Z')
        return "N/A"
    except Exception:
        return "N/A"

@st.cache_data(ttl=600)
def get_weather_data(lat, lon):
    """Ruft aktuelle Wetterdaten ab."""
    if lat is None or lon is None: return None
    try:
        api_url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,precipitation","temperature_unit": "celsius", "precipitation_unit": "mm"}
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        current = response.json().get('current', {})
        return {'temperature': current.get('temperature_2m'),'humidity': current.get('relative_humidity_2m'),'precipitation': current.get('precipitation')}
    except Exception: return None

def send_to_discord_as_file(webhook_url, df, weather_data):
    """Sendet die komplette Rangliste als CSV-Datei und eine Zusammenfassung an Discord."""
    if df.empty: return {"status": "error", "message": "DataFrame ist leer."}

    # Erstelle einen detaillierten Zeitstempel auf Deutsch
    days_de = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    now = datetime.now()
    day_name = days_de[now.weekday()]
    timestamp_str = now.strftime(f"{day_name}, %d.%m.%Y um %H:%M Uhr")

    weather_summary = "Wetterdaten für Fritz nicht verfügbar."
    if weather_data and all(v is not None for v in weather_data.values()):
        weather_summary = (f"Aktuelles Wetter an Fritz' Position: "
                           f"{weather_data['temperature']}°C, "
                           f"{weather_data['humidity']}% Luftfeuchtigkeit, "
                           f"{weather_data['precipitation']}mm Niederschlag.")
    
    content = (f"**RAAM Live-Export vom {timestamp_str}**\n\n"
               f"🌦️ {weather_summary}\n\n"
               f"Die vollständige Rangliste befindet sich im Anhang.")

    csv_data = df.to_csv(index=False, encoding='utf-8')
    file_name = f"raam_live_export_{now.strftime('%Y%m%d_%H%M')}.csv"
    payload_json = {"content": content, "username": "RAAM Live Tracker", "avatar_url": "https://i.imgur.com/4M34hi2.png"}
    files = {'file': (file_name, csv_data, 'text/csv')}
    
    try:
        response = requests.post(webhook_url, data={'payload_json': json.dumps(payload_json)}, files=files, timeout=15)
        return {"status": "success", "message": f"Datei '{file_name}' erfolgreich gesendet!"} if 200 <= response.status_code < 300 else {"status": "error", "message": f"Discord-Fehler: {response.status_code}"}
    except requests.exceptions.RequestException as e: return {"status": "error", "message": f"Netzwerkfehler: {e}"}

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
        if auto_refresh: st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
        return

    df = create_dataframe(racers_data)
    df = calculate_statistics(df)
    
    st.success(f"{len(df)} Solo-Fahrer geladen!")
    st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
    
    fritz_data = df[df['is_fritz']]
    # Initialisiere weather_data außerhalb des if-Blocks, um es später für den Export zu verwenden
    weather_data = None
    if not fritz_data.empty:
        fritz = fritz_data.iloc[0]
        weather_data = get_weather_data(fritz.get('lat'), fritz.get('lon'))
        local_time = get_local_time(fritz.get('lat'), fritz.get('lon'))
        
        st.markdown("### ⭐ Fritz Geers Live Status")
        cols = st.columns(6)
        cols[0].metric("Position", f"#{fritz['position']}")
        cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
        cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
        cols[3].metric("Startnummer", f"#{fritz['bib']}")
        cols[4].metric("Lokale Zeit", local_time)
        
        if weather_data and all(v is not None for v in weather_data.values()):
            st.markdown("#### 🌦️ Wetter an seiner Position")
            w_cols = st.columns(3)
            w_cols[0].metric("Temperatur", f"{weather_data['temperature']} °C")
            w_cols[1].metric("Luftfeuchtigkeit", f"{weather_data['humidity']}%")
            w_cols[2].metric("Niederschlag (1h)", f"{weather_data['precipitation']} mm")
    
    # Discord-Button in der Sidebar (wird jetzt immer angezeigt, wenn Daten da sind)
    try:
        webhook_url = st.secrets["DISCORD_WEBHOOK_URL"]
        st.sidebar.markdown("---")
        st.sidebar.header("Export")
        if st.sidebar.button("Export an Discord senden"):
            with st.spinner("Sende CSV an Discord..."):
                result = send_to_discord_as_file(webhook_url, df, weather_data)
                if result.get("status") == "success": st.sidebar.success(result.get("message"))
                else: st.sidebar.error(result.get("message"))
    except KeyError: pass
            
    st.markdown("---")
    # --- WIEDERHERGESTELLTE UI-TABS ---
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
        map_df = df[df['lat'] != 0]
        if not map_df.empty:
            m = folium.Map(location=[map_df['lat'].mean(), map_df['lon'].mean()], zoom_start=6)
            for _, r in map_df.iterrows():
                folium.Marker([r['lat'], r['lon']], 
                              popup=f"<b>{r['name']}</b><br>Pos: #{r['position']}<br>Dist: {r['distance']:.1f} mi",
                              tooltip=f"#{r['position']} {r['name']}",
                              icon=folium.Icon(color='gold' if r['is_fritz'] else 'blue', icon='star' if r['is_fritz'] else 'bicycle', prefix='fa')).add_to(m)
            st_folium(m, height=600, width=None)

    with tab3:
        st.subheader("Top 10 nach Distanz")
        top10 = df.head(10).sort_values('distance', ascending=True)
        fig = px.bar(top10, y='name', x='distance', orientation='h', text='distance', labels={'name': 'Fahrer', 'distance': 'Distanz (Meilen)'})
        fig.update_traces(texttemplate='%{text:.1f} mi', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
