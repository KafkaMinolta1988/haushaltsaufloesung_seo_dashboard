import streamlit as st

# --- 1. DATEN AUS DEM TRESOR LADEN ---
# Wenn diese Daten fehlen, gibt es eine Fehlermeldung
try:
    CLIENT_DOMAIN = st.secrets["client_domain"]
    APP_PASSWORD = st.secrets["app_password"]
except KeyError:
    st.error("Der Tresor (Secrets) ist leer. Bitte richte die Secrets in Streamlit ein!")
    st.stop()

# --- 2. PASSWORT-SCHUTZ ---
st.title("🔒 Login")
st.write("Bitte loggen Sie sich ein, um den SEO-Report zu sehen.")

eingabe = st.text_input("Passwort:", type="password")

if eingabe != APP_PASSWORD:
    st.warning("Warten auf korrektes Passwort...")
    st.stop()  # Stoppt den Aufbau der Seite hier

# --- 3. DAS EIGENTLICHE DASHBOARD ---
# Ab hier ist alles sicher und geschützt!
st.empty() # Macht den Bildschirm sauber
st.success("Erfolgreich eingeloggt!")

st.header(f"📈 SEO-Performance für: {CLIENT_DOMAIN}")
st.write("Hier werden bald die Live-Daten aus der Ahrefs- und Google-API auftauchen.")

# Test-Box
st.info("Das Dashboard läuft perfekt und holt sich die URL aus dem geheimen Tresor!")
