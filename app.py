"""
RAAM 2025 Live Dashboard - Version 16 (Finaler Debug-Modus)
- Lädt die Zieldatei herunter und zeigt ihren kompletten Inhalt zur Analyse an.
"""

import streamlit as st
import pandas as pd
import requests
import re

# Seiten-Konfiguration
st.set_page_config(
    page_title="RAAM 2025 Live Tracker - Fritz Geers",
    page_icon="🚴",
    layout="wide"
)

# --- DEBUG-FUNKTION: ZEIGT DEN ROHEN INHALT DER DATENDATEI ---
@st.cache_data(ttl=10) # Kurzer Cache für Debugging
def fetch_and_display_raw_data():
    """DEBUG-VERSION: Lädt die Zieldatei herunter und zeigt ihren kompletten Inhalt an."""
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://trackleaders.com/raam25f.php'}

    st.info(f"Versuche, Rohdaten von {data_url} abzurufen...")
    
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        # Löst bei Fehlern wie 404 (Not Found) eine Exception aus
        response.raise_for_status()

        js_content = response.text
        
        st.success("Datei erfolgreich heruntergeladen! Hier ist der Inhalt:")
        
        # WICHTIGSTER TEIL: Zeige den gesamten Inhalt der Datei an
        st.code(js_content, language='javascript')
        
        st.warning("Bitte kopiere den gesamten Text aus dem obigen Code-Feld und sende ihn mir, damit ich den Code final anpassen kann.")
        
        # Wir stoppen hier absichtlich, da wir nur den Inhalt sehen wollen.
        return None

    except requests.exceptions.RequestException as e:
        st.error(f"Netzwerk- oder Verbindungsfehler: {e}")
        return None
    except Exception as e:
        st.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        return None


def main():
    st.title("🔎 Daten-Analyse Modus")
    st.write("Diese Version der App dient nur dazu, die Struktur der Live-Daten zu analysieren.")
    
    fetch_and_display_raw_data()


if __name__ == "__main__":
    main()
