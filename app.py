"""
RAAM 2025 Live Tracker - Debug Version
Zeigt genau was von TrackLeaders kommt
"""

import streamlit as st
import requests
import json
from datetime import datetime

st.set_page_config(
    page_title="RAAM 2025 Debug",
    page_icon="🔧",
    layout="wide"
)

st.title("🔧 RAAM 2025 - TrackLeaders Debug")

# Test verschiedene URLs
urls_to_test = [
    "https://trackleaders.com/raam25.json",
    "https://trackleaders.com/raam25f.php",
    "https://trackleaders.com/raam25f.php?format=json",
    "https://trackleaders.com/raam25/data.json",
    "https://trackleaders.com/api/v1/race/raam25/leaderboard",
    "https://trackleaders.com/spot/raam25.json",
    "https://trackleaders.com/raam25i.php",
    "https://trackleaders.com/raam25m.php"
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://trackleaders.com/raam25'
}

st.markdown("## URL Tests")

for url in urls_to_test:
    with st.expander(f"Test: {url}"):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Status Code", response.status_code)
            with col2:
                st.metric("Content-Type", response.headers.get('content-type', 'N/A'))
            with col3:
                st.metric("Content Length", len(response.content))
            
            # Zeige ersten Teil der Antwort
            st.text("Erste 1000 Zeichen:")
            st.code(response.text[:1000])
            
            # Versuche als JSON zu parsen
            try:
                data = response.json()
                st.success("✅ Gültiges JSON gefunden!")
                st.json(data if isinstance(data, dict) else data[:3] if isinstance(data, list) else data)
            except:
                st.warning("❌ Kein gültiges JSON")
                
                # Suche nach JavaScript-Variablen
                import re
                patterns = [
                    r'var\s+(\w+)\s*=\s*(\[.*?\]);',
                    r'var\s+(\w+)\s*=\s*(\{.*?\});',
                ]
                
                found_vars = []
                for pattern in patterns:
                    matches = re.findall(pattern, response.text, re.DOTALL)
                    for var_name, var_content in matches:
                        found_vars.append(f"{var_name} = {var_content[:100]}...")
                
                if found_vars:
                    st.info(f"JavaScript-Variablen gefunden: {len(found_vars)}")
                    for var in found_vars[:3]:
                        st.code(var)
                        
        except Exception as e:
            st.error(f"Fehler: {str(e)}")

st.markdown("---")
st.markdown("## Iframe Analyse")

# Prüfe ob die Hauptseite ein iframe verwendet
with st.expander("Hauptseite Analyse"):
    try:
        main_response = requests.get("https://trackleaders.com/raam25", headers=headers)
        st.code(main_response.text[:2000])
        
        # Suche nach iframes
        import re
        iframes = re.findall(r'<iframe.*?src="([^"]*)"', main_response.text)
        if iframes:
            st.success(f"Iframes gefunden: {iframes}")
            
    except Exception as e:
        st.error(f"Fehler: {str(e)}")

st.markdown("---")
st.markdown("## Manuelle URL Eingabe")

manual_url = st.text_input("Testen Sie eine eigene URL:", "")
if manual_url and st.button("Testen"):
    try:
        response = requests.get(manual_url, headers=headers, timeout=10)
        st.metric("Status", response.status_code)
        st.text("Antwort:")
        st.code(response.text[:2000])
    except Exception as e:
        st.error(f"Fehler: {str(e)}")

st.markdown("---")
st.info("""
**Nächste Schritte:**
1. Schauen Sie welche URL einen Status 200 mit Daten zurückgibt
2. Prüfen Sie ob JavaScript-Variablen gefunden werden
3. Teilen Sie mir die Ergebnisse mit
""")
