import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
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
    GSC_JSON_RAW = st.secrets["gsc_json"]
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
# 3. INTERAKTIVES PERFORMANCE-DASHBOARD
# ==========================================
st.empty()
st.title("Performance-Dashboard")
st.caption(f"Domain: {CLIENT_DOMAIN}")

# GSC Daten automatisch im Hintergrund laden
@st.cache_data(ttl=3600)  # Speichert Daten für 1 Std im Zwischenspeicher
def load_gsc_data():
    creds_dict = json.loads(GSC_JSON_RAW)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    service = build('searchconsole', 'v1', credentials=credentials)

    # Zeitraum: Letzte 90 Tage für schöne Verläufe
    end_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=92)).strftime('%Y-%m-%d')

    request_body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['date']
    }

    response = service.searchanalytics().query(
        siteUrl=CLIENT_DOMAIN,
        body=request_body
    ).execute()

    rows = response.get('rows', [])
    if not rows:
        return None

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['keys'].str[0])
    df = df.sort_values('date')
    df['position'] = df['position'].round(1)
    return df

df = load_gsc_data()

if df is not None:
    # ------------------------------------------
    # METRIK-AUSWAHL DROPDOWN
    # ------------------------------------------
    metrik_option = st.selectbox(
        "Metrik auswählen",
        options=["Durchschnittliche Position (Ranking)", "Organische Klicks", "Impressionen"]
    )

    # Spaltenzuordnung je nach Auswahl
    if "Position" in metrik_option:
        column_name = 'position'
        label_name = 'Durchschnittliche Position'
        invert_y = True  # Platz 1 gehört nach oben!
    elif "Klicks" in metrik_option:
        column_name = 'clicks'
        label_name = 'Klicks'
        invert_y = False
    else:
        column_name = 'impressions'
        label_name = 'Impressionen'
        invert_y = False

    # ------------------------------------------
    # KPI BERECHNUNGEN (Aktuell vs. Trend)
    # ------------------------------------------
    aktueller_wert = df[column_name].iloc[-1]
    start_wert = df[column_name].iloc[0]

    # Trend in Prozent berechnen
    if start_wert != 0:
        if column_name == 'position':
            # Bei Position bedeutet ein kleinerer Wert eine BESSERE Performance!
            trend_pct = ((start_wert - aktueller_wert) / start_wert) * 100
        else:
            trend_pct = ((aktueller_wert - start_wert) / start_wert) * 100
    else:
        trend_pct = 0.0

    # ------------------------------------------
    # INTERAKTIVES PLOTLY DIAGRAMM BUILDEN
    # ------------------------------------------
    fig = px.line(
        df,
        x='date',
        y=column_name,
        markers=True,
        title=f"{label_name} über die Zeit"
    )

    # Design anpassen (Klinisches Blau / Schlicht)
    fig.update_traces(
        line_color='#4A90E2',
        line_width=3,
        marker=dict(size=8, color='#4A90E2')
    )
    
    fig.update_layout(
        xaxis_title="Datum",
        yaxis_title=label_name,
        template="plotly_white",
        hovermode="x unified"
    )

    # Falls Ranking ausgewählt: Y-Achse umdrehen (Platz 1 oben)
    if invert_y:
        fig.update_yaxes(autorange="reversed")

    # Diagramm in Streamlit rendern
    st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------
    # KPI-METRIKEN UNTER DEM GRAPHEN
    # ------------------------------------------
    col1, col2 = st.columns(2)
    
    if column_name == 'position':
        col1.metric("AKTUELLER RANKING-DURCHSCHNITT", f"{aktueller_wert:.1f}")
    else:
        col1.metric("AKTUELLER WERT", f"{int(aktueller_wert):,}".replace(",", "."))

    col2.metric("PERFORMANCE-TREND", f"{trend_pct:+.1f}%")

else:
    st.warning("Keine Daten in der Google Search Console gefunden. Prüfe die URL-Schreibweise in den Secrets.")
