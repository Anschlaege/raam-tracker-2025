"""
RAAM 2025 Live Dashboard - Version 3
Nutzt den direkten JSON/API-Abruf für maximale Stabilität.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from datetime import datetime
import requests
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
    .fritz-highlight {
        background-color: #ffd700;
        padding: 10px;
        border-radius: 5px;
        font-weight: bold;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)


# --- NEUE DATENABRUF-FUNKTIONEN (API-VERSION) ---

@st.cache_data(ttl=45)  # Kürzerer Cache, da der Abruf schneller und stabiler ist
def fetch_trackleaders_data():
    """
    Holt Live-Daten direkt von der RAAM 2025 JSON-Datenquelle.
    Diese Methode ist stabiler als HTML-Scraping.
    """
    # Dies ist die direkte URL zur JSON-Datei, die die Webseite selbst verwendet.
    json_data_url = "https://trackleaders.com/spot/raam25/full.json"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Referer': 'https://trackleaders.com/raam25f.php',
        'Accept': 'application/json, text/javascript, */*; q=0.01'
    }
    
    try:
        response = requests.get(json_data_url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data and 'features' in data:
                return parse_geojson_data(data['features'])
            else:
                st.error("JSON-Datenquelle ist leer oder hat ein unerwartetes Format.")
                return None
        else:
            st.error(f"Fehler beim Abrufen der Datenquelle. Status Code: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Netzwerkfehler beim Abrufen der JSON-Daten: {e}")
        return None
    except json.JSONDecodeError:
        st.error("Fehler beim Verarbeiten der JSON-Antwort. Die Daten sind möglicherweise fehlerhaft.")
        return None
    return None

def parse_geojson_data(features):
    """Konvertiert TrackLeaders GeoJSON-Daten in ein einheitliches Format."""
    racers = []
    for item in features:
        props = item.get('properties', {})
        coords = item.get('geometry', {}).get('coordinates', [0, 0])

        if 'name' in props and 'cat' in props:
            if 'solo' in props.get('cat', '').lower():
                racer = {
                    'name': props.get('name', 'N/A'),
                    'bib': str(props.get('bib', '')),
                    'category': props.get('cat', 'SOLO'),
                    'position': 999,
                    'distance': float(props.get('dist', 0)),
                    'speed': float(props.get('spd', 0)),
                    'location': props.get('loc', ''),
                    'lat': float(coords[1]) if coords else 0,
                    'lon': float(coords[0]) if coords else 0,
                    'time_behind': props.get('gap', ''),
                    'elapsed_time': props.get('elapsed', ''),
                    'last_update': props.get('ts', '') 
                }
                racers.append(racer)

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
    if not racers_data:
        return pd.DataFrame()
    df = pd.DataFrame(racers_data)
    df['is_fritz'] = df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True)
    df = df.sort_values('position')
    df['data_timestamp'] = datetime.now()
    return df

def calculate_statistics(df):
    """Berechnet zusätzliche Statistiken."""
    if df.empty:
        return df
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
    st.sidebar.info(
        "**Live-Daten** von TrackLeaders\n\n"
        "**Fritz Geers** wird mit ⭐ hervorgehoben"
    )
    
    st.title("🏆 Race Across America 2025 - Live Tracking")
    
    with st.spinner("Lade Live-Daten von TrackLeaders..."):
        racers_data = fetch_trackleaders_data()
    
    if racers_data:
        df = create_dataframe(racers_data)
        df = calculate_statistics(df)
        
        st.markdown(f"*Aktualisiert: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")
        
        if df.empty:
            st.warning("Keine Solo-Fahrer in den Live-Daten gefunden.")
        else:
            fritz_data = df[df['is_fritz']]
            
            if not fritz_data.empty:
                fritz = fritz_data.iloc[0]
                st.markdown("### ⭐ Fritz Geers Live Status")
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                with col1:
                    st.metric("Position", f"#{fritz['position']}" if fritz['position'] < 999 else "N/A")
                with col2:
                    st.metric("Distanz", f"{fritz['distance']:.1f} mi")
                with col3:
                    st.metric("Geschwindigkeit", f"{fritz['speed']:.1f} mph" if fritz['speed'] > 0 else "N/A")
                with col4:
                    st.metric("Standort", fritz['location'] if fritz['location'] else "Unterwegs")
                with col5:
                    st.metric("Rückstand", fritz.get('gap_miles', 'N/A'))
                with col6:
                    st.metric("Zeit", fritz['elapsed_time'] if fritz['elapsed_time'] else "N/A")
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
                        popup_html = f"""
                        <div style='font-size: 14px;'>
                        <b>{'⭐ ' if racer['is_fritz'] else ''}{racer['name']}</b><br>
                        Position: #{racer['position']}<br>
                        Distanz: {racer['distance']:.1f} mi<br>
                        Geschw.: {racer['speed']:.1f} mph<br>
                        Standort: {racer['location']}<br>
                        Letztes Update: {racer.get('last_update', 'N/A')}
                        </div>
                        """
                        folium.Marker(
                            [racer['lat'], racer['lon']],
                            popup=folium.Popup(popup_html, max_width=300),
                            tooltip=f"{racer['name']} (#{racer['position']})",
                            icon=folium.Icon(color=color, prefix='fa', icon=icon)
                        ).add_to(m)
                    st_folium(m, height=600, width=None)
                else:
                    st.info("Keine GPS-Koordinaten in den Live-Daten verfügbar.")
            
            with tab3:
                st.subheader("Live Statistiken")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Aktive Fahrer", len(df))
                with col2:
                    st.metric("Führender", df.iloc[0]['name'] if not df.empty else "N/A")
                with col3:
                    avg_speed = df[df['speed'] > 0]['speed'].mean()
                    st.metric("Ø Geschwindigkeit", f"{avg_speed:.1f} mph" if avg_speed > 0 else "N/A")
                with col4:
                    max_dist = df['distance'].max()
                    st.metric("Führung", f"{max_dist:.1f} mi")
                
                st.markdown("---")
                
                col1, col2 = st.columns(2)
                with col1:
                    top10 = df.nsmallest(10, 'position')
                    fig_speed = px.bar(top10, x='name', y='speed', color='is_fritz', color_discrete_map={False: 'lightblue', True: 'gold'}, title='Top 10 - Aktuelle Geschwindigkeiten', labels={'speed': 'Geschwindigkeit (mph)', 'name': ''})
                    fig_speed.update_layout(showlegend=False, xaxis_tickangle=-45)
                    st.plotly_chart(fig_speed, use_container_width=True)
                with col2:
                    top10 = df.nsmallest(10, 'position').sort_values('distance', ascending=True)
                    fig_dist = px.bar(top10, y='name', x='distance', orientation='h', color='is_fritz', color_discrete_map={False: 'lightblue', True: 'gold'}, title='Top 10 - Zurückgelegte Distanz', labels={'distance': 'Distanz (Meilen)', 'name': ''})
                    fig_dist.update_layout(showlegend=False)
                    st.plotly_chart(fig_dist, use_container_width=True)
            
            with tab4:
                st.subheader("Rohdaten von TrackLeaders")
                st.caption("Für Debugging und Analyse")
                st.dataframe(df, use_container_width=True)
                json_data = df.to_dict('records')
                json_str = json.dumps(json_data, indent=2, default=str)
                st.download_button("📥 Download JSON", json_str, f"raam_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "application/json")
    
    if auto_refresh:
        st.markdown('<meta http-equiv="refresh" content="45">', unsafe_allow_html=True)
        st.sidebar.info("🔄 Nächstes Update in 45 Sekunden...")

if __name__ == "__main__":
    main()
