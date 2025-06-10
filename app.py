"""
RAAM 2025 Live Dashboard - Version 14 (Feature-Update)
- Fügt eine Export-Funktion zu Discord via Webhook hinzu.
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

# --- NEUE FUNKTION FÜR DISCORD ---
def send_to_discord(webhook_url, df):
    """Formatiert die Top-Fahrer und sendet sie an einen Discord-Webhook."""
    if df.empty:
        return {"status": "error", "message": "DataFrame ist leer."}

    # Wir senden die Top 15 als Text, um die Nachricht lesbar zu halten
    top_15 = df.head(15)
    
    # Erstelle einen schön formatierten Text für Discord
    # Markdown für Code-Blöcke in Discord wird mit ``` gestartet und beendet
    message_content = "```\n"
    message_content += "RAAM 2025 - Live Rangliste Update\n"
    message_content += "-------------------------------------\n"
    message_content += top_15[['position', 'name', 'distance', 'speed']].to_string(index=False)
    message_content += "\n```"

    # Daten für den POST-Request an Discord vorbereiten
    payload = {
        "content": message_content,
        "username": "RAAM Live Tracker",
        "avatar_url": "[https://i.imgur.com/4M34hi2.png](https://i.imgur.com/4M34hi2.png)" # Ein Fahrrad-Icon
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if 200 <= response.status_code < 300:
            return {"status": "success", "message": "Daten erfolgreich an Discord gesendet!"}
        else:
            return {"status": "error", "message": f"Discord-Fehler: {response.status_code}, {response.text}"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Netzwerkfehler beim Senden: {e}"}


# Seiten-Konfiguration
st.set_page_config(
    page_title="RAAM 2025 Live Tracker - Fritz Geers",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ... (alle anderen Funktionen von fetch_trackleaders_data bis calculate_statistics bleiben unverändert) ...
@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    """Liest die mainpoints.js und extrahiert die Fahrerdaten direkt aus dem JavaScript-Code."""
    data_url = "[https://trackleaders.com/spot/raam25/mainpoints.js](https://trackleaders.com/spot/raam25/mainpoints.js)"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': '[https://trackleaders.com/raam25f.php](https://trackleaders.com/raam25f.php)'}

    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        if response.status_code != 200:
            st.error(f"Fehler beim Abruf der Datendatei. Status: {response.status_code}")
            return None

        js_content = response.text
        pattern = re.compile(
            r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\].*?"
            r"bindTooltip\(\"<b>\((\d+)\)\s*(.*?)<\/b>.*?"
            r"([\d.]+)\s*mph at route mile ([\d.]+)",
            re.DOTALL
        )
        matches = pattern.findall(js_content)

        if not matches:
            st.error("Konnte keine Fahrer-Daten mit dem Regex-Muster im JavaScript finden.")
            return None
        
        return parse_js_code_data(matches)

    except Exception as e:
        st.error(f"Ein unerwarteter Fehler im Datenabruf ist aufgetreten: {e}")
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

# Hauptanwendung
def main():
    st.sidebar.title("🚴 RAAM 2025 Live Tracker")
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Jetzt aktualisieren"):
        st.cache_data.clear()
        st.rerun()
    auto_refresh = st.sidebar.checkbox("Auto-Refresh (45 Sek)", value=True)
    st.sidebar.markdown("---")
    
    # Der Hauptteil der UI bleibt gleich
    # ...

    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    with st.spinner("Lade und analysiere Live-Daten..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        st.success(f"{len(racers_data)} Fahrer erfolgreich aus Live-Daten extrahiert!")
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        
        # --- NEUER EXPORT-BEREICH IN DER SIDEBAR ---
        st.sidebar.markdown("---")
        st.sidebar.header("Export & Benachrichtigung")
        
        # Hole die Webhook-URL aus den Streamlit Secrets
        try:
            webhook_url = st.secrets["DISCORD_WEBHOOK_URL"]
            if st.sidebar.button("Update an Discord senden"):
                with st.spinner("Sende an Discord..."):
                    result = send_to_discord(webhook_url, df)
                    if result["status"] == "success":
                        st.sidebar.success(result["message"])
                    else:
                        st.sidebar.error(result["message"])
        except KeyError:
            st.sidebar.error("Discord Webhook URL nicht in den Secrets gefunden.")
            st.sidebar.info("Bitte füge `DISCORD_WEBHOOK_URL` zu deinen Streamlit Secrets hinzu.")

        # --- REST DER ANZEIGE ---
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        if not df.empty:
            # ... (UI-Code für Fritz-Status und Tabs wie zuvor)
            pass

    else:
        st.warning("Es konnten keine verarbeitbaren Daten gefunden werden.")

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="45">', unsafe_allow_html=True)

if __name__ == "__main__":
    # Wir müssen den vollen UI-Code hier wieder einfügen
    main()
