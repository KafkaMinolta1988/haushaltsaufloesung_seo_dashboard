import streamlit as st
import requests  # <-- Wichtig: Der "Briefträger" für die API

# ==========================================
# 1. DATEN AUS DEM TRESOR LADEN
# ==========================================
try:
    CLIENT_DOMAIN = st.secrets["client_domain"]
    APP_PASSWORD = st.secrets["app_password"]
    AHREFS_KEY = st.secrets["ahrefs_api_key"] # <-- Neu: Dein Ahrefs-Key
except KeyError:
    st.error("Der Tresor (Secrets) ist unvollständig. Bitte richte die Secrets in Streamlit ein!")
    st.stop()

# ==========================================
# 2. PASSWORT-SCHUTZ
# ==========================================
st.title("🔒 Login")
st.write("Bitte loggen Sie sich ein, um den SEO-Report zu sehen.")

eingabe = st.text_input("Passwort:", type="password")

if eingabe != APP_PASSWORD:
    st.warning("Warten auf korrektes Passwort...")
    st.stop()  # Stoppt den Aufbau der Seite hier

# ==========================================
# 3. DAS EIGENTLICHE DASHBOARD MIT AHREFS
# ==========================================
st.empty() # Macht den Bildschirm unter dem Login sauber
st.success("Erfolgreich eingeloggt!")

st.header(f"📈 SEO-Performance für: {CLIENT_DOMAIN}")
st.write("Hier sind deine Live-Daten direkt aus Ahrefs:")

# Ein Button, damit die Abfrage nicht bei jedem Klick ungewollt API-Credits verbraucht
if st.button("Ahrefs Daten jetzt live abrufen"):
    
    with st.spinner("Verbinde mit Ahrefs..."):
        # Der cURL-Befehl von deinem Screenshot, übersetzt in Python
        url = "https://api.ahrefs.com/v3/site-explorer/metrics"
        headers = {
            "Authorization": f"Bearer {AHREFS_KEY}",
            "Accept": "application/json"
        }
        params = {
            "select": "domain_rating,live_backlinks",
            "target": CLIENT_DOMAIN,
            "date": "2026-07-20" # Ein fixes Datum für diesen ersten Test
        }
        
        # Die Daten werden abgefragt
        antwort = requests.get(url, headers=headers, params=params)
        
        # Wenn alles geklappt hat
        if antwort.status_code == 200:
            daten = antwort.json()
            
            # Die Zahlen aus den Ahrefs-Daten herausfischen
            dr = daten["metrics"].get("domain_rating", "Keine Daten")
            backlinks = daten["metrics"].get("live_backlinks", "Keine Daten")
            
            # Schicke KPI-Boxen anzeigen
            col1, col2 = st.columns(2)
            col1.metric("Domain Rating (DR)", dr)
            col2.metric("Live Backlinks", backlinks)
            
            st.success("Daten erfolgreich geladen!")
            
        else:
            st.error(f"Fehler! Ahrefs meldet: {antwort.text}")
