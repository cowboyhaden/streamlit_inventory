import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import csv
import io
import os
from datetime import datetime, date
import gspread

# ==============================================================================
# ##### CONFIGURATION #####
# ==============================================================================
APP_VERSION = "v1.0.0"
APP_TITLE = "Cowboy Coffee"
APP_SUBTITLE = "Inventory Manager"

# Path to items CSV (same directory as app.py)
ITEMS_CSV = os.path.join(os.path.dirname(__file__), "Streamlit Inventory Data - Items.csv")

# Submissions log (written alongside app.py on each submit)
SUBMISSIONS_CSV = os.path.join(os.path.dirname(__file__), "inventory_submissions.csv")

# Color palette (warm earthy tones from .pen design)
COLOR_BG_PAGE         = "#FBF7F2"
COLOR_BG_CARD         = "#FFFFFF"
COLOR_BG_DARK         = "#3D3229"
COLOR_BG_SUCCESS      = "#E8F0E4"
COLOR_TEXT_PRIMARY    = "#2C1810"
COLOR_TEXT_SECONDARY  = "#7A6B5E"
COLOR_TEXT_TERTIARY   = "#A89888"
COLOR_ACCENT_GREEN    = "#7A9B6D"
COLOR_ACCENT_GREEN_LT = "#D4E4CD"
COLOR_ACCENT_BROWN    = "#A68B6B"
COLOR_ACCENT_WARM     = "#C4956A"
COLOR_BORDER_SUBTLE   = "#E8DFD2"
COLOR_HIGHLIGHT       = "#F0EBE3"

# Location cards
LOCATIONS = [
    {"name": "Teton Village", "icon": "🏔️", "subtitle": "Last reported 2 days ago", "accent": COLOR_ACCENT_GREEN_LT},
    {"name": "Town Square",   "icon": "🏢", "subtitle": "Last reported yesterday",   "accent": COLOR_ACCENT_WARM},
]

# Google Sheets integration
SPREADSHEET_ID    = "1int09gdLEXTXnydTLSSLmY-oNj3edG_ZKXgJC2CNZK0"
LOG_WORKSHEET_GID = 1487457430

# Category display config
CATEGORY_META = {
    "Coffee":      {"icon": "☕"},
    "Ingredients": {"icon": "🧃"},
    "Supplies":    {"icon": "📦"},
    "Merch":       {"icon": "🛍️"},
}


# ==============================================================================
# ##### HELPERS #####
# ==============================================================================
def load_categories(csv_path: str) -> list[dict]:
    """
    Parse the items CSV and build the CATEGORIES structure.

    Input type rules (driven by the 'Unit' column):
      - "box fill scale 1 to 10"  → slider  (0–10, step 1)
      - everything else            → stepper (0–Max Inventory, step 1)
    """
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    categories = {}
    for _, row in df.iterrows():
        cat_name = str(row["Category"]).strip()
        item_name = str(row["Item"]).strip()
        max_inv = int(row["Max Inventory"])
        unit = str(row["Unit"]).strip()

        if cat_name not in categories:
            meta = CATEGORY_META.get(cat_name, {"icon": "📋"})
            categories[cat_name] = {"name": cat_name, "icon": meta["icon"], "items": []}

        if "scale 1 to 10" in unit.lower():
            item = {
                "name":    item_name,
                "input":   "slider",
                "unit":    "/ 10",
                "max":     10.0,
                "step":    1.0,
                "default": 0.0,
            }
        else:
            item = {
                "name":    item_name,
                "input":   "stepper",
                "unit":    unit,
                "max":     max_inv,
                "default": 0,
            }

        categories[cat_name]["items"].append(item)

    return list(categories.values())


def get_greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    return "Good evening"


def get_today_str() -> str:
    return date.today().strftime("%A, %B %-d, %Y")


def get_today_short() -> str:
    return date.today().strftime("%b %-d")


def count_reported_items(inventory: dict, categories: list) -> tuple[int, int]:
    """Return (reported_count, total_count).
    An item counts as reported if it has a value > 0 OR is in confirmed_zero."""
    confirmed_zero = getattr(st.session_state, "confirmed_zero", set())
    reported, total = 0, 0
    for cat in categories:
        for item in cat["items"]:
            total += 1
            val = inventory.get(item["name"], item["default"])
            if item["input"] == "slider":
                if float(val) > 0 or item["name"] in confirmed_zero:
                    reported += 1
            else:
                if int(val) > 0 or item["name"] in confirmed_zero:
                    reported += 1
    return reported, total


def format_value(item: dict, value) -> str:
    """Format a value with its unit for review display."""
    if item["input"] == "slider":
        v = float(value) if value else 0.0
        return f"{int(v)} {item['unit']}"
    else:
        v = int(value) if value else 0
        return f"{v} {item['unit']}"


def build_export_csv(location: str, submitted_at: str, inventory: dict, categories: list) -> str:
    """Build a CSV string of the submission for Google Sheets import."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Submitted At", "Location", "Category", "Item", "Value", "Unit"])
    for cat in categories:
        for item in cat["items"]:
            val = inventory.get(item["name"], item["default"])
            if item["input"] == "slider":
                display = int(float(val)) if val else 0
            else:
                display = int(val) if val else 0
            writer.writerow([submitted_at, location, cat["name"], item["name"], display, item["unit"]])
    return output.getvalue()


def append_to_submissions_log(location: str, submitted_at: str, inventory: dict, categories: list):
    """Append this submission as rows to the local submissions log CSV."""
    file_exists = os.path.exists(SUBMISSIONS_CSV)
    with open(SUBMISSIONS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Submitted At", "Location", "Category", "Item", "Value", "Unit"])
        for cat in categories:
            for item in cat["items"]:
                val = inventory.get(item["name"], item["default"])
                display = int(float(val)) if item["input"] == "slider" else int(val) if val else 0
                writer.writerow([submitted_at, location, cat["name"], item["name"], display, item["unit"]])


# ==============================================================================
# ##### UI #####
# ==============================================================================
st.set_page_config(
    page_title="Cowboy Coffee Inventory",
    page_icon="☕",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Load categories from CSV (cached so it only reads once per session)
@st.cache_data
def get_categories():
    return load_categories(ITEMS_CSV)

CATEGORIES = get_categories()

# Session state init
if "screen"          not in st.session_state: st.session_state.screen          = "location"
if "location"        not in st.session_state: st.session_state.location        = None
if "manager_name"    not in st.session_state: st.session_state.manager_name    = ""
if "inventory"       not in st.session_state: st.session_state.inventory       = {}
if "confirmed_zero"  not in st.session_state: st.session_state.confirmed_zero  = set()
if "submitted_time"  not in st.session_state: st.session_state.submitted_time  = None
if "sheets_status"   not in st.session_state: st.session_state.sheets_status   = None  # True/False/None

# Custom CSS — mobile-first, warm design
st.markdown(f"""
<style>
    .stApp {{
        background-color: {COLOR_BG_PAGE};
        max-width: 402px;
        margin: 0 auto;
    }}
    section[data-testid="stSidebar"] {{ display: none; }}
    header[data-testid="stHeader"]   {{ background-color: {COLOR_BG_PAGE}; }}
    .block-container {{
        padding: 1rem 1.2rem 6rem 1.2rem;
        max-width: 402px;
    }}

    /* ── Location card buttons (secondary = default) ── */
    button[data-testid="stBaseButton-secondary"] {{
        background-color: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER_SUBTLE};
        border-radius: 16px;
        padding: 16px 20px;
        text-align: left;
        color: {COLOR_TEXT_PRIMARY};
        font-weight: 600;
        font-size: 16px;
    }}
    button[data-testid="stBaseButton-secondary"]:hover {{
        background-color: #EDE3D5;
        border-color: {COLOR_BORDER_SUBTLE};
    }}

    /* ── Primary / submit buttons ── */
    button[data-testid="stBaseButton-primary"] {{
        border: none !important;
        border-radius: 26px !important;
        height: 52px !important;
        font-size: 16px !important;
        font-weight: 700 !important;
        color: white !important;
        transition: background-color 0.2s ease !important;
    }}

    /* ── Stepper ± buttons: buttons inside a column that has nested sub-columns
          (identified by the stLayoutWrapper in the path, absent for simple dot buttons) ── */
    div[data-testid="stExpander"]
        div[data-testid="stColumn"]
        > div[data-testid="stVerticalBlock"]
        > div[data-testid="stLayoutWrapper"]
        > div[data-testid="stHorizontalBlock"]
        button[data-testid="stBaseButton-secondary"] {{
        background-color: #EDE3D5 !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 4px 0 !important;
        font-size: 20px !important;
        font-weight: 400 !important;
        color: {COLOR_TEXT_PRIMARY} !important;
        min-height: 38px !important;
        height: 38px !important;
    }}
    div[data-testid="stExpander"]
        div[data-testid="stColumn"]
        > div[data-testid="stVerticalBlock"]
        > div[data-testid="stLayoutWrapper"]
        > div[data-testid="stHorizontalBlock"]
        button[data-testid="stBaseButton-secondary"]:hover {{
        background-color: #D9CBBA !important;
        border-color: transparent !important;
    }}
    /* Tighten gap between stepper sub-columns */
    div[data-testid="stExpander"] div[data-testid="stHorizontalBlock"] div[data-testid="stHorizontalBlock"] {{
        gap: 4px !important;
    }}

    /* ── Dot buttons (OOS toggle) ── */
    [data-dot-state] button[data-testid="stBaseButton-secondary"] {{
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        min-height: 0 !important;
        height: 38px !important;
        font-size: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        cursor: pointer !important;
    }}
    /* Hide the button's inner text element — only show the ::before circle */
    [data-dot-state] button[data-testid="stBaseButton-secondary"] p {{
        display: none !important;
    }}
    [data-dot-state] button[data-testid="stBaseButton-secondary"]::before {{
        content: '' !important;
        display: block !important;
        width: 16px !important;
        height: 16px !important;
        border-radius: 50% !important;
        transition: background 0.15s, transform 0.1s !important;
        flex-shrink: 0 !important;
    }}
    /* Gray: not yet reported — matches design's $border-subtle fill */
    [data-dot-state="empty"] button[data-testid="stBaseButton-secondary"]::before {{
        background: {COLOR_BORDER_SUBTLE} !important;
    }}
    [data-dot-state="empty"] button[data-testid="stBaseButton-secondary"]:hover::before {{
        background: {COLOR_TEXT_TERTIARY} !important;
        transform: scale(1.15) !important;
    }}
    /* Red: confirmed out of stock */
    [data-dot-state="oos"] button[data-testid="stBaseButton-secondary"]::before {{
        background: #CC6B5A !important;
    }}
    [data-dot-state="oos"] button[data-testid="stBaseButton-secondary"]:hover::before {{
        background: #B05040 !important;
        transform: scale(1.15) !important;
    }}

    /* ── Slider → green track & thumb ── */
    div[data-testid="stSlider"] [role="slider"] {{
        background-color: {COLOR_ACCENT_GREEN} !important;
        border: 3px solid white !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.15) !important;
    }}
    div[data-baseweb="slider"] [data-testid="stSliderTrack"] > div:nth-child(2) {{
        background: {COLOR_ACCENT_GREEN} !important;
    }}

    /* ── Category expander ── */
    div[data-testid="stExpander"] > details {{
        border: none !important;
        background: transparent !important;
    }}
    div[data-testid="stExpander"] > details > summary {{
        padding: 2px 4px !important;
        border-radius: 8px !important;
        min-height: 44px;
        align-items: center;
    }}
    div[data-testid="stExpander"] > details > summary:hover {{
        background-color: {COLOR_HIGHLIGHT} !important;
    }}
    div[data-testid="stExpander"] > details > summary p {{
        font-size: 15px !important;
        font-weight: 700 !important;
        color: {COLOR_TEXT_PRIMARY} !important;
    }}
    /* Count badge: backtick code in expander label */
    div[data-testid="stExpander"] summary p code {{
        background-color: {COLOR_ACCENT_GREEN_LT} !important;
        color: {COLOR_ACCENT_GREEN} !important;
        border-radius: 11px !important;
        padding: 1px 8px !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        border: none !important;
    }}

    /* ── Progress bar ── */
    div[data-testid="stProgressBar"] > div {{
        background-color: {COLOR_ACCENT_GREEN} !important;
        border-radius: 3px !important;
    }}
    div[data-testid="stProgressBar"] {{
        border-radius: 3px !important;
        height: 6px !important;
    }}

    /* Prevent columns from stacking on narrow viewports */
    div[data-testid="stHorizontalBlock"] > div {{
        min-width: 0 !important;
    }}

    #MainMenu {{ visibility: hidden; }}
    footer    {{ visibility: hidden; }}
    hr {{ border-color: {COLOR_BORDER_SUBTLE}; opacity: 0.4; }}
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# ##### GOOGLE SHEETS #####
# ==============================================================================
@st.cache_data(ttl=300)
def get_last_reported_dates() -> dict:
    """Return {location_name: human_readable_string} from the log sheet.
    Cached for 5 minutes. Falls back to empty dict on any error.
    """
    if "gcp_service_account" not in st.secrets:
        return {}
    try:
        gc      = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        ws      = gc.open_by_key(SPREADSHEET_ID).get_worksheet_by_id(LOG_WORKSHEET_GID)
        records = ws.get_all_records()          # list of dicts, header row = col names

        # Find the most recent date string per location
        latest: dict[str, str] = {}
        for row in records:
            loc = str(row.get("Location", "")).strip()
            d   = str(row.get("Date", "")).strip()
            if loc and d and (loc not in latest or d > latest[loc]):
                latest[loc] = d

        # Format as relative strings
        today   = date.today()
        result  = {}
        for loc, d_str in latest.items():
            try:
                d     = date.fromisoformat(d_str)
                delta = (today - d).days
                if   delta == 0: result[loc] = "Last reported today"
                elif delta == 1: result[loc] = "Last reported yesterday"
                elif delta <  7: result[loc] = f"Last reported {delta} days ago"
                else:            result[loc] = f"Last reported {d.strftime('%b %-d')}"
            except ValueError:
                pass
        return result
    except Exception:
        return {}


def write_to_google_sheets(
    location: str,
    manager_name: str,
    now_dt: datetime,
    inventory: dict,
    categories: list,
    confirmed_zero: set | None = None,
) -> tuple[bool, str]:
    """Append one row per item to the Google Sheet log tab.

    Auth: service account credentials stored in st.secrets["gcp_service_account"].
    Columns written: Date | Time | Location | Manager | Item | Quantity
    OOS items (in confirmed_zero) are logged as 0.
    Returns (success, error_message).
    """
    if "gcp_service_account" not in st.secrets:
        return False, "gcp_service_account not configured in Streamlit secrets."

    confirmed_zero = confirmed_zero or set()

    try:
        gc          = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet   = spreadsheet.get_worksheet_by_id(LOG_WORKSHEET_GID)

        date_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%-I:%M %p")

        rows = []
        for cat in categories:
            for item in cat["items"]:
                if item["name"] in confirmed_zero:
                    qty = 0  # out of stock
                else:
                    val = inventory.get(item["name"], item["default"])
                    qty = int(float(val)) if item["input"] == "slider" else (int(val) if val else 0)
                rows.append([date_str, time_str, location, manager_name, item["name"], qty])

        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        return True, ""

    except Exception as exc:
        return False, str(exc)


# ── SCREEN 1: Location Selection ──────────────────────────────────────────────
def render_location_screen():
    st.markdown(
        f"""<div style="text-align:center; padding:2rem 0 0.5rem 0;">
          <div style="display:inline-block; background:{COLOR_BG_DARK}; border-radius:16px;
                      width:64px; height:64px; line-height:64px; font-size:30px;">☕</div>
          <h2 style="margin:0.4rem 0 0 0; color:{COLOR_TEXT_PRIMARY}; font-weight:800; font-size:24px;">{APP_TITLE}</h2>
          <p style="margin:0; color:{COLOR_TEXT_TERTIARY}; font-size:13px;">{APP_SUBTITLE}</p>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""<div style="text-align:center; padding:1.5rem 0;">
          <p style="margin:0; color:{COLOR_TEXT_PRIMARY}; font-size:20px; font-weight:600;">{get_greeting()}, Manager</p>
          <p style="margin:0.25rem 0 0; color:{COLOR_TEXT_SECONDARY}; font-size:14px;">Select a location to report inventory</p>
        </div>""",
        unsafe_allow_html=True,
    )

    name = st.text_input(
        "Your name",
        value=st.session_state.manager_name,
        placeholder="Enter your name",
        key="name_input",
    )
    st.session_state.manager_name = name.strip()

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    last_reported = get_last_reported_dates()
    for loc in LOCATIONS:
        subtitle = last_reported.get(loc["name"], loc["subtitle"])
        disabled = not st.session_state.manager_name
        if st.button(
            f"{loc['icon']}  **{loc['name']}**\n\n{subtitle}",
            key=f"loc_{loc['name']}",
            use_container_width=True,
            disabled=disabled,
        ):
            st.session_state.location  = loc["name"]
            st.session_state.screen    = "reporting"
            st.session_state.inventory = {}
            st.session_state.sheets_status = None
            st.rerun()

    st.markdown(
        f'<p style="text-align:center; color:{COLOR_TEXT_TERTIARY}; font-size:12px; padding-top:1.5rem;">'
        f'{get_today_str()}</p>',
        unsafe_allow_html=True,
    )


# ── SCREEN 2: Inventory Reporting ─────────────────────────────────────────────
@st.dialog("Items with no quantity")
def _oos_confirm_dialog(unreported: list):
    """Shown when user tries to submit with unreported items.
    Lets them bulk-confirm all as OOS in one tap, or go back to fill them in.
    """
    n = len(unreported)
    st.markdown(
        f"<p style='color:{COLOR_TEXT_SECONDARY}; font-size:14px;'>"
        f"{'This item has' if n == 1 else f'These {n} items have'} no quantity entered. "
        f"Mark {'it' if n == 1 else 'them'} as <strong>out of stock</strong> and continue?</p>",
        unsafe_allow_html=True,
    )
    st.markdown("")
    for name in unreported:
        st.markdown(
            f"<p style='font-size:13px; color:{COLOR_TEXT_PRIMARY}; margin:0.15rem 0;'>• {name}</p>",
            unsafe_allow_html=True,
        )
    st.markdown("")
    col_back, col_confirm = st.columns(2)
    with col_back:
        if st.button("Go Back", use_container_width=True):
            st.rerun()
    with col_confirm:
        if st.button("Mark as Out of Stock", type="primary", use_container_width=True):
            for name in unreported:
                st.session_state.confirmed_zero.add(name)
            st.session_state.screen = "review"
            st.rerun()


def _toggle_confirmed_zero(inventory_key: str):
    """Toggle OOS (confirmed zero) state for an item."""
    cz = st.session_state.confirmed_zero
    if inventory_key in cz:
        cz.discard(inventory_key)
    else:
        cz.add(inventory_key)


def _stepper_decrement(inventory_key: str):
    """Decrement a stepper item (on_click callback), clamped to 0."""
    st.session_state.inventory[inventory_key] = max(
        0, st.session_state.inventory.get(inventory_key, 0) - 1
    )


def _stepper_increment(inventory_key: str, max_val: int):
    """Increment a stepper item, clamped to max_val. Clears OOS flag."""
    st.session_state.confirmed_zero.discard(inventory_key)
    st.session_state.inventory[inventory_key] = min(
        max_val, st.session_state.inventory.get(inventory_key, 0) + 1
    )


# Lucide circle-check icon — matches the design's reported-state dot
_CIRCLE_CHECK_SVG = (
    "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' "
    f"stroke='{COLOR_ACCENT_GREEN}' stroke-width='2.5' "
    "stroke-linecap='round' stroke-linejoin='round'>"
    "<circle cx='12' cy='12' r='10'/>"
    "<polyline points='9 12 11 14.5 15 9.5'/>"
    "</svg>"
)


def render_reporting_screen():
    # Dynamic submit button color
    reported, total = count_reported_items(st.session_state.inventory, CATEGORIES)
    submit_color = COLOR_ACCENT_GREEN if reported == total else "#C4B8A5"
    st.markdown(
        f"<style>button[data-testid='stBaseButton-primary'] "
        f"{{ background-color: {submit_color} !important; }}</style>",
        unsafe_allow_html=True,
    )

    # Header
    col_back, col_title, col_date = st.columns([1, 4, 2])
    with col_back:
        if st.button("←", key="back_to_loc"):
            st.session_state.screen         = "location"
            st.session_state.inventory      = {}
            st.session_state.confirmed_zero = set()
            st.rerun()
    with col_title:
        st.markdown(
            f"<p style='font-size:20px; font-weight:700; color:{COLOR_TEXT_PRIMARY}; margin:0; padding-top:4px;'>"
            f"{st.session_state.location}</p>",
            unsafe_allow_html=True,
        )
    with col_date:
        st.markdown(
            f"<p style='text-align:right; font-size:13px; font-weight:500; color:{COLOR_TEXT_SECONDARY}; margin:0; padding-top:8px;'>"
            f"{get_today_short()}</p>",
            unsafe_allow_html=True,
        )

    # Progress — custom HTML matching design
    reported, total = count_reported_items(st.session_state.inventory, CATEGORIES)
    pct = reported / total if total > 0 else 0
    fill_w = int(pct * 100)
    st.markdown(
        f"""<div style="margin:0.25rem 0 0.75rem;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="color:{COLOR_TEXT_SECONDARY};font-size:12px;font-weight:500;">{reported} of {total} items updated</span>
            <span style="color:{COLOR_ACCENT_GREEN};font-size:12px;font-weight:600;">{fill_w}%</span>
          </div>
          <div style="background:{COLOR_BORDER_SUBTLE};border-radius:3px;height:6px;width:100%;overflow:hidden;">
            <div style="background:{COLOR_ACCENT_GREEN};border-radius:3px;height:6px;width:{fill_w}%;"></div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # JS: MutationObserver to tag dot buttons with data-dot-state for CSS targeting
    components.html("""
    <script>
    (function() {
        var doc = window.parent.document;
        if (window.parent.__ccDotObs) { window.parent.__ccDotObs.disconnect(); }
        function classify() {
            doc.querySelectorAll('button[data-testid="stBaseButton-secondary"]').forEach(function(btn) {
                var t = btn.textContent.trim();
                var w = btn.closest('[data-testid="stButton"]');
                if (!w) return;
                if (t === '\u25cb') { w.setAttribute('data-dot-state','empty'); }
                else if (t === '\u25cf') { w.setAttribute('data-dot-state','oos'); }
                else { w.removeAttribute('data-dot-state'); }
            });
        }
        var obs = new MutationObserver(classify);
        obs.observe(doc.body, {childList:true, subtree:true});
        window.parent.__ccDotObs = obs;
        classify();
    })();
    </script>
    """, height=0, scrolling=False)

    # Categories
    for cat_idx, cat in enumerate(CATEGORIES):
        count = len(cat["items"])
        with st.expander(f"{cat['icon']} **{cat['name']}** `{count}`", expanded=True):
            for item_idx, item in enumerate(cat["items"]):
                key = item["name"]

                # Init value
                if key not in st.session_state.inventory:
                    st.session_state.inventory[key] = item["default"]

                val = st.session_state.inventory[key]
                is_confirmed = key in st.session_state.confirmed_zero
                has_stock = (
                    float(val) > 0 if item["input"] == "slider" else int(val) > 0
                )

                # Dot column: green HTML (has stock) or interactive button (zero)
                # "○" = not yet confirmed zero  "●" = confirmed out of stock
                dot_col, name_col, inp_col = st.columns([0.3, 2.7, 2])
                with dot_col:
                    if has_stock:
                        st.markdown(
                            f"<div style='display:flex;align-items:center;justify-content:center;"
                            f"height:38px;'>{_CIRCLE_CHECK_SVG}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        dot_char = "●" if is_confirmed else "○"
                        st.button(
                            dot_char,
                            key=f"dot_{cat_idx}_{item_idx}",
                            on_click=_toggle_confirmed_zero,
                            args=(key,),
                            use_container_width=True,
                        )
                with name_col:
                    st.markdown(
                        f"<div style='display:flex;align-items:center;height:38px;overflow:hidden;'>"
                        f"<span style='font-size:14px;font-weight:500;color:{COLOR_TEXT_PRIMARY};"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{key}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                if item["input"] == "stepper":
                    with inp_col:
                        minus_col, disp_col, plus_col = st.columns([1, 1, 1])
                        with minus_col:
                            st.button(
                                "−",
                                key=f"minus_{cat_idx}_{item_idx}",
                                on_click=_stepper_decrement,
                                args=(key,),
                                use_container_width=True,
                            )
                        with disp_col:
                            if is_confirmed and not has_stock:
                                disp_text  = "OOS"
                                disp_color = "#CC6B5A"
                                disp_size  = "12px"
                            else:
                                disp_text  = str(int(val))
                                disp_color = COLOR_TEXT_PRIMARY
                                disp_size  = "15px"
                            st.markdown(
                                f"<div style='text-align:center;font-size:{disp_size};font-weight:600;"
                                f"color:{disp_color};padding:7px 0;'>{disp_text}</div>",
                                unsafe_allow_html=True,
                            )
                        with plus_col:
                            st.button(
                                "+",
                                key=f"plus_{cat_idx}_{item_idx}",
                                on_click=_stepper_increment,
                                args=(key, item["max"]),
                                use_container_width=True,
                            )
                elif item["input"] == "slider":
                    with inp_col:
                        new_val = st.slider(
                            key,
                            min_value=0,
                            max_value=int(item["max"]),
                            value=int(float(val)),
                            step=1,
                            key=f"slider_{cat_idx}_{item_idx}",
                            label_visibility="collapsed",
                        )
                        if new_val > 0:
                            st.session_state.confirmed_zero.discard(key)
                        st.session_state.inventory[key] = new_val

    st.markdown("")

    # Submit button — always enabled; intercepts if any items are unresolved
    reported, total = count_reported_items(st.session_state.inventory, CATEGORIES)
    all_reported    = reported == total
    if st.button("Submit Inventory", key="submit_inventory", type="primary", use_container_width=True):
        if all_reported:
            st.session_state.screen = "review"
            st.rerun()
        else:
            # Collect items with no qty and no OOS flag
            unreported = [
                item["name"]
                for cat in CATEGORIES
                for item in cat["items"]
                if item["name"] not in st.session_state.confirmed_zero
                and (float(st.session_state.inventory.get(item["name"], item["default"])) == 0
                     if item["input"] == "slider"
                     else int(st.session_state.inventory.get(item["name"], item["default"]) or 0) == 0)
            ]
            _oos_confirm_dialog(unreported)


# ── SCREEN 3: Review & Submit ─────────────────────────────────────────────────
def render_review_screen():
    # Submit button is always green on the review screen
    st.markdown(
        f"<style>button[data-testid='stBaseButton-primary'] "
        f"{{ background-color: {COLOR_ACCENT_GREEN} !important; }}</style>",
        unsafe_allow_html=True,
    )
    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("←", key="back_to_report"):
            st.session_state.screen = "reporting"
            st.rerun()
    with col_title:
        st.markdown(
            f"<p style='font-size:20px; font-weight:700; color:{COLOR_TEXT_PRIMARY}; margin:0; padding-top:4px;'>"
            f"Review Inventory</p>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<p style='color:{COLOR_TEXT_SECONDARY}; font-size:13px; margin-top:-0.4rem;'>"
        f"{st.session_state.location} · {get_today_short()}, {date.today().year}</p>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    for cat in CATEGORIES:
        st.markdown(
            f"<p style='font-size:14px; font-weight:700; color:{COLOR_TEXT_PRIMARY}; margin-bottom:0.2rem;'>"
            f"{cat['icon']} {cat['name']}</p>",
            unsafe_allow_html=True,
        )
        st.divider()
        for item in cat["items"]:
            val = st.session_state.inventory.get(item["name"], item["default"])
            is_oos = item["name"] in st.session_state.confirmed_zero
            if is_oos:
                display   = "OUT"
                val_color = "#CC6B5A"
            else:
                display   = format_value(item, val)
                val_color = COLOR_TEXT_TERTIARY if display.startswith("0") else COLOR_TEXT_PRIMARY

            lc, rc = st.columns([3, 2])
            with lc:
                st.markdown(
                    f"<p style='font-size:13px; color:{COLOR_TEXT_SECONDARY}; margin:0.1rem 0;'>{item['name']}</p>",
                    unsafe_allow_html=True,
                )
            with rc:
                st.markdown(
                    f"<p style='font-size:13px; font-weight:600; color:{val_color}; text-align:right; margin:0.1rem 0;'>"
                    f"{display}</p>",
                    unsafe_allow_html=True,
                )
        st.markdown("")

    st.markdown("")

    if st.button("Submit Inventory", key="final_submit", type="primary", use_container_width=True):
        now = datetime.now()
        submitted_at = now.strftime("%Y-%m-%d %-I:%M %p")
        st.session_state.submitted_time = now.strftime("%-I:%M %p")

        # Write to Google Sheets
        ok, err = write_to_google_sheets(
            location=st.session_state.location,
            manager_name=st.session_state.manager_name,
            now_dt=now,
            inventory=st.session_state.inventory,
            categories=CATEGORIES,
            confirmed_zero=st.session_state.confirmed_zero,
        )
        st.session_state.sheets_status = (ok, err)
        if ok:
            get_last_reported_dates.clear()  # refresh location card subtitles

        st.session_state.screen = "success"
        st.rerun()

    st.markdown("")
    center_col = st.columns([1, 2, 1])[1]
    with center_col:
        if st.button("Go Back & Edit", key="go_back_edit", use_container_width=True):
            st.session_state.screen = "reporting"
            st.rerun()


# ── SCREEN 4: Success ─────────────────────────────────────────────────────────
def render_success_screen():
    st.markdown("")
    st.markdown("")

    st.markdown(
        f"""<div style="text-align:center; padding:2rem 0 1rem;">
          <div style="display:inline-flex; align-items:center; justify-content:center;
                      background:{COLOR_BG_SUCCESS}; border-radius:50%; width:96px; height:96px;">
            <div style="display:inline-flex; align-items:center; justify-content:center;
                        background:{COLOR_ACCENT_GREEN}; border-radius:50%;
                        width:64px; height:64px; color:white; font-size:32px;">✓</div>
          </div>
          <h2 style="color:{COLOR_TEXT_PRIMARY}; font-weight:800; font-size:24px; margin:1rem 0 0.3rem;">
            Inventory Submitted!</h2>
          <p style="color:{COLOR_TEXT_SECONDARY}; font-size:14px; margin:0;">
            {st.session_state.location} · {get_today_str()}</p>
          <p style="color:{COLOR_TEXT_TERTIARY}; font-size:12px; margin:0.3rem 0 0;">
            Submitted at {st.session_state.submitted_time or "—"}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown("")

    # Google Sheets status
    if st.session_state.sheets_status is not None:
        ok, err = st.session_state.sheets_status
        if ok:
            st.markdown(
                f"<div style='text-align:center;font-size:13px;color:{COLOR_ACCENT_GREEN};'>"
                f"✓ Logged to Google Sheets</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='text-align:center;font-size:12px;color:{COLOR_TEXT_TERTIARY};'>"
                f"⚠ Sheets not updated — {err}</div>",
                unsafe_allow_html=True,
            )

    st.markdown("")

    center_col = st.columns([1, 3, 1])[1]
    with center_col:
        if st.button("Done", key="done_btn", type="primary", use_container_width=True):
            st.session_state.screen         = "location"
            st.session_state.inventory      = {}
            st.session_state.location       = None
            st.session_state.sheets_status  = None
            st.session_state.confirmed_zero = set()
            st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────
screen = st.session_state.screen
if   screen == "location":  render_location_screen()
elif screen == "reporting": render_reporting_screen()
elif screen == "review":    render_review_screen()
elif screen == "success":   render_success_screen()

# Sidebar
st.sidebar.markdown(f"**{APP_TITLE}** {APP_VERSION}")
st.sidebar.caption("Inventory reporting app.")
st.sidebar.divider()
st.sidebar.caption(f"Loaded {sum(len(c['items']) for c in CATEGORIES)} items across {len(CATEGORIES)} categories.")
