import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# 0. SEITEN-KONFIGURATION
# ==========================================
st.set_page_config(
    page_title="SEO Dashboard",
    page_icon="📈",
    layout="wide"
)

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
# HILFSFUNKTION FÜR PROZENTRECHNUNG
# ==========================================
def calc_pct_str(curr, prev):
    if prev == 0 and curr == 0: return "0.0%"
    if prev == 0 and curr > 0: return "+100% (Neu)"
    return f"{((curr - prev) / prev) * 100:+.1f}%"

# ==========================================
# 3. DASHBOARD MAIN
# ==========================================
st.empty()
st.title("Performance-Dashboard")
st.caption(f"Domain: {CLIENT_DOMAIN}")

tab1, tab2 = st.tabs(["📊 Google Search Console", "🎯 Ahrefs Analytics & Keywords"])

# ------------------------------------------
# TAB 1: GOOGLE SEARCH CONSOLE
# ------------------------------------------
@st.cache_data(ttl=3600)
def load_gsc_yoy_totals():
    creds_dict = json.loads(GSC_JSON_RAW)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    service = build('searchconsole', 'v1', credentials=credentials)

    end_curr = datetime.now() - timedelta(days=2)
    start_curr = end_curr - timedelta(days=30)
    
    end_prev = end_curr - timedelta(days=365)
    start_prev = start_curr - timedelta(days=365)

    def fetch_totals(s_date, e_date):
        req = {'startDate': s_date.strftime('%Y-%m-%d'), 'endDate': e_date.strftime('%Y-%m-%d')}
        res = service.searchanalytics().query(siteUrl=CLIENT_DOMAIN, body=req).execute()
        return res.get('rows', [{'clicks': 0, 'impressions': 0, 'ctr': 0, 'position': 0}])[0]

    return fetch_totals(start_curr, end_curr), fetch_totals(start_prev, end_prev)

@st.cache_data(ttl=3600)
def load_gsc_timeseries():
    creds_dict = json.loads(GSC_JSON_RAW)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    service = build('searchconsole', 'v1', credentials=credentials)

    end_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=92)).strftime('%Y-%m-%d')
    request_body = {'startDate': start_date, 'endDate': end_date, 'dimensions': ['date']}
    
    response = service.searchanalytics().query(siteUrl=CLIENT_DOMAIN, body=request_body).execute()
    rows = response.get('rows', [])
    if not rows: return None

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['keys'].str[0])
    df = df.sort_values('date')
    df['position'] = df['position'].round(1)
    return df

with tab1:
    st.subheader("Performance (Letzte 30 Tage vs. Vorjahr)")
    
    with st.spinner("Lade GSC-Daten inkl. Vorjahr..."):
        try:
            curr_gsc, prev_gsc = load_gsc_yoy_totals()
            
            c_clicks = curr_gsc.get('clicks', 0)
            p_clicks = prev_gsc.get('clicks', 0)
            c_impr = curr_gsc.get('impressions', 0)
            p_impr = prev_gsc.get('impressions', 0)
            c_ctr = curr_gsc.get('ctr', 0) * 100
            p_ctr = prev_gsc.get('ctr', 0) * 100
            c_pos = curr_gsc.get('position', 0)
            p_pos = prev_gsc.get('position', 0)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Klicks", f"{int(c_clicks):,}".replace(",", "."), delta=calc_pct_str(c_clicks, p_clicks))
            col2.metric("Impressionen", f"{int(c_impr):,}".replace(",", "."), delta=calc_pct_str(c_impr, p_impr))
            col3.metric("Ø CTR", f"{c_ctr:.2f}%", delta=f"{c_ctr - p_ctr:+.2f}% Punkte")
            col4.metric("Ø Position", f"{c_pos:.1f}", delta=f"{c_pos - p_pos:+.1f} Plätze", delta_color="inverse")
            
        except Exception as e:
            st.error(f"Fehler beim Abruf der GSC YoY Daten: {e}")

    st.divider()
    
    df_trend = load_gsc_timeseries()
    if df_trend is not None:
        metrik_option = st.selectbox("Metrik für Zeitverlauf auswählen", ["Durchschnittliche Position", "Organische Klicks", "Impressionen"])
        
        column_map = {"Position": ('position', True), "Klicks": ('clicks', False), "Impressionen": ('impressions', False)}
        for key, (col_name, inv_y) in column_map.items():
            if key in metrik_option:
                column_name, invert_y = col_name, inv_y
        
        fig = px.line(df_trend, x='date', y=column_name, markers=True, title=f"{metrik_option} (Letzte 90 Tage)")
        fig.update_traces(line_color='#4A90E2', line_width=3, marker=dict(size=8, color='#4A90E2'))
        fig.update_layout(xaxis_title="Datum", yaxis_title=metrik_option, template="plotly_white", hovermode="x unified")
        if invert_y: fig.update_yaxes(autorange="reversed")
        
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# TAB 2: AHREFS WEB ANALYTICS & RANK TRACKER
# ------------------------------------------
with tab2:
    st.subheader("🎯 Ahrefs Web Analytics & Keywords")
    
    device_choice = st.radio("Gerät für Rank Tracker auswählen:", ["desktop", "mobile"], horizontal=True)

    if st.button("Ahrefs Daten jetzt live abrufen"):
        headers = {"Authorization": f"Bearer {AHREFS_KEY}", "Accept": "application/json"}
        where_filter = json.dumps({"and": [{"and": [{"field": "source_channel", "is": ["eq", "search"]}]}]})

        # --- Teil 1: Analytics YoY ---
        with st.spinner("Lade organischen Traffic inkl. Vorjahr..."):
            now = datetime.now()
            to_curr = now.strftime('%Y-%m-%dT23:59:59Z')
            from_curr = (now - timedelta(days=30)).strftime('%Y-%m-%dT00:00:00Z')
            
            to_prev = (now - timedelta(days=365)).strftime('%Y-%m-%dT23:59:59Z')
            from_prev = (now - timedelta(days=395)).strftime('%Y-%m-%dT00:00:00Z')

            params_curr = {"from": from_curr, "to": to_curr, "project_id": AHREFS_PROJECT_ID, "where": where_filter}
            params_prev = {"from": from_prev, "to": to_prev, "project_id": AHREFS_PROJECT_ID, "where": where_filter}

            res_curr = requests.get("https://api.ahrefs.com/v3/web-analytics/stats", headers=headers, params=params_curr)
            res_prev = requests.get("https://api.ahrefs.com/v3/web-analytics/stats", headers=headers, params=params_prev)

            if res_curr.status_code == 200 and res_prev.status_code == 200:
                stats_curr = res_curr.json().get("stats") or {}
                stats_prev = res_prev.json().get("stats") or {}

                c_vis, p_vis = int(stats_curr.get("visitors") or 0), int(stats_prev.get("visitors") or 0)
                c_ses, p_ses = int(stats_curr.get("sessions") or 0), int(stats_prev.get("sessions") or 0)
                c_pag, p_pag = int(stats_curr.get("pageviews") or 0), int(stats_prev.get("pageviews") or 0)

                st.markdown("### 👥 Organischer Traffic (30 Tage vs. Vorjahr)")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Einzelne Besucher", f"{c_vis:,}".replace(",", "."), delta=calc_pct_str(c_vis, p_vis))
                col_b.metric("Sitzungen", f"{c_ses:,}".replace(",", "."), delta=calc_pct_str(c_ses, p_ses))
                col_c.metric("Seitenaufrufe", f"{c_pag:,}".replace(",", "."), delta=calc_pct_str(c_pag, p_pag))
            else:
                st.error("Fehler beim Abruf der Ahrefs Analytics Vorjahresdaten.")

        st.divider()

        # --- Teil 2: Rank Tracker Keywords (Exakt wie in Ahrefs API-Export) ---
        with st.spinner("Lade Keyword-Rankings aus Ahrefs..."):
            rank_url = "https://api.ahrefs.com/v3/rank-tracker/overview"
            keywords_raw = []
            res_rank = None
            found_date_str = ""

            # Exakte 1:1 Parameter-Liste aus dem Ahrefs API-Button
            ahrefs_exact_select = (
                "keyword,keyword_difficulty,clicks,cost_per_click,parent_topic,location,language,"
                "target_positions_count,position,position_prev,position_diff,url,url_prev,created_at,"
                "serp_updated,serp_updated_prev,best_position_kind,best_position_kind_previous,"
                "best_position_has_thumbnail,best_position_has_thumbnail_previous,best_position_has_video_preview,"
                "best_position_has_video_preview_previous,tags,country,serp_features,is_branded,is_local,"
                "is_navigational,is_informational,is_commercial,is_transactional,search_type_image,"
                "search_type_news,search_type_video,search_type_web,volume,traffic,traffic_prev,traffic_diff,clicks_per_search"
            )

            # Teste die letzten 7 Tage, falls der heutige Scan noch nicht abgeschlossen ist
            for days_back in range(0, 7):
                curr_d = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
                prev_d = (datetime.now() - timedelta(days=days_back + 30)).strftime('%Y-%m-%d')

                rank_params = {
                    "project_id": AHREFS_PROJECT_ID,
                    "date": curr_d,
                    "date_compared": prev_d,
                    "device": device_choice,
                    "limit": 100,
                    "order_by": "traffic:desc",
                    "select": ahrefs_exact_select
                }

                res_rank = requests.get(rank_url, headers=headers, params=rank_params)

                if res_rank.status_code == 200:
                    json_data = res_rank.json()
                    data_temp = json_data.get("overview") or []
                    if data_temp:
                        keywords_raw = data_temp
                        found_date_str = curr_d
                        break

            if keywords_raw:
                df_rank = pd.DataFrame(keywords_raw)

                def format_trend_arrow(diff):
                    if pd.isna(diff) or diff == 0:
                        return "➖ 0"
                    elif diff > 0:
                        return f"🟢 +{int(diff)}"
                    else:
                        return f"🔴 {int(diff)}"

                df_display = pd.DataFrame()
                df_display["Keyword"] = df_rank.get("keyword", "")
                df_display["Position"] = df_rank.get("position", None)
                
                if "position_diff" in df_rank.columns:
                    df_display["Trend"] = df_rank["position_diff"].apply(format_trend_arrow)
                else:
                    df_display["Trend"] = "➖ 0"

                df_display["Suchvolumen"] = df_rank.get("volume", 0)
                df_display["Traffic"] = df_rank.get("traffic", 0)
                df_display["KD"] = df_rank.get("keyword_difficulty", 0)
                df_display["URL"] = df_rank.get("url", "")

                top10_count = len(df_display[df_display["Position"].fillna(99) <= 10])

                st.markdown(f"### 🏆 Rank Tracker Keywords *(Datenstand: {found_date_str})*")
                st.metric("TRACKED KEYWORDS IN DEN TOP 10", f"{top10_count} Keywords")

                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True
                )
                st.success(f"{len(df_display)} Keywords erfolgreich aus Ahrefs geladen!")
            else:
                if res_rank is not None and res_rank.status_code != 200:
                    st.error(f"Fehler bei Ahrefs Rank Tracker API ({res_rank.status_code}): {res_rank.text}")
                else:
                    st.warning("Keine getrackten Keywords in Ahrefs gefunden.")
