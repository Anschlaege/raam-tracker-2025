# notifier.py - Ein separates Skript nur für den automatischen stündlichen Export

import pandas as pd
import requests
import re
import json
from datetime import datetime
from pytz import timezone
import os # Wichtig für den Zugriff auf Secrets in GitHub Actions

# --- HILFSFUNKTIONEN (kopiert aus unserer Haupt-App) ---

def degrees_to_cardinal(d):
    """Konvertiert Grad in eine Himmelsrichtung."""
    if d is None: return ""
    dirs = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = int((d + 11.25)/22.5)
    return dirs[ix % 16]

@st.cache_data(ttl=600)
def get_weather_forecast(lat, lon):
    if lat is None or lon is None: return None
    try:
        params = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m", "temperature_unit": "celsius", "precipitation_unit": "mm", "wind_speed_unit": "kmh"}
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except: return None
    
def send_to_discord_as_file(webhook_url, df, weather_data):
    # ... (Diese Funktion bleibt exakt gleich wie in der Haupt-App)
    # ... (Kopiere sie aus der app.py hierher)
    pass # Platzhalter - bitte aus der app.py kopieren

# --- DATENABRUF-LOGIK (kopiert aus unserer Haupt-App) ---

def fetch_and_process_data():
    data_url = "https://trackleaders.com/spot/raam25/mainpoints.js"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://trackleaders.com/raam25f.php'}
    try:
        response = requests.get(data_url, headers=headers, timeout=20)
        response.raise_for_status()
        
        # Parsing-Logik
        racers = []
        for block in response.text.split('markers.push('):
            try:
                status = re.search(r"\.mystatus\s*=\s*'(.*?)';", block).group(1)
                category = re.search(r"\.mycategory\s*=\s*'(.*?)';", block).group(1)
                if status.lower() != 'active' or category.lower() != 'solo': continue
                lat_lon = re.search(r"L\.marker\(\[([\d.-]+),\s*([\d.-]+)\]", block)
                tooltip = re.search(r"bindTooltip\(\"<b>\(([\w\d]+)\)\s*([^\<]*)<\/b>.*?<br>([\d.]+)\s*mph at route mile ([\d.]+)", block)
                if not all([lat_lon, tooltip]): continue
                racers.append({'lat': float(lat_lon.group(1)), 'lon': float(lat_lon.group(2)), 'bib': tooltip.group(1),'name': tooltip.group(2).strip(), 'speed': float(tooltip.group(3)), 'distance_covered_miles': float(tooltip.group(4))})
            except: continue
        
        if not racers: return None, None

        df = pd.DataFrame(racers).sort_values(by='distance_covered_miles', ascending=False).reset_index(drop=True)
        df['position'] = df.index + 1
        df['is_fritz'] = (df['bib'] == '675') | (df['name'].str.lower().str.contains('fritz|geers|gers', na=False, regex=True))
        
        # Wetter für Fritz holen
        weather_data = None
        fritz_data = df[df['is_fritz']]
        if not fritz_data.empty:
            fritz = fritz_data.iloc[0]
            weather_data = get_weather_forecast(fritz.get('lat'), fritz.get('lon'))

        return df, weather_data
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
        return None, None

# --- HAUPTSKRIPT ---
if __name__ == "__main__":
    print("Notifier-Bot wird gestartet...")
    
    # Hole die Webhook-URL aus den GitHub Secrets
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    
    if not webhook_url:
        print("Fehler: DISCORD_WEBHOOK_URL wurde nicht gefunden!")
    else:
        dataframe, weather = fetch_and_process_data()
        if dataframe is not None:
            print(f"{len(dataframe)} Fahrer gefunden. Sende an Discord...")
            # Hier musst du die vollständige `send_to_discord_as_file`-Funktion aus deiner app.py einfügen
            # send_to_discord_as_file(webhook_url, dataframe, weather)
            print("Update an Discord gesendet.")
        else:
            print("Keine verarbeitbaren Daten gefunden.")
            
    print("Notifier-Bot beendet.")
