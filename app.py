"""
RAAM 2025 Live Dashboard - Version 10 (Stabile Darstellung)
- Entfernt die problematische .hide()-Funktion, um Kompatibilität zu gewährleisten.
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


@st.cache_data(ttl=45)
def fetch_trackleaders_data():
    """Liest die mainpoints.js und extrahiert die Fahrerdaten direkt aus dem JavaScript-Code."""
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://trackleaders.com/raam25f.php'}

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

    except requests.exceptions.RequestException as e:
        st.error(f"Netzwerkfehler: {e}")
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
    """Berechnet zusätzliche Statistiken."""
    if df.empty: return df
    leader = df.iloc[0]
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
    st.sidebar.info("**Live-Daten** von TrackLeaders\n\n**Fritz Geers** (#675) wird mit ⭐ hervorgehoben")
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    with st.spinner("Lade und analysiere Live-Daten..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        st.success(f"{len(racers_data)} Fahrer erfolgreich aus Live-Daten extrahiert!")
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        if not df.empty:
            fritz_data = df[df['is_fritz']]
            if not fritz_data.empty:
                fritz = fritz_data.iloc[0]
                st.markdown("### ⭐ Fritz Geers Live Status")
                cols = st.columns(6)
                cols[0].metric("Position", f"#{fritz['position']}")
                cols[1].metric("Distanz", f"{fritz['distance']:.1f} mi")
                cols[2].metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph")
                cols[3].metric("Startnummer", f"#{fritz['bib']}")
                cols[4].metric("Rückstand", fritz.get('gap_miles', 'N/A'))
            else:
                st.warning("⚠️ Fritz Geers (#675) wurde in den Live-Daten nicht gefunden.")
            
            st.markdown("---")
            tab1, tab2, tab3 = st.tabs(["📊 Live Rangliste", "🗺️ Karte", "📈 Statistiken"])
            
            with tab1:
                st.subheader("Live Rangliste - Solo Kategorie")
                display_cols = ['position', 'bib', 'name', 'distance', 'speed', 'gap_miles', 'is_fritz']
                display_df = df[display_cols].copy()
                display_df.rename(columns={
                    'position': 'Pos', 'bib': 'Nr.', 'name': 'Name', 
                    'distance': 'Distanz (mi)', 'speed': 'Geschw. (mph)', 'gap_miles': 'Rückstand'
                }, inplace=True)
                
                def highlight_fritz(row):
                    return ['background-color: #ffd700'] * len(row) if row.is_fritz else [''] * len(row)
                
                # --- KORREKTUR HIER: .hide() entfernt ---
                styled_df = display_df.style.apply(highlight_fritz, axis=1)
                
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

            with tab3:
                st.subheader("Live Statistiken")
                top10 = df.head(10)
                fig_dist = px.bar(top10, y='name', x='distance', orientation='h', title='Top 10 - Distanz')
                st.plotly_chart(fig_dist, use_container_width=True)

    else:
        st.warning("Es konnten keine verarbeitbaren Daten gefunden werden. Warten auf das nächste Update...")

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="45">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
