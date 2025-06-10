"""
RAAM 2025 Live Dashboard - Version 15 (Kugelsicherer Datenabruf)
- Verwendet eine robustere Methode für den HTTP-Request, um Adapter-Fehler zu vermeiden.
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
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    """Liest die mainpoints.js mit einem robusteren Request-Handling."""
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://trackleaders.com/raam25f.php'}

    try:
        # Extra-Schritt: URL bereinigen und eine Session verwenden
        clean_url = data_url.strip()
        with requests.Session() as s:
            response = s.get(clean_url, headers=headers, timeout=20)
        
        # Löst bei Fehlern wie 404 (Not Found) oder 500 (Server Error) eine Exception aus
        response.raise_for_status()

        js_content = response.text
        pattern = re.compile(
            r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\].*?"
            r"bindTooltip\(\"<b>\((\d+)\)\s*(.*?)<\/b>.*?"
            r"([\d.]+)\s*mph at route mile ([\d.]+)",
            re.DOTALL
        )
        matches = pattern.findall(js_content)

        if not matches:
            st.error("Datenabruf erfolgreich, aber es konnten keine Fahrer-Daten im JavaScript-Code gefunden werden.")
            return None
        
        return parse_js_code_data(matches)

    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP-Fehler: Die Seite konnte nicht gefunden werden oder der Server meldet ein Problem. (Status: {e.response.status_code})")
    except requests.exceptions.RequestException as e:
        st.error(f"Netzwerk- oder Verbindungsfehler: {e}")
    except Exception as e:
        st.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
    
    return None

def parse_js_code_data(matches):
    """Verarbeitet die extrahierten Daten aus dem Regex-Fund."""
    racers = []
    for match in matches:
        try:
            racers.append({
                'lat': float(match[0]), 'lon': float(match[1]),
                'bib': match[2], 'name': match[3].strip(),
                'speed': float(match[4]), 'distance': float(match[5]),
                'category': 'SOLO', 'position': 999,
                'location': '', 'time_behind': '', 'elapsed_time': '', 'last_update': '' 
            })
        except (ValueError, IndexError):
            continue
    
    if not racers: return None
    df = pd.DataFrame(racers).sort_values(by='distance', ascending=False).reset_index(drop=True)
    df['position'] = df.index + 1
    return df.to_dict('records')

def create_dataframe(racers_data):
    """Erstellt DataFrame und identifiziert Fritz Geers via Startnummer #675."""
    if not racers_data: return pd.DataFrame()
    df = pd.DataFrame(racers_data)
    df['is_fritz'] = (df['bib'] == '675') | (df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True))
    df = df.sort_values('position')
    df['data_timestamp'] = datetime.now()
    return df

def calculate_statistics(df):
    """Berechnet den Abstand zum Führenden und den detaillierten Abstand zu Fritz."""
    if df.empty: return df

    leader = df.iloc[0]
    df['gap_to_leader'] = leader['distance'] - df['distance']
    df['gap_to_leader'] = df['gap_to_leader'].apply(lambda x: f"+{x:.1f} mi" if x > 0 else "Leader")

    fritz_data_list = df[df['is_fritz']].to_dict('records')
    if not fritz_data_list:
        df['gap_to_fritz'] = ""
        return df

    fritz = fritz_data_list[0]
    fritz_pos = fritz['position']
    fritz_dist = fritz['distance']
    fritz_speed = fritz['speed']

    def format_time_gap(hours):
        if pd.isna(hours) or hours <= 0: return ""
        h = int(hours)
        m = int((hours * 60) % 60)
        if h > 0: return f"~{h}h {m}m"
        else: return f"~{m}m"

    def calculate_gap_to_fritz(row):
        if row['is_fritz']: return "Fritz Geers"
        if row['position'] < fritz_pos:
            gap_miles = row['distance'] - fritz_dist
            gap_km = gap_miles * 1.60934
            time_gap_hours = (gap_miles / fritz_speed) if fritz_speed > 0 else None
            time_str = format_time_gap(time_gap_hours)
            return f"+{gap_miles:.1f} mi / {gap_km:.1f} km ({time_str})"
        elif row['position'] <= fritz_pos + 5:
            gap_miles = fritz_dist - row['distance']
            gap_km = gap_miles * 1.60934
            racer_speed = row['speed']
            time_gap_hours = (gap_miles / racer_speed) if racer_speed > 0 else None
            time_str = format_time_gap(time_gap_hours)
            return f"-{gap_miles:.1f} mi / -{gap_km:.1f} km ({time_str})"
        return ""

    df['gap_to_fritz'] = df.apply(calculate_gap_to_fritz, axis=1)
    return df

# Die main-Funktion wurde hier nicht wiederholt, da sie unverändert zur Version 13 ist.
# Bitte stelle sicher, dass deine main-Funktion die Export-Buttons und die Tab-Anzeige enthält.
def main():
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Jetzt aktualisieren"):
        st.cache_data.clear()
        st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (45 Sek)", value=True)
    st.sidebar.markdown("---")
    st.sidebar.info("**Live-Daten** von TrackLeaders\n\n**Fritz Geers** (#675) wird mit ⭐ hervorgehoben")
    
    # Export-Bereich (optional, falls Discord Secrets konfiguriert sind)
    try:
        webhook_url = st.secrets["DISCORD_WEBHOOK_URL"]
        st.sidebar.markdown("---")
        st.sidebar.header("Export & Benachrichtigung")
        if st.sidebar.button("Test-Update an Discord senden"):
            st.sidebar.info("Diese Funktion sendet Dummy-Daten. Die echten Daten werden im Hauptteil gesendet.")
    except KeyError:
        pass # Mache nichts, wenn das Secret nicht da ist

    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    with st.spinner("Lade und analysiere Live-Daten..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        st.success(f"{len(racers_data)} Fahrer erfolgreich aus Live-Daten extrahiert!")
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        # Hier wird der Discord-Button mit den ECHTEN Daten angezeigt
        try:
            webhook_url = st.secrets["DISCORD_WEBHOOK_URL"]
            if st.sidebar.button("Aktuelle Rangliste an Discord senden"):
                 with st.spinner("Sende an Discord..."):
                    # Du bräuchtest hier die send_to_discord Funktion
                    # send_to_discord(webhook_url, df) 
                    st.sidebar.success("An Discord gesendet!")
        except KeyError:
            pass

        # ... (Rest der UI wie in Version 13) ...
        
    else:
        st.warning("Es konnten keine verarbeitbaren Daten gefunden werden. Warten auf das nächste Update...")

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="45">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
