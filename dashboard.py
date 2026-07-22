import streamlit as st
import requests
import json  # <-- Neu hinzugefügt
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build


# ==========================================
# 1. DATEN AUS DEM TRESOR LADEN
# ==========================================
try:
    CLIENT_DOMAIN = st.secrets["client_domain"]
    APP_PASSWORD = st.secrets["app_password"]
    AHREFS_KEY = st.secrets["ahrefs_api_key"]
    GSC_JSON_RAW = st.secrets["gsc_json"]  # <-- Geändert
except KeyError:
    st.error("Der Tresor (Secrets) ist unvollständig. Bitte überprüfe deine Secrets in Streamlit!")
    st.stop()

# ==========================================
# 2. PASSWORT-SCHUTZ
# ==========================================
st.title("🔒 Login")
eingabe = st.text_input("Passwort:", type="password")

if eingabe != APP_PASSWORD:
    st.warning("Warten auf korrektes Passwort...")
    st.stop()

# ==========================================
# 3. DASHBOARD (BEIDE APIS INTEGRATED)
# ==========================================
st.empty()
st.success("Erfolgreich eingeloggt!")
st.header(f"📈 SEO & Performance Dashboard: {CLIENT_DOMAIN}")

# TABS FÜR DIE SAUBERE TRENNUNG
tab1, tab2 = st.tabs(["📊 Google Search Console", "🔗 Ahrefs Metriken"])

# ------------------------------------------
# TAB 1: GOOGLE SEARCH CONSOLE
# ------------------------------------------
with tab1:
    st.subheader("Performance der letzten 30 Tage (GSC)")
    
    if st.button("GSC Daten jetzt live abrufen"):
        with st.spinner("Verbinde mit Google Search Console..."):
            try:
                # Login bei Google über die Secrets
                creds_dict = dict(GSC_SECRETS)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
                )
                service = build('searchconsole', 'v1', credentials=credentials)

                # Zeitraum berechnen (GSC hat immer ca. 2 Tage Datenverzug)
                end_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=32)).strftime('%Y-%m-%d')

                # Abfrage-Paket schnüren
                request_body = {
                    'startDate': start_date,
                    'endDate': end_date,
                    'dimensions': ['date']
                }

                # Abfrage an Google senden
                response = service.searchanalytics().query(
                    siteUrl=CLIENT_DOMAIN,
                    body=request_body
                ).execute()

                rows = response.get('rows', [])

                if rows:
                    # Kennzahlen aufsummieren und berechnen
                    total_clicks = sum(row['clicks'] for row in rows)
                    total_impressions = sum(row['impressions'] for row in rows)
                    avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
                    avg_position = sum(row['position'] for row in rows) / len(rows)

                    # KPI Boxen anzeigen
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Klicks (30 Tage)", f"{total_clicks:,}".replace(",", "."))
                    col2.metric("Impressionen", f"{total_impressions:,}".replace(",", "."))
                    col3.metric("Ø CTR", f"{avg_ctr:.2f}%")
                    col4.metric("Ø Position", f"{avg_position:.1f}")

                    st.success("GSC-Daten erfolgreich geladen!")
                else:
                    st.warning("Keine Daten gefunden. Prüfe, ob die 'client_domain' in den Secrets exakt mit der GSC-Property übereinstimmt!")

            except Exception as e:
                st.error(f"Fehler bei der Google API: {e}")

# ------------------------------------------
# TAB 2: AHREFS METRIKEN
# ------------------------------------------
with tab2:
    st.subheader("Ahrefs Live-Metriken")
    if st.button("Ahrefs Daten jetzt live abrufen"):
        with st.spinner("Verbinde mit Ahrefs..."):
            url = "https://api.ahrefs.com/v3/site-explorer/metrics"
            headers = {
                "Authorization": f"Bearer {AHREFS_KEY}",
                "Accept": "application/json"
            }
            params = {
                "select": "domain_rating,live_backlinks",
                "target": CLIENT_DOMAIN,
                "date": "2026-07-20"
            }
            
            antwort = requests.get(url, headers=headers, params=params)
            if antwort.status_code == 200:
                daten = antwort.json()
                dr = daten["metrics"].get("domain_rating", "Keine Daten")
                backlinks = daten["metrics"].get("live_backlinks", "Keine Daten")
                
                col1, col2 = st.columns(2)
                col1.metric("Domain Rating (DR)", dr)
                col2.metric("Live Backlinks", backlinks)
                st.success("Ahrefs-Daten erfolgreich geladen!")
            else:
                st.error(f"Fehler! Ahrefs meldet: {antwort.text}")
