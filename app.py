"""
RAAM 2025 Live Dashboard - Version 8 (Finale Lösung)
Liest und verarbeitet den generierten JavaScript-Code direkt.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime
import requests
import re

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


# --- FINALE DATENABRUF-FUNKTION (PASST ZU JAVASCRIPT-CODE-STRUKTUR) ---

@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    """
    Liest die mainpoints.js und extrahiert die Fahrerdaten direkt aus dem
    generierten JavaScript-Code mittels Regex.
    """
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://trackleaders.com/raam25f.php'
    }

    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        if response.status_code != 200:
            st.error(f"Fehler beim Abruf der Datendatei. Status: {response.status_code}")
            return None

        js_content = response.text

        # Dieser Regex ist maßgeschneidert, um die Daten aus dem JS-Code zu extrahieren.
        # Er sucht nach Blöcken, die mit L.marker beginnen und die relevanten Daten enthalten.
        pattern = re.compile(
            r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\].*?"  # 1: lat, 2: lon
            r"bindTooltip\(\"<b>\((\d+)\)\s*(.*?)<\/b>.*?"  # 3: bib, 4: name
            r"([\d.]+)\s*mph at route mile ([\d.]+)",  # 5: speed, 6: distance
            re.DOTALL
        )
        
        matches = pattern.findall(js_content)

        if not matches:
            st.error("Konnte keine Fahrer-Daten mit dem neuen Regex-Muster im JavaScript finden.")
            st.code(js_content[:2000]) # Zeige den Anfang des Codes zur Analyse
            return None
        
        return parse_js_code_data(matches)

    except requests.exceptions.RequestException as e:
        st.error(f"Netzwerkfehler: {e}")
    except Exception as e:
        st.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
    
    return None

def parse_js_code_data(matches):
    """Verarbeitet die extrahierten Daten aus dem Regex-Fund."""
    racers = []
    for match in matches:
        try:
            # Da die Kategorie nicht explizit vorhanden ist, nehmen wir an, dass es Solo-Fahrer sind.
            # Dies ist eine Annahme basierend auf dem Dateinamen 'mainpoints.js'.
            racer = {
                'lat': float(match[0]),
                'lon': float(match[1]),
                'bib': match[2],
                'name': match[3].strip(),
                'speed': float(match[4]),
                'distance': float(match[5]),
                'category': 'SOLO',
                'position': 999, # Platzhalter, wird später berechnet
                'location': '',  # Nicht direkt verfügbar in diesem Format
                'time_behind': '',
                'elapsed_time': '',
                'last_update': '' 
            }
            racers.append(racer)
        except (ValueError, IndexError):
            # Ignoriere fehlerhafte Übereinstimmungen
            continue
    
    if not racers:
        st.warning("Regex hat zwar Treffer gefunden, aber keiner konnte verarbeitet werden.")
        return None

    # Erstelle DataFrame zur Berechnung der Positionen
    df = pd.DataFrame(racers)
    df = df.sort_values(by='distance', ascending=False).reset_index(drop=True)
    df['position'] = df.index + 1
    return df.to_dict('records')

def create_dataframe(racers_data):
    """Erstellt und bereitet DataFrame vor."""
    if not racers_data: return pd.DataFrame()
    df = pd.DataFrame(racers_data)
    df['is_fritz'] = df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True)
    df = df.sort_values('position')
    df['data_timestamp'] = datetime.now()
    return df

def calculate_statistics(df):
    """Berechnet zusätzliche Statistiken."""
    if df.empty: return df
    leader = df.iloc[0]
    if 'distance' in df.columns:
        df['gap_miles'] = leader['distance'] - df['distance']
        df['gap_miles'] = df['gap_miles'].apply(lambda x: f"+{x:.1f}" if x > 0 else "Leader")
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
    st.sidebar.info("**Live-Daten** von TrackLeaders\n\n**Fritz Geers** wird mit ⭐ hervorgehoben")
    
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    with st.spinner("Lade und analysiere Live-Daten..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        st.success(f"{len(racers_data)} Fahrer erfolgreich aus Live-Daten extrahiert!")
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        if df.empty:
            st.warning("Daten konnten nicht in ein DataFrame umgewandelt werden.")
        else:
            fritz_data = df[df['is_fritz']]
            
            if not fritz_data.empty:
                fritz = fritz_data.iloc[0]
                st.markdown("### ⭐ Fritz Geers Live Status")
                cols = st.columns(6)
                cols[0].metric("Position", f"#{fritz['position']}")
                cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
                cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
                cols[3].metric("Standort", fritz.get('location', 'N/A'))
                cols[4].metric("Rückstand", fritz.get('gap_miles', 'N/A'))
                cols[5].metric("Zeit", fritz.get('elapsed_time', 'N/A'))
            else:
                st.warning("⚠️ Fritz Geers wurde in den Live-Daten nicht gefunden.")
            
            st.markdown("---")
            tab1, tab2, tab3 = st.tabs(["📊 Live Rangliste", "🗺️ Karte", "📈 Statistiken"])
            
            with tab1:
                display_cols = ['position', 'name', 'distance', 'speed', 'is_fritz']
                display_df = df.reindex(columns=display_cols).copy()
                display_df.columns = ['Pos', 'Name', 'Distanz (mi)', 'Geschw. (mph)', 'is_fritz']
                def highlight_fritz(row):
                    return ['background-color: #ffd700'] * len(row) if row['is_fritz'] else [''] * len(row)
                styled_df = display_df.drop('is_fritz', axis=1).style.apply(highlight_fritz, axis=1)
                st.dataframe(styled_df, use_container_width=True, height=600)

            with tab2:
                st.subheader("Live Positionen auf der Karte")
                map_df = df[(df['lat'] != 0) & (df['lon'] != 0)]
                if not map_df.empty:
                    m = folium.Map(location=[map_df['lat'].mean(), map_df['lon'].mean()], zoom_start=5)
                    for _, racer in map_df.iterrows():
                        color = 'gold' if racer['is_fritz'] else 'blue'
                        icon = 'star' if racer['is_fritz'] else 'bicycle'
                        popup_html = f"<b>{racer['name']}</b><br>Pos: #{racer['position']}<br>Dist: {racer['distance']:.1f} mi"
                        folium.Marker([racer['lat'], racer['lon']], popup=folium.Popup(popup_html, max_width=300),
                                      tooltip=f"{racer['name']} (#{racer['position']})",
                                      icon=folium.Icon(color=color, prefix='fa', icon=icon)).add_to(m)
                    st_folium(m, height=600, width=None)
                else:
                    st.info("Keine GPS-Koordinaten in den Live-Daten verfügbar.")

            with tab3:
                # Statistiken... (können nach Bedarf hinzugefügt werden)
                st.info("Statistik-Tab wird nach Bedarf implementiert.")

    else:
        st.warning("Es konnten keine verarbeitbaren Daten gefunden werden. Warten auf das nächste Update...")

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="45">', unsafe_allow_html=True)
        st.sidebar.info("🔄 Nächstes Update in 45 Sekunden...")

if __name__ == "__main__":
    main()
