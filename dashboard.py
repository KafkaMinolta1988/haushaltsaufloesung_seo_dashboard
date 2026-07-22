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
    AHREFS_PROJECT_ID = st.secrets["ahrefs_project_id"]
    GSC_JSON_RAW = st.secrets["gsc_json"]
except KeyError as e:
    st.error(f"Fehler im Tresor (Secrets): Der Schlüssel '{e}' fehlt!")
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
# 3. DASHBOARD MAIN
# ==========================================
st.empty()
st.title("Performance-Dashboard")
st.caption(f"Domain: {CLIENT_DOMAIN}")

tab1, tab2 = st.tabs(["📊 Google Search Console (Trend)", "🎯 Ahrefs Analytics & Keywords"])

# ------------------------------------------
# TAB 1: GOOGLE SEARCH CONSOLE TREND
# ------------------------------------------
@st.cache_data(ttl=3600)
def load_gsc_timeseries():
    creds_dict = json.loads(GSC_JSON_RAW)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    service = build('searchconsole', 'v1', credentials=credentials)

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

with tab1:
    df_trend = load_gsc_timeseries()
    if df_trend is not None:
        metrik_option = st.selectbox(
            "Metrik auswählen",
            options=["Durchschnittliche Position (Ranking)", "Organische Klicks", "Impressionen"]
        )

        if "Position" in metrik_option:
            column_name = 'position'
            label_name = 'Durchschnittliche Position'
            invert_y = True
        elif "Klicks" in metrik_option:
            column_name = 'clicks'
            label_name = 'Klicks'
            invert_y = False
        else:
            column_name = 'impressions'
            label_name = 'Impressionen'
            invert_y = False

        fig = px.line(
            df_trend, x='date', y=column_name, markers=True,
            title=f"{label_name} über die Zeit"
        )
        fig.update_traces(line_color='#4A90E2', line_width=3, marker=dict(size=8, color='#4A90E2'))
        fig.update_layout(xaxis_title="Datum", yaxis_title=label_name, template="plotly_white", hovermode="x unified")
        if invert_y:
            fig.update_yaxes(autorange="reversed")

        st.plotly_chart(fig, use_container_width=True)

        # KPI BERECHNUNGEN MIT GRÜNEN/ROTEN PFEILEN
        aktueller_wert = df_trend[column_name].iloc[-1]
        start_wert = df_trend[column_name].iloc[0]

        col1, col2 = st.columns(2)
        if column_name == 'position':
            # Bei Position ist ein SINKENDER Wert positiv!
            diff_pos = start_wert - aktueller_wert
            trend_pct = ((start_wert - aktueller_wert) / start_wert * 100) if start_wert != 0 else 0
            
            col1.metric("AKTUELLER RANKING-DURCHSCHNITT", f"{aktueller_wert:.1f}")
            # delta_color="inverse" sorgt dafür, dass negativer Positionswert (z.B. von Platz 15 auf Platz 8) grün angezeigt wird
            col2.metric(
                "PERFORMANCE-TREND", 
                f"{aktueller_wert:.1f}", 
                delta=f"{trend_pct:+.1f}% (Veränderung)",
                delta_color="normal" if trend_pct >= 0 else "inverse"
            )
        else:
            trend_pct = ((aktueller_wert - start_wert) / start_wert * 100) if start_wert != 0 else 0
            col1.metric("AKTUELLER WERT", f"{int(aktueller_wert):,}".replace(",", "."))
            col2.metric(
                "PERFORMANCE-TREND", 
                f"{int(aktueller_wert):,}".replace(",", "."), 
                delta=f"{trend_pct:+.1f}%"
            )

# ------------------------------------------
# TAB 2: AHREFS WEB ANALYTICS & RANK TRACKER
# ------------------------------------------
with tab2:
    st.subheader("🎯 Ahrefs Web Analytics & Keywords")
    
    if st.button("Ahrefs Daten jetzt live abrufen"):
        headers = {
            "Authorization": f"Bearer {AHREFS_KEY}",
            "Accept": "application/json"
        }

        # --- Teil 1: Organischer Traffic aus Ahrefs Web Analytics ---
        with st.spinner("Lade organischen Traffic aus Ahrefs Web Analytics..."):
            to_date = datetime.now().strftime('%Y-%m-%dT23:59:59Z')
            from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT00:00:00Z')

            where_filter = json.dumps({
                "and": [
                    {
                        "and": [
                            {"field": "source_channel", "is": ["eq", "search"]}
                        ]
                    }
                ]
            })

            analytics_url = "https://api.ahrefs.com/v3/web-analytics/stats"
            analytics_params = {
                "from": from_date,
                "to": to_date,
                "project_id": AHREFS_PROJECT_ID,
                "where": where_filter
            }

            res_analytics = requests.get(analytics_url, headers=headers, params=analytics_params)

            if res_analytics.status_code == 200:
                stats_raw = res_analytics.json().get("stats") or {}
                
                # ABFANGEN VON NONE-WERTE (Verhindert den ValueError)
                visitors = int(stats_raw.get("visitors") or 0)
                sessions = int(stats_raw.get("sessions") or 0)
                pageviews = int(stats_raw.get("pageviews") or 0)

                st.markdown("### 👥 Organischer Traffic (Letzte 30 Tage)")
                col_a, col_b, col_c = st.columns(3)
                
                # Anzeige mit Tausendertrennzeichen
                col_a.metric("Einzelne Besucher (Visitors)", f"{visitors:,}".replace(",", "."))
                col_b.metric("Sitzungen (Sessions)", f"{sessions:,}".replace(",", "."))
                col_c.metric("Seitenaufrufe (Pageviews)", f"{pageviews:,}".replace(",", "."))
            else:
                st.error(f"Fehler bei Ahrefs Analytics API: {res_analytics.status_code} - {res_analytics.text}")

        st.divider()

        # --- Teil 2: Rank Tracker Keywords mit grünen/roten Pfeilen ---
        with st.spinner("Lade Keyword-Rankings aus Ahrefs..."):
            today_str = datetime.now().strftime('%Y-%m-%d')
            prev_month_str = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

            rank_url = "https://api.ahrefs.com/v3/rank-tracker/overview"
            rank_params = {
                "date": today_str,
                "date_compared": prev_month_str,
                "device": "desktop",
                "limit": 100,
                "order_by": "traffic:desc",
                "project_id": AHREFS_PROJECT_ID,
                "select": "keyword,keyword_difficulty,position,position_prev,position_diff,volume,traffic,url"
            }

            res_rank = requests.get(rank_url, headers=headers, params=rank_params)

            if res_rank.status_code == 200:
                keywords_raw = res_rank.json().get("overview", [])

                if keywords_raw:
                    df_rank = pd.DataFrame(keywords_raw)

                    # Funktion für grüne/rote Pfeile in der Tabelle
                    def format_trend_arrow(diff):
                        if pd.isna(diff) or diff == 0:
                            return "➖ 0"
                        elif diff > 0:
                            return f"🟢 +{int(diff)}"
                        else:
                            return f"🔴 {int(diff)}"

                    # Tabellenspalten aufbereiten
                    df_display = pd.DataFrame()
                    df_display["Keyword"] = df_rank.get("keyword", "")
                    df_display["Position"] = df_rank.get("position", None)
                    
                    # Pfeil-Spalte berechnen
                    if "position_diff" in df_rank.columns:
                        df_display["Trend (30T)"] = df_rank["position_diff"].apply(format_trend_arrow)
                    else:
                        df_display["Trend (30T)"] = "➖ 0"

                    df_display["Suchvolumen"] = df_rank.get("volume", 0)
                    df_display["Traffic"] = df_rank.get("traffic", 0)
                    df_display["KD"] = df_rank.get("keyword_difficulty", 0)
                    df_display["URL"] = df_rank.get("url", "")

                    top10_count = len(df_display[df_display["Position"].fillna(99) <= 10])

                    st.markdown("### 🏆 Rank Tracker Keywords")
                    st.metric("TRACKED KEYWORDS IN DEN TOP 10", f"{top10_count} Keywords")

                    st.dataframe(
                        df_display,
                        use_container_width=True,
                        hide_index=True
                    )
                    st.success("Ahrefs Daten erfolgreich geladen!")
                else:
                    st.warning("Keine Rank Tracker Daten für dieses Projekt gefunden.")
            else:
                st.error(f"Fehler bei Ahrefs Rank Tracker API: {res_rank.status_code} - {res_rank.text}")
