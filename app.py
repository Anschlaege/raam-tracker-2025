"""
RAAM 2025 Live Dashboard - Version 6 (Finale Version)
Greift gezielt auf die korrekte Datenquelle (mainpoints.js) zu.
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


# --- FINALE, KORREKTE DATENABRUF-FUNKTIONEN ---

@st.cache_data(ttl=45) # Cache für 45 Sekunden
def fetch_trackleaders_data():
    """
    Holt die Live-Daten gezielt aus der 'mainpoints.js'-Datei von TrackLeaders.
    """
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://trackleaders.com/raam25f.php'
    }

    try:
        response = requests.get(data_url, headers=headers, timeout=15)
        if response.status_code != 200:
            st.error(f"Fehler beim Abrufen der Datendatei. Status Code: {response.status_code}")
            return None

        # Die .js-Datei enthält Daten in einer JavaScript-Variable, z.B. "var markers = [...]"
        # Wir extrahieren das Array mit einem regulären Ausdruck.
        match = re.search(r'var\s+markers\s*=\s*(\[.*?\]);', response.text, re.DOTALL)
        
        if not match:
            st.error("Konnte die 'markers'-Variable in der mainpoints.js nicht finden.")
            return None

        js_data_string = match.group(1)

        # Konvertiere den JavaScript-String in valides JSON:
        # 1. Setze Keys in Anführungszeichen (z.B. name: -> "name":)
        # 2. Ersetze einfache Anführungszeichen durch doppelte
        json_str = re.sub(r'([{,]\s*)(\w+):', r'\1"\2":', js_data_string)
        json_str = re.sub(r"'", '"', json_str)
        
        # Entferne das letzte Komma in Objekten, falls vorhanden (z.B. {..., "key":"val",})
        json_str = re.sub(r',\s*([\}\]])', r'\1', json_str)

        data = json.loads(json_str)
        return parse_marker_data(data)

    except requests.exceptions.RequestException as e:
        st.error(f"Ein Netzwerkfehler ist aufgetreten: {e}")
    except json.JSONDecodeError:
        st.error("Fehler beim Verarbeiten der JSON-Antwort. Der Regex zur Konvertierung war nicht erfolgreich.")
        st.code(json_str[:1000]) # Zeige den fehlerhaften JSON-String zum Debuggen
    except Exception as e:
        st.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
    
    return None

def parse_marker_data(raw_data):
    """Verarbeitet die Daten aus dem 'markers'-Array."""
    racers = []
    for item in raw_data:
        # Nur Fahrer mit Status "Live" und Kategorie "SOLO" berücksichtigen
        if item.get('status') == 'Live' and 'solo' in item.get('cat', '').lower():
            try:
                racer = {
                    'name': item.get('name', 'N/A'),
                    'bib': str(item.get('bib', '')),
                    'category': item.get('cat', 'SOLO'),
                    'position': 999,
                    'distance': float(item.get('dist', 0)),
                    'speed': float(item.get('spd', 0)),
                    'location': item.get('loc', ''),
                    'lat': float(item.get('lat', 0)),
                    'lon': float(item.get('lon', 0)),
                    'time_behind': '', # In diesem Format oft nicht direkt verfügbar
                    'elapsed_time': item.get('elapsed', ''),
                    'last_update': item.get('ts', '') 
                }
                racers.append(racer)
            except (ValueError, TypeError):
                # Ignoriere Einträge, die nicht korrekt konvertiert werden können
                continue

    if not racers:
        return None

    df = pd.DataFrame(racers)
    if not df.empty:
        df = df.sort_values(by='distance', ascending=False).reset_index(drop=True)
        df['position'] = df.index + 1
        return df.to_dict('records')
    return None

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
    
    with st.spinner("Lade Live-Daten von TrackLeaders..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        st.success("Live-Daten erfolgreich geladen!")
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        if df.empty:
            st.warning("Keine Solo-Fahrer in den Live-Daten gefunden oder alle sind 'Scratch'.")
        else:
            fritz_data = df[df['is_fritz']]
            
            if not fritz_data.empty:
                fritz = fritz_data.iloc[0]
                st.markdown("### ⭐ Fritz Geers Live Status")
                cols = st.columns(6)
                cols[0].metric("Position", f"#{fritz['position']}")
                cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
                cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
                cols[3].metric("Standort", fritz['location'] or "Unterwegs")
                cols[4].metric("Rückstand", fritz.get('gap_miles', 'N/A'))
                cols[5].metric("Zeit", fritz['elapsed_time'] or "N/A")
            else:
                st.warning("⚠️ Fritz Geers wurde in den Live-Daten nicht gefunden.")
            
            st.markdown("---")
            tab1, tab2, tab3, tab4 = st.tabs(["📊 Live Rangliste", "🗺️ Karte", "📈 Statistiken", "📡 Rohdaten"])
            
            with tab1:
                st.subheader("Live Rangliste - Solo Kategorie")
                display_cols = ['position', 'name', 'distance', 'speed', 'location', 'gap_miles', 'elapsed_time', 'is_fritz']
                display_df = df.reindex(columns=display_cols).copy()
                display_df.columns = ['Pos', 'Name', 'Distanz (mi)', 'Geschw. (mph)', 'Standort', 'Rückstand', 'Zeit', 'is_fritz']
                def highlight_fritz(row):
                    return ['background-color: #ffd700'] * len(row) if row['is_fritz'] else [''] * len(row)
                styled_df = display_df.drop('is_fritz', axis=1).style.apply(highlight_fritz, axis=1)
                st.dataframe(styled_df, use_container_width=True, height=600)
                csv = display_df.drop('is_fritz', axis=1).to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download CSV", csv, f"raam_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
            
            with tab2:
                st.subheader("Live Positionen auf der Karte")
                map_df = df[(df['lat'] != 0) & (df['lon'] != 0)]
                if not map_df.empty:
                    m = folium.Map(location=[38.0, -97.0], zoom_start=4)
                    for _, racer in map_df.iterrows():
                        color = 'gold' if racer['is_fritz'] else 'blue'
                        icon = 'star' if racer['is_fritz'] else 'bicycle'
                        popup_html = f"""<b>{'⭐ ' if racer['is_fritz'] else ''}{racer['name']}</b><br>
                                       Position: #{racer['position']}<br>
                                       Distanz: {racer['distance']:.1f} mi"""
                        folium.Marker([racer['lat'], racer['lon']], popup=folium.Popup(popup_html, max_width=300),
                                      tooltip=f"{racer['name']} (#{racer['position']})",
                                      icon=folium.Icon(color=color, prefix='fa', icon=icon)).add_to(m)
                    st_folium(m, height=600, width=None)
                else:
                    st.info("Keine GPS-Koordinaten in den Live-Daten verfügbar.")
            
            with tab3:
                st.subheader("Live Statistiken")
                cols = st.columns(4)
