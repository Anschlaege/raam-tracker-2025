"""
RAAM 2025 Live Dashboard - Version 17 (Finale, funktionierende Version)
- Verwendet einen robusten, mehrstufigen Parser, der auf die exakte Datenstruktur zugeschnitten ist.
- Filtert korrekt nur aktive Solo-Fahrer.
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
    """Lädt die mainpoints.js und übergibt den Roh-Text an den Parser."""
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}

    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        return parse_js_code_data(response.text)
    except requests.exceptions.RequestException as e:
        st.error(f"Netzwerkfehler: {e}")
    except Exception as e:
        st.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
    return None

def parse_js_code_data(js_content):
    """
    Parst den rohen JavaScript-Inhalt, indem er ihn in Blöcke aufteilt
    und jeden Block einzeln mit gezielten Regex-Mustern analysiert.
    """
    racers = []
    # Teile die Datei in Blöcke, einen für jeden Fahrer. Der Split-Punkt ist verlässlich.
    racer_blocks = js_content.split('markers.push(')

    for block in racer_blocks:
        try:
            # Extrahiere alle benötigten Informationen mit einzelnen, kleinen Regex-Mustern.
            status = re.search(r"\.mystatus\s*=\s*'(.*?)';", block).group(1)
            category = re.search(r"\.mycategory\s*=\s*'(.*?)';", block).group(1)
            
            # Überspringe alle, die nicht aktive Solo-Fahrer sind.
            if status != 'Active' or category != 'Solo':
                continue

            lat_lon = re.search(r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\]", block)
            tooltip = re.search(r"bindTooltip\(\"<b>\(([\w\d]+)\)\s*(.*?)<\/b>.*?<br>([\d.]+)\s*mph at route mile ([\d.]+)", block)
            
            if not all([lat_lon, tooltip]):
                continue

            racers.append({
                'lat': float(lat_lon.group(1)),
                'lon': float(lat_lon.group(2)),
                'bib': tooltip.group(1),
                'name': tooltip.group(2).strip(),
                'speed': float(tooltip.group(3)),
                'distance': float(tooltip.group(4)),
                'category': category,
                'position': 999, 'location': '', 'time_behind': '', 
                'elapsed_time': '', 'last_update': '' 
            })
        except (AttributeError, ValueError, IndexError):
            # Ignoriere Blöcke, die nicht das erwartete Format haben
            continue
    
    if not racers:
        st.warning("Daten heruntergeladen, aber keine passenden Fahrer (Status: Active, Kategorie: Solo) gefunden.")
        return None
        
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
    """Berechnet Abstände zum Führenden und zu Fritz."""
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
        else:
            st.warning("⚠️ Fritz Geers (#675) wurde in den Live-Daten nicht gefunden.")
        
        st.markdown("---")
        tab1, tab2, tab3 = st.tabs(["📊 Live Rangliste", "🗺️ Karte", "📈 Statistiken"])
        
        with tab1:
            st.subheader("Live Rangliste - Solo Kategorie")
            display_cols = ['position', 'bib', 'name', 'distance', 'speed', 'gap_to_fritz', 'is_fritz']
            display_df = df.reindex(columns=display_cols, fill_value="")
            display_df.rename(columns={
                'position': 'Pos', 'bib': 'Nr.', 'name': 'Name', 
                'distance': 'Distanz (mi)', 'speed': 'Geschw. (mph)', 
                'gap_to_fritz': 'Abstand zu Fritz'
            }, inplace=True)
            
            def highlight_fritz(row):
                return ['background-color: #ffd700'] * len(row) if row.is_fritz else [''] * len(row)
            
            st.dataframe(display_df.style.apply(highlight_fritz, axis=1), 
                         use_container_width=True, height=800,
                         column_config={"is_fritz": None}) # Versteckt die Hilfsspalte stabil

        with tab2:
            st.subheader("Live Positionen auf der Karte")
            map_df = df[(df['lat'] != 0) & (df['lon'] != 0)]
            if not map_df.empty:
                m = folium.Map(location=[map_df['lat'].mean(), map_df['lon'].mean()], zoom_start=5)
                for _, r in map_df.iterrows():
                    folium.Marker([r['lat'], r['lon']], 
                                  popup=f"<b>{r['name']}</b><br>Pos: #{r['position']}<br>Dist: {r['distance']:.1f} mi",
                                  tooltip=f"#{r['position']} {r['name']}",
                                  icon=folium.Icon(color='gold' if r['is_fritz'] else 'blue', 
                                                   icon='star' if r['is_fritz'] else 'bicycle', prefix='fa')).add_to(m)
                st_folium(m, height=600, width=None)

        with tab3:
            st.subheader("Top 10 nach Distanz")
            top10 = df.head(10).sort_values('distance', ascending=True)
            fig = px.bar(top10, y='name', x='distance', orientation='h', text='distance',
                         labels={'name': 'Fahrer', 'distance': 'Distanz (Meilen)'})
            fig.update_traces(texttemplate='%{text:.1f} mi', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("Es konnten keine verarbeitbaren Daten gefunden werden.")

    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
