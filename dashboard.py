import io
import json
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ReportLab Bibliotheken für PDF-Generierung
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ==========================================
# 0. SEITEN-KONFIGURATION
# ==========================================
st.set_page_config(page_title="SEO Dashboard", page_icon="📈", layout="wide")

# ==========================================
# 1. DATEN AUS DEM TRESOR LADEN
# ==========================================
try:
  CLIENT_DOMAIN = st.secrets["client_domain"]
  APP_PASSWORD = st.secrets["app_password"]
  AHREFS_KEY = st.secrets["ahrefs_api_key"].strip()
  AHREFS_PROJECT_ID = str(st.secrets["ahrefs_project_id"]).strip()
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
# HILFSFUNKTIONEN
# ==========================================
def calc_pct_str(curr, prev):
  if prev == 0 and curr == 0:
    return "0.0%"
  if prev == 0 and curr > 0:
    return "+100% (Neu)"
  return f"{((curr - prev) / prev) * 100:+.1f}%"


# --- PDF CHART 1: GSC Traffic Verlaufs-Chart ---
def generate_gsc_chart_bytes(df_trend):
  fig, ax = plt.subplots(figsize=(5.8, 2.2), dpi=200)
  if df_trend is not None and not df_trend.empty:
    ax.plot(
        df_trend["date"],
        df_trend["clicks"],
        color="#2563EB",
        linewidth=2,
        label="Traffic",
    )
    ax.fill_between(
        df_trend["date"], df_trend["clicks"], color="#2563EB", alpha=0.15
    )

  ax.set_facecolor("#F8FAFC")
  fig.patch.set_facecolor("#ffffff")
  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)
  ax.grid(axis="y", linestyle="--", alpha=0.5, color="#CBD5E1")
  ax.tick_params(axis="both", colors="#475569", labelsize=7.5)
  ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
  ax.set_title(
      "Organischer Traffic (GSC - Letzte 90 Tage)",
      fontsize=9,
      fontweight="bold",
      color="#0F172A",
      pad=8,
  )

  plt.tight_layout()
  buf = io.BytesIO()
  plt.savefig(buf, format="png", dpi=200, bbox_inches="tight")
  plt.close(fig)
  buf.seek(0)
  return buf


# --- PDF CHART 2: Aufgeräumtes Balkendiagramm (Horizontal) ---
def generate_kw_bar_bytes(df_display):
  p1_3 = len(df_display[df_display["Position"].between(1, 3)])
  p4_10 = len(df_display[df_display["Position"].between(4, 10)])
  p11_20 = len(df_display[df_display["Position"].between(11, 20)])
  p21_plus = len(df_display[df_display["Position"] > 20])

  categories = ["Top 1-3", "Top 4-10", "Top 11-20", "21+"]
  counts = [p1_3, p4_10, p11_20, p21_plus]
  colors_list = ["#16A34A", "#2563EB", "#F59E0B", "#94A3B8"]

  fig, ax = plt.subplots(figsize=(2.8, 2.2), dpi=200)

  bars = ax.barh(
      categories[::-1], counts[::-1], color=colors_list[::-1], height=0.55
  )

  max_val = max(counts) if max(counts) > 0 else 1
  for bar in bars:
    width = bar.get_width()
    ax.text(
        width + (max_val * 0.05),
        bar.get_y() + bar.get_height() / 2,
        f"{int(width)}",
        va="center",
        ha="left",
        fontsize=8,
        fontweight="bold",
        color="#0F172A",
    )

  ax.set_facecolor("#F8FAFC")
  fig.patch.set_facecolor("#ffffff")
  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)
  ax.spines["bottom"].set_visible(False)
  ax.spines["left"].set_color("#CBD5E1")
  ax.xaxis.set_visible(False)
  ax.tick_params(axis="y", colors="#0F172A", labelsize=8)
  ax.set_xlim(0, max_val * 1.3)
  ax.set_title(
      "Keyword-Verteilung",
      fontsize=9,
      fontweight="bold",
      color="#0F172A",
      pad=8,
  )

  plt.tight_layout()
  buf = io.BytesIO()
  plt.savefig(buf, format="png", dpi=200, bbox_inches="tight")
  plt.close(fig)
  buf.seek(0)
  return buf


# --- KUNDEN-PDF REPORT BUILDER (REPORTLAB) ---
def build_live_pdf_report(
    domain,
    gsc_yoy_data,
    ahrefs_analytics_data,
    df_display,
    df_trend,
    device_choice,
):
  pdf_buffer = io.BytesIO()
  doc = SimpleDocTemplate(
      pdf_buffer,
      pagesize=A4,
      leftMargin=36,
      rightMargin=36,
      topMargin=36,
      bottomMargin=36,
  )
  story = []

  PRIMARY_COLOR = colors.HexColor("#0F172A")
  ACCENT_COLOR = colors.HexColor("#2563EB")
  TEXT_COLOR = colors.HexColor("#334155")
  LIGHT_BG = colors.HexColor("#F8FAFC")

  styles = getSampleStyleSheet()

  title_style = ParagraphStyle(
      "T",
      parent=styles["Heading1"],
      fontName="Helvetica-Bold",
      fontSize=22,
      leading=26,
      textColor=PRIMARY_COLOR,
      spaceAfter=4,
  )

  subtitle_style = ParagraphStyle(
      "ST",
      parent=styles["Normal"],
      fontName="Helvetica",
      fontSize=10,
      leading=14,
      textColor=colors.HexColor("#64748B"),
      spaceAfter=12,
  )

  section_heading = ParagraphStyle(
      "SH",
      parent=styles["Heading2"],
      fontName="Helvetica-Bold",
      fontSize=12,
      leading=16,
      textColor=PRIMARY_COLOR,
      spaceBefore=18,
      spaceAfter=10,
  )

  cell_style = ParagraphStyle(
      "C",
      parent=styles["Normal"],
      fontName="Helvetica",
      fontSize=8.5,
      leading=11,
      textColor=TEXT_COLOR,
  )

  cell_header_style = ParagraphStyle(
      "CH",
      parent=styles["Normal"],
      fontName="Helvetica-Bold",
      fontSize=8.5,
      leading=11,
      textColor=colors.white,
  )

  # Header
  today_str = datetime.now().strftime("%d.%m.%Y")
  story.append(Paragraph("SEO & Performance Kundenreport", title_style))
  story.append(
      Paragraph(
          f"Website: <b>{domain}</b> &nbsp;|&nbsp; Stand: {today_str}",
          subtitle_style,
      )
  )
  story.append(
      HRFlowable(
          width="100%", thickness=1.5, color=ACCENT_COLOR, spaceAfter=12
      )
  )

  # Section 1: KPI Summary
  story.append(
      Paragraph(
          "Performance Overview (30 Tage vs. Vorjahr)", section_heading
      )
  )
  c_clicks, p_clicks, c_impr, p_impr = gsc_yoy_data
  c_vis, p_vis, c_pag, p_pag, pages_per_vis_curr, pages_per_vis_prev = (
      ahrefs_analytics_data
  )

  kpi_data = [[
      Paragraph(
          f"<b>Organischer Traffic (GSC)</b><br/><font size=11"
          f" color='#0F172A'><b>{int(c_clicks):,}</b></font><br/><font"
          f" color='#16A34A'>{calc_pct_str(c_clicks, p_clicks)}</font>",
          cell_style,
      ),
      Paragraph(
          f"<b>Impressionen (GSC)</b><br/><font size=11"
          f" color='#0F172A'><b>{int(c_impr):,}</b></font><br/><font"
          f" color='#16A34A'>{calc_pct_str(c_impr, p_impr)}</font>",
          cell_style,
      ),
      Paragraph(
          f"<b>Besucher (Ahrefs)</b><br/><font size=11"
          f" color='#0F172A'><b>{int(c_vis):,}</b></font><br/><font"
          f" color='#16A34A'>{calc_pct_str(c_vis, p_vis)}</font>",
          cell_style,
      ),
      Paragraph(
          f"<b>Ø Seiten / Besucher</b><br/><font size=11"
          f" color='#0F172A'><b>{pages_per_vis_curr:.2f}</b></font><br/><font"
          f" color='#D97706'>{calc_pct_str(pages_per_vis_curr, pages_per_vis_prev)}</font>",
          cell_style,
      ),
  ]]
  kpi_table = Table(kpi_data, colWidths=[130, 130, 130, 133])
  kpi_table.setStyle(
      TableStyle([
          ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
          ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
          ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
          ("PADDING", (0, 0), (-1, -1), 8),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
      ])
  )
  story.append(kpi_table)

  # Section 2: Visual Charts
  story.append(
      Paragraph("Visuelle Trend- & Keyword-Analyse", section_heading)
  )
  gsc_img = Image(generate_gsc_chart_bytes(df_trend), width=320, height=120)
  kw_img = Image(generate_kw_bar_bytes(df_display), width=185, height=120)

  chart_table = Table([[gsc_img, kw_img]], colWidths=[325, 198])
  chart_table.setStyle(
      TableStyle([
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LEFTPADDING", (0, 0), (-1, -1), 0),
          ("RIGHTPADDING", (0, 0), (-1, -1), 0),
      ])
  )
  story.append(chart_table)

  # Section 3: Keyword Rankings 
  story.append(
      Paragraph(
          f"Top Keyword Rankings ({device_choice.capitalize()})",
          section_heading,
      )
  )

  kw_headers = [
      Paragraph("Keyword", cell_header_style),
      Paragraph("Position", cell_header_style),
      Paragraph("Trend", cell_header_style),
      Paragraph("Volumen", cell_header_style),
      Paragraph("Traffic", cell_header_style),
      Paragraph("KD", cell_header_style),
  ]
  kw_table_data = [kw_headers]

  for _, row in df_display.head(100).iterrows():
    trend_raw = str(row["Trend"])

    if "🟢" in trend_raw:
      trend_pdf = f"<font color='#16A34A'><b>{trend_raw.replace('🟢 ', '')}</b></font>"
    elif "🔴" in trend_raw:
      trend_pdf = f"<font color='#DC2626'><b>{trend_raw.replace('🔴 ', '')}</b></font>"
    else:
      trend_pdf = f"<font color='#94A3B8'>{trend_raw.replace('➖ ', '')}</font>"

    kw_table_data.append([
        Paragraph(f"<b>{row['Keyword']}</b>", cell_style),
        Paragraph(str(row["Position"]), cell_style),
        Paragraph(trend_pdf, cell_style), 
        Paragraph(f"{int(row['Suchvolumen']):,}", cell_style),
        Paragraph(f"{int(row['Traffic']):,}", cell_style),
        Paragraph(str(int(row["KD"])), cell_style),
    ])

  kw_table = Table(
      kw_table_data, colWidths=[183, 60, 70, 70, 70, 70], repeatRows=1
  )
  kw_table.setStyle(
      TableStyle([
          ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
          ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
          ("PADDING", (0, 0), (-1, -1), 5),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
      ])
  )
  story.append(kw_table)

  doc.build(story)
  pdf_buffer.seek(0)
  return pdf_buffer


# ==========================================
# 3. DASHBOARD MAIN
# ==========================================
st.empty()
st.title("Performance-Dashboard")
st.caption(f"Domain: {CLIENT_DOMAIN}")

tab1, tab2 = st.tabs(
    ["📊 Google Search Console", "🎯 Ahrefs Analytics & Keywords"]
)


# ------------------------------------------
# TAB 1: GOOGLE SEARCH CONSOLE
# ------------------------------------------
@st.cache_data(ttl=3600)
def load_gsc_yoy_totals():
  creds_dict = json.loads(GSC_JSON_RAW)
  credentials = service_account.Credentials.from_service_account_info(
      creds_dict, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
  )
  service = build("searchconsole", "v1", credentials=credentials)

  end_curr = datetime.now() - timedelta(days=2)
  start_curr = end_curr - timedelta(days=30)

  end_prev = end_curr - timedelta(days=365)
  start_prev = start_curr - timedelta(days=365)

  def fetch_totals(s_date, e_date):
    req = {
        "startDate": s_date.strftime("%Y-%m-%d"),
        "endDate": e_date.strftime("%Y-%m-%d"),
    }
    res = (
        service.searchanalytics().query(siteUrl=CLIENT_DOMAIN, body=req).execute()
    )
    return res.get(
        "rows", [{"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}]
    )[0]

  return fetch_totals(start_curr, end_curr), fetch_totals(start_prev, end_prev)


@st.cache_data(ttl=3600)
def load_gsc_timeseries():
  creds_dict = json.loads(GSC_JSON_RAW)
  credentials = service_account.Credentials.from_service_account_info(
      creds_dict, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
  )
  service = build("searchconsole", "v1", credentials=credentials)

  end_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
  start_date = (datetime.now() - timedelta(days=92)).strftime("%Y-%m-%d")
  request_body = {
      "startDate": start_date,
      "endDate": end_date,
      "dimensions": ["date"],
  }

  response = (
      service.searchanalytics()
      .query(siteUrl=CLIENT_DOMAIN, body=request_body)
      .execute()
  )
  rows = response.get("rows", [])
  if not rows:
    return None

  df = pd.DataFrame(rows)
  df["date"] = pd.to_datetime(df["keys"].str[0])
  df = df.sort_values("date")
  df["position"] = df["position"].round(1)
  return df


with tab1:
  st.subheader("Performance (Letzte 30 Tage vs. Vorjahr)")

  with st.spinner("Lade GSC-Daten inkl. Vorjahr..."):
    try:
      curr_gsc, prev_gsc = load_gsc_yoy_totals()

      c_clicks = curr_gsc.get("clicks", 0)
      p_clicks = prev_gsc.get("clicks", 0)
      c_impr = curr_gsc.get("impressions", 0)
      p_impr = prev_gsc.get("impressions", 0)
      c_ctr = curr_gsc.get("ctr", 0) * 100
      p_ctr = prev_gsc.get("ctr", 0) * 100
      c_pos = curr_gsc.get("position", 0)
      p_pos = prev_gsc.get("position", 0)

      col1, col2, col3, col4 = st.columns(4)
      col1.metric(
          "Organischer Traffic",
          f"{int(c_clicks):,}".replace(",", "."),
          delta=calc_pct_str(c_clicks, p_clicks),
      )
      col2.metric(
          "Impressionen",
          f"{int(c_impr):,}".replace(",", "."),
          delta=calc_pct_str(c_impr, p_impr),
      )
      col3.metric(
          "Ø CTR", f"{c_ctr:.2f}%", delta=f"{c_ctr - p_ctr:+.2f}% Punkte"
      )
      col4.metric(
          "Ø Position",
          f"{c_pos:.1f}",
          delta=f"{c_pos - p_pos:+.1f} Plätze",
          delta_color="inverse",
      )

    except Exception as e:
      st.error(f"Fehler beim Abruf der GSC YoY Daten: {e}")

  st.divider()

  df_trend = load_gsc_timeseries()
  if df_trend is not None:
    metrik_option = st.selectbox(
        "Metrik für Zeitverlauf auswählen",
        [
            "Durchschnittliche Position",
            "Organischer Traffic",
            "Impressionen",
        ],
    )

    column_map = {
        "Position": ("position", True),
        "Traffic": ("clicks", False),
        "Impressionen": ("impressions", False),
    }
    for key, (col_name, inv_y) in column_map.items():
      if key in metrik_option:
        column_name, invert_y = col_name, inv_y

    fig = px.line(
        df_trend,
        x="date",
        y=column_name,
        markers=True,
        title=f"{metrik_option} (Letzte 90 Tage)",
    )
    fig.update_traces(
        line_color="#4A90E2", line_width=3, marker=dict(size=8, color="#4A90E2")
    )
    fig.update_layout(
        xaxis_title="Datum",
        yaxis_title=metrik_option,
        template="plotly_white",
        hovermode="x unified",
    )
    if invert_y:
      fig.update_yaxes(autorange="reversed")

    st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# TAB 2: AHREFS WEB ANALYTICS & RANK TRACKER
# ------------------------------------------
with tab2:
  st.subheader("🎯 Ahrefs Web Analytics & Keywords")

  device_choice = st.radio(
      "Gerät für Rank Tracker auswählen:",
      ["desktop", "mobile"],
      horizontal=True,
  )

  if st.button("Ahrefs Daten jetzt live abrufen"):
    headers = {
        "Authorization": f"Bearer {AHREFS_KEY}",
        "Accept": "application/json",
    }
    where_filter = json.dumps({
        "and": [{"and": [{"field": "source_channel", "is": ["eq", "search"]}]}]
    })

    # --- Teil 1: Analytics YoY ---
    with st.spinner("Lade organischen Traffic inkl. Vorjahr..."):
      now = datetime.now()
      to_curr = now.strftime("%Y-%m-%dT23:59:59Z")
      from_curr = (now - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")

      to_prev = (now - timedelta(days=365)).strftime("%Y-%m-%dT23:59:59Z")
      from_prev = (now - timedelta(days=395)).strftime("%Y-%m-%dT00:00:00Z")

      params_curr = {
          "from": from_curr,
          "to": to_curr,
          "project_id": AHREFS_PROJECT_ID,
          "where": where_filter,
      }
      params_prev = {
          "from": from_prev,
          "to": to_prev,
          "project_id": AHREFS_PROJECT_ID,
          "where": where_filter,
      }

      res_curr = requests.get(
          "https://api.ahrefs.com/v3/web-analytics/stats",
          headers=headers,
          params=params_curr,
      )
      res_prev = requests.get(
          "https://api.ahrefs.com/v3/web-analytics/stats",
          headers=headers,
          params=params_prev,
      )

      if res_curr.status_code == 200 and res_prev.status_code == 200:
        stats_curr = res_curr.json().get("stats") or {}
        stats_prev = res_prev.json().get("stats") or {}

        c_vis, p_vis = int(stats_curr.get("visitors") or 0), int(
            stats_prev.get("visitors") or 0
        )
        c_pag, p_pag = int(stats_curr.get("pageviews") or 0), int(
            stats_prev.get("pageviews") or 0
        )

        pages_per_vis_curr = (c_pag / c_vis) if c_vis > 0 else 0
        pages_per_vis_prev = (p_pag / p_vis) if p_vis > 0 else 0

        st.markdown("### 👥 Organischer Traffic (30 Tage vs. Vorjahr)")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric(
            "Einzelne Besucher",
            f"{c_vis:,}".replace(",", "."),
            delta=calc_pct_str(c_vis, p_vis),
        )
        col_b.metric(
            "Ø Seiten / Besucher",
            f"{pages_per_vis_curr:.2f}",
            delta=calc_pct_str(pages_per_vis_curr, pages_per_vis_prev),
        )
        col_c.metric(
            "Seitenaufrufe",
            f"{c_pag:,}".replace(",", "."),
            delta=calc_pct_str(c_pag, p_pag),
        )
      else:
        st.error("Fehler beim Abruf der Ahrefs Analytics Vorjahresdaten.")

    st.divider()

    # --- Teil 2: Rank Tracker Keywords ---
    with st.spinner("Lade Keyword-Rankings aus Ahrefs..."):
      rank_url = "https://api.ahrefs.com/v3/rank-tracker/overview"

      today_str = datetime.now().strftime("%Y-%m-%d")
      prev_month_str = (datetime.now() - timedelta(days=30)).strftime(
          "%Y-%m-%d"
      )

      ahrefs_exact_select = (
          "keyword,keyword_difficulty,clicks,cost_per_click,parent_topic,location,language,"
          "target_positions_count,position,position_prev,position_diff,url,url_prev,created_at,"
          "serp_updated,serp_updated_prev,best_position_kind,best_position_kind_previous,"
          "best_position_has_thumbnail,best_position_has_thumbnail_previous,best_position_has_video_preview,"
          "best_position_has_video_preview_previous,tags,country,serp_features,is_branded,is_local,"
          "is_navigational,is_informational,is_commercial,is_transactional,search_type_image,"
          "search_type_news,search_type_video,search_type_web,volume,traffic,traffic_prev,traffic_diff,clicks_per_search"
      )

      rank_params = {
          "project_id": AHREFS_PROJECT_ID,
          "date": today_str,
          "date_compared": prev_month_str,
          "device": device_choice,
          "limit": 1000,
          "order_by": "traffic:desc",
          "select": ahrefs_exact_select,
      }

      res_rank = requests.get(rank_url, headers=headers, params=rank_params)

      if res_rank.status_code == 200:
        json_data = res_rank.json()
        keywords_raw = (
            json_data.get("overviews")
            or json_data.get("overview")
            or json_data.get("keywords")
            or []
        )

        if keywords_raw:
          df_rank = pd.DataFrame(keywords_raw)

          # Nur Keywords behalten, die eine tatsächliche Position besitzen
          df_rank["position"] = pd.to_numeric(
              df_rank.get("position"), errors="coerce"
          )
          df_rank = df_rank.dropna(subset=["position"]).copy()

          df_display = pd.DataFrame()
          df_display["Keyword"] = df_rank.get("keyword", "-").fillna("-")
          df_display["Position"] = df_rank["position"].astype(int)

          def format_trend_arrow(diff):
            try:
              d = float(diff)
              if pd.isna(d) or d == 0:
                return "➖ 0"
              elif d < 0:
                return f"🟢 +{abs(int(d))}"
              else:
                return f"🔴 -{abs(int(d))}"
            except:
              return "➖ 0"

          df_display["Trend"] = df_rank.get(
              "position_diff", pd.Series([0] * len(df_rank))
          ).apply(format_trend_arrow)
          df_display["Suchvolumen"] = (
              pd.to_numeric(df_rank.get("volume", 0), errors="coerce")
              .fillna(0)
              .astype(int)
          )
          df_display["Traffic"] = (
              pd.to_numeric(df_rank.get("traffic", 0), errors="coerce")
              .fillna(0)
              .astype(int)
          )
          df_display["KD"] = (
              pd.to_numeric(df_rank.get("keyword_difficulty", 0), errors="coerce")
              .fillna(0)
              .astype(int)
          )
          df_display["URL"] = df_rank.get("url", "-").fillna("-")

          # 1:1 Sortierung exakt nach Ranking (Position 1, 2, 3...)
          df_display = df_display.sort_values(
              by=["Position", "Suchvolumen"], ascending=[True, False]
          ).reset_index(drop=True)

          if not df_display.empty:
            top10_count = len(df_display[df_display["Position"] <= 10])

            st.markdown(f"### 🏆 Rank Tracker Keywords ({device_choice.capitalize()})")
            st.metric(
                "TRACKED KEYWORDS IN DEN TOP 10", f"{top10_count} Keywords"
            )

            st.dataframe(df_display, use_container_width=True, hide_index=True)
            st.success(f"{len(df_display)} gerankte Keywords geladen!")

            st.divider()

            # --- KUNDEN PDF GENERIEREN UND HERUNTERLADEN ---
            gsc_yoy_data = (c_clicks, p_clicks, c_impr, p_impr)
            ahrefs_analytics_data = (
                c_vis,
                p_vis,
                c_pag,
                p_pag,
                pages_per_vis_curr,
                pages_per_vis_prev,
            )

            pdf_bytes = build_live_pdf_report(
                CLIENT_DOMAIN,
                gsc_yoy_data,
                ahrefs_analytics_data,
                df_display,
                df_trend,
                device_choice,
            )

            st.markdown("### 📄 PDF-Export für Kunden")
            st.download_button(
                label="📥 Als PDF-Kundenreport herunterladen",
                data=pdf_bytes,
                file_name=f"SEO_Report_{CLIENT_DOMAIN.replace('https://', '').replace('/', '')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
          else:
            st.warning(f"Keine gerankten Keywords auf {device_choice.capitalize()} gefunden.")
        else:
          st.warning("Keine Keywords in Ahrefs gefunden.")
      else:
        st.error(
            f"Fehler bei Ahrefs Rank Tracker API ({res_rank.status_code}):"
            f" {res_rank.text}"
        )
