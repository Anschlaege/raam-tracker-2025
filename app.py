"""
RAAM 2025 Live Dashboard
Streamlit-basiertes Dashboard mit Fokus auf Fritz Geers
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import time

# Seiten-Konfiguration
st.set_page_config(
    page_title="RAAM 2025 Live Tracker",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS für Fritz Geers Hervorhebung
st.markdown("""
<style>
    .fritz-highlight {
        background-color: #ffd700;
        padding: 10px;
        border-radius: 5px;
        font-weight: bold;
    }
    .metric-container {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

class RAAMDashboard:
    def __init__(self, db_path: str = "raam_2025.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        
    def get_current_standings(self):
        """Holt aktuelle Rangliste"""
        query = """
        SELECT 
            r.name,
            r.bib_number,
            r.country,
            p.rank,
            p.distance_miles,
            p.speed_mph,
            p.elevation_ft,
            p.checkpoint,
            p.time_behind_leader,
            p.timestamp,
            p.latitude,
            p.longitude,
            p.temperature_f,
            p.weather_condition,
            CASE WHEN r.is_fritz_geers = 1 THEN 1 ELSE 0 END as is_fritz
        FROM racers r
        JOIN positions p ON r.bib_number = p.bib_number
        WHERE p.timestamp = (
            SELECT MAX(timestamp) FROM positions WHERE bib_number = r.bib_number
        )
        AND r.category = 'SOLO'
        ORDER BY p.rank
        """
        return pd.read_sql_query(query, self.conn)
    
    def get_racer_history(self, bib_number: str, hours: int = 24):
        """Holt Historie eines Fahrers"""
        query = """
        SELECT * FROM positions 
        WHERE bib_number = ? 
        AND timestamp > datetime('now', '-{} hours')
        ORDER BY timestamp
        """.format(hours)
        return pd.read_sql_query(query, self.conn, params=[bib_number])
    
    def get_checkpoint_times(self):
        """Holt Checkpoint-Zeiten"""
        query = """
        SELECT 
            r.name,
            c.checkpoint_name,
            c.arrival_time,
            c.rest_duration_minutes
        FROM checkpoints c
        JOIN racers r ON c.bib_number = r.bib_number
        WHERE r.category = 'SOLO'
        ORDER BY c.arrival_time DESC
        LIMIT 50
        """
        return pd.read_sql_query(query, self.conn)

# Dashboard initialisieren
dashboard = RAAMDashboard()

# Sidebar
st.sidebar.title("🚴 RAAM 2025 Tracker")
st.sidebar.markdown("---")

# Auto-Refresh
auto_refresh = st.sidebar.checkbox("Auto-Refresh (30 Sek)", value=True)
if auto_refresh:
    time_placeholder = st.sidebar.empty()
    time_placeholder.text(f"Update: {datetime.now().strftime('%H:%M:%S')}")
    time.sleep(30)
    st.rerun()

# Fritz Geers Filter
highlight_fritz = st.sidebar.checkbox("⭐ Fritz Geers hervorheben", value=True)

# Zeitbereich für Historie
time_range = st.sidebar.slider(
    "Historie (Stunden)",
    min_value=6,
    max_value=168,
    value=24,
    step=6
)

# Hauptbereich
st.title("🏆 Race Across America 2025 - Live Tracking")
st.markdown(f"*Letzte Aktualisierung: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}*")

# Aktuelle Standings laden
standings_df = dashboard.get_current_standings()

# Fritz Geers finden
fritz_data = standings_df[standings_df['is_fritz'] == 1]
if not fritz_data.empty:
    fritz_row = fritz_data.iloc[0]
    
    # Fritz Geers Highlight Box
    st.markdown("### ⭐ Fritz Geers Status")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Position", f"#{int(fritz_row['rank'])}")
    with col2:
        st.metric("Distanz", f"{fritz_row['distance_miles']:.1f} mi")
    with col3:
        st.metric("Geschwindigkeit", f"{fritz_row['speed_mph']:.1f} mph")
    with col4:
        st.metric("Höhe", f"{fritz_row['elevation_ft']:,} ft")
    with col5:
        st.metric("Rückstand", fritz_row['time_behind_leader'] or "Führend!")
    
    if fritz_row['weather_condition']:
        st.info(f"🌡️ Wetter bei Fritz: {fritz_row['temperature_f']:.0f}°F, {fritz_row['weather_condition']}")

st.markdown("---")

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺️ Live Karte", 
    "📊 Rangliste", 
    "📈 Statistiken", 
    "🏁 Checkpoints",
    "📊 Analyse"
])

with tab1:
    st.subheader("Live Positionen aller Solo-Fahrer")
    
    # Folium Karte erstellen
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)  # USA Mitte
    
    # Route (vereinfacht - normalerweise würden Sie GPX laden)
    route_points = [
        [33.7490, -118.2923],  # Los Angeles (Start)
        [38.5816, -121.4944],  # Sacramento
        [39.7392, -104.9903],  # Denver
        [39.0997, -94.5786],   # Kansas City
        [38.6270, -90.1994],   # St. Louis
        [39.7684, -86.1581],   # Indianapolis
        [39.9612, -82.9988],   # Columbus
        [40.4406, -79.9959],   # Pittsburgh
        [39.2904, -76.6122]    # Baltimore (Ziel)
    ]
    
    # Route zeichnen
    folium.PolyLine(route_points, color="blue", weight=3, opacity=0.8).add_to(m)
    
    # Fahrer-Positionen
    for _, racer in standings_df.iterrows():
        if pd.notna(racer['latitude']) and pd.notna(racer['longitude']):
            # Icon und Farbe
            if racer['is_fritz'] == 1 and highlight_fritz:
                icon_color = 'gold'
                icon = 'star'
                prefix = '⭐ '
            else:
                icon_color = 'blue'
                icon = 'bicycle'
                prefix = ''
            
            # Popup-Text
            popup_text = f"""
            <b>{prefix}{racer['name']}</b><br>
            Position: #{int(racer['rank'])}<br>
            Distanz: {racer['distance_miles']:.1f} mi<br>
            Geschw.: {racer['speed_mph']:.1f} mph<br>
            Checkpoint: {racer['checkpoint'] or 'Unterwegs'}<br>
            Aktualisiert: {racer['timestamp']}
            """
            
            folium.Marker(
                [racer['latitude'], racer['longitude']],
                popup=popup_text,
                tooltip=f"{prefix}{racer['name']} (#{int(racer['rank'])})",
                icon=folium.Icon(color=icon_color, icon=icon)
            ).add_to(m)
    
    # Karte anzeigen
    st_folium(m, height=600, width=None)

with tab2:
    st.subheader("📊 Aktuelle Rangliste - Solo Kategorie")
    
    # Ranglisten-Tabelle vorbereiten
    display_df = standings_df[[
        'rank', 'name', 'country', 'distance_miles', 'speed_mph', 
        'elevation_ft', 'checkpoint', 'time_behind_leader', 'is_fritz'
    ]].copy()
    
    # Spalten umbenennen
    display_df.columns = [
        'Pos', 'Name', 'Land', 'Distanz (mi)', 'Geschw. (mph)', 
        'Höhe (ft)', 'Checkpoint', 'Rückstand', 'is_fritz'
    ]
    
    # Fritz Geers Styling
    def highlight_fritz(row):
        if row['is_fritz'] == 1 and highlight_fritz:
            return ['background-color: #ffd700'] * len(row)
        return [''] * len(row)
    
    # Tabelle ohne is_fritz Spalte anzeigen
    styled_df = display_df.drop('is_fritz', axis=1).style.apply(highlight_fritz, axis=1)
    st.dataframe(styled_df, use_container_width=True, height=600)
    
    # Download-Button
    csv = display_df.drop('is_fritz', axis=1).to_csv(index=False)
    st.download_button(
        label="📥 Rangliste als CSV herunterladen",
        data=csv,
        file_name=f"raam_rangliste_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

with tab3:
    st.subheader("📈 Leistungsstatistiken")
    
    # Fahrer-Auswahl
    selected_racers = st.multiselect(
        "Fahrer auswählen:",
        options=standings_df['name'].tolist(),
        default=[fritz_row['name']] if not fritz_data.empty else []
    )
    
    if selected_racers:
        # Subplots erstellen
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Geschwindigkeitsverlauf', 'Höhenprofil',
                'Distanz über Zeit', 'Durchschnittsgeschwindigkeit'
            ),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"type": "bar"}]]
        )
        
        colors = px.colors.qualitative.Set1
        
        for idx, racer_name in enumerate(selected_racers):
            racer_bib = standings_df[standings_df['name'] == racer_name]['bib_number'].iloc[0]
            history_df = dashboard.get_racer_history(racer_bib, time_range)
            
            if not history_df.empty:
                color = colors[idx % len(colors)]
                
                # Geschwindigkeit
                fig.add_trace(
                    go.Scatter(
                        x=history_df['timestamp'],
                        y=history_df['speed_mph'],
                        name=racer_name,
                        line=dict(color=color),
                        showlegend=True
                    ),
                    row=1, col=1
                )
                
                # Höhe
                fig.add_trace(
                    go.Scatter(
                        x=history_df['distance_miles'],
                        y=history_df['elevation_ft'],
                        name=racer_name,
                        line=dict(color=color),
                        showlegend=False
                    ),
                    row=1, col=2
                )
                
                # Distanz
                fig.add_trace(
                    go.Scatter(
                        x=history_df['timestamp'],
                        y=history_df['distance_miles'],
                        name=racer_name,
                        line=dict(color=color),
                        showlegend=False
                    ),
                    row=2, col=1
                )
        
        # Durchschnittsgeschwindigkeiten
        avg_speeds = []
        for racer_name in selected_racers:
            racer_data = standings_df[standings_df['name'] == racer_name]
            if not racer_data.empty:
                avg_speeds.append({
                    'Name': racer_name,
                    'Avg Speed': racer_data['speed_mph'].iloc[0]
                })
        
        if avg_speeds:
            avg_df = pd.DataFrame(avg_speeds)
            fig.add_trace(
                go.Bar(
                    x=avg_df['Name'],
                    y=avg_df['Avg Speed'],
                    showlegend=False
                ),
                row=2, col=2
            )
        
        # Layout anpassen
        fig.update_xaxes(title_text="Zeit", row=1, col=1)
        fig.update_xaxes(title_text="Distanz (mi)", row=1, col=2)
        fig.update_xaxes(title_text="Zeit", row=2, col=1)
        fig.update_xaxes(title_text="Fahrer", row=2, col=2)
        
        fig.update_yaxes(title_text="Geschw. (mph)", row=1, col=1)
        fig.update_yaxes(title_text="Höhe (ft)", row=1, col=2)
        fig.update_yaxes(title_text="Distanz (mi)", row=2, col=1)
        fig.update_yaxes(title_text="Ø Geschw. (mph)", row=2, col=2)
        
        fig.update_layout(height=800, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Bitte wählen Sie mindestens einen Fahrer aus.")

with tab4:
    st.subheader("🏁 Checkpoint-Zeiten")
    
    checkpoint_df = dashboard.get_checkpoint_times()
    
    if not checkpoint_df.empty:
        # Checkpoint-Tabelle
        st.dataframe(checkpoint_df, use_container_width=True)
        
        # Checkpoint-Analyse
        st.markdown("### Durchschnittliche Ruhezeiten")
        avg_rest = checkpoint_df.groupby('checkpoint_name')['rest_duration_minutes'].mean()
        
        fig_rest = px.bar(
            x=avg_rest.index,
            y=avg_rest.values,
            labels={'x': 'Checkpoint', 'y': 'Ø Ruhezeit (Minuten)'},
            title="Durchschnittliche Ruhezeiten pro Checkpoint"
        )
        st.plotly_chart(fig_rest, use_container_width=True)
    else:
        st.info("Noch keine Checkpoint-Daten verfügbar.")

with tab5:
    st.subheader("📊 Erweiterte Analyse")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Geschwindigkeitsverteilung
        st.markdown("#### Geschwindigkeitsverteilung")
        fig_speed_dist = px.box(
            standings_df,
            y='speed_mph',
            x=['Solo'] * len(standings_df),
            points="all",
            title="Aktuelle Geschwindigkeiten aller Fahrer"
        )
        st.plotly_chart(fig_speed_dist, use_container_width=True)
    
    with col2:
        # Führungswechsel
        st.markdown("#### Top 5 Positionen")
        top5_df = standings_df[standings_df['rank'] <= 5][['rank', 'name', 'distance_miles']]
        
        fig_top5 = px.bar(
            top5_df,
            x='name',
            y='distance_miles',
            color='rank',
            title="Top 5 Fahrer nach Distanz",
            labels={'distance_miles': 'Distanz (Meilen)'}
        )
        st.plotly_chart(fig_top5, use_container_width=True)
    
    # Wetter-Analyse
    st.markdown("### 🌡️ Wetterbedingungen")
    weather_df = standings_df[standings_df['temperature_f'].notna()]
    
    if not weather_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Temperaturkarte
            fig_temp = px.scatter_mapbox(
                weather_df,
                lat='latitude',
                lon='longitude',
                color='temperature_f',
                size='speed_mph',
                hover_data=['name', 'weather_condition'],
                color_continuous_scale='RdYlBu_r',
                mapbox_style='open-street-map',
                title="Temperaturen entlang der Route",
                zoom=3
            )
            fig_temp.update_layout(height=400)
            st.plotly_chart(fig_temp, use_container_width=True)
        
        with col2:
            # Wetter-Statistiken
            st.metric("Ø Temperatur", f"{weather_df['temperature_f'].mean():.1f}°F")
            st.metric("Min/Max Temp", f"{weather_df['temperature_f'].min():.0f}°F / {weather_df['temperature_f'].max():.0f}°F")
            
            # Wetterbedingungen
            conditions = weather_df['weather_condition'].value_counts()
            st.markdown("**Wetterbedingungen:**")
            for condition, count in conditions.items():
                st.write(f"- {condition}: {count} Fahrer")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>🚴 RAAM 2025 Live Tracker | Daten von TrackLeaders.com | 
    Automatische Updates alle 5 Minuten</p>
</div>
""", unsafe_allow_html=True)

# Excel-Export Button in der Sidebar
st.sidebar.markdown("---")
if st.sidebar.button("📊 Excel-Export erstellen"):
    with st.spinner("Erstelle Excel-Export..."):
        # Export-Funktion aufrufen
        from raam_tracker_main import RAAMTracker
        tracker = RAAMTracker()
        export_file = tracker.export_to_excel()
        
        with open(export_file, 'rb') as f:
            st.sidebar.download_button(
                label="📥 Excel herunterladen",
                data=f,
                file_name=export_file,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        st.sidebar.success("Export erstellt!")
