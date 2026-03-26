import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, date
from zoneinfo import ZoneInfo
import gspread
import json
import io

# ==============================================================================
# ##### CONFIGURATION #####
# ==============================================================================
APP_VERSION = "v1.5.6"
APP_TITLE = "Cowboy Coffee"
APP_SUBTITLE = "Inventory Manager"

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
SPREADSHEET_ID       = "1int09gdLEXTXnydTLSSLmY-oNj3edG_ZKXgJC2CNZK0"
LOG_WORKSHEET_GID    = 1487457430
ITEMS_WORKSHEET_NAME = "Items"

# Mapping from location name to "Need" worksheet tab name
NEED_WORKSHEET_NAMES = {
    "Town Square":   "Town Square Need",
    "Teton Village": "Teton Village Need",
    "Big Sky":       "Big Sky Need",
}

# Category display config
CATEGORY_META = {
    "Coffee":      {"icon": "☕"},
    "Ingredients": {"icon": "🧃"},
    "Supplies":    {"icon": "📦"},
    "Merch":       {"icon": "🛍️"},
    "Clothing":    {"icon": "👕"},
}

# Grey-out rules per category group
# "zero"    → grey when need == 0
# "low_pct" → grey when need >= 80 % of category max
GREYOUT_ZERO_CATS  = {"Coffee", "Ingredients", "Supplies"}
GREYOUT_LOWPCT_CATS = {"Merch", "Clothing"}


# ==============================================================================
# ##### HELPERS #####
# ==============================================================================
def _build_categories_from_records(records: list) -> list[dict]:
    """
    Build the CATEGORIES structure from gspread row dicts.

    Input type rules (driven by the 'Unit' column):
      - "box fill scale 1 to 10"  → slider  (0–10, step 1)
      - everything else            → stepper (0–Max Inventory, step 1)
    """
    categories = {}
    for row in records:
        cat_name  = str(row.get("Category", "")).strip()
        item_name = str(row.get("Item", "")).strip()
        unit      = str(row.get("Unit", "")).strip()
        try:
            max_inv = 99  # User can enter 0-99; Max Inventory column is ignored for capping
        except (ValueError, TypeError):
            max_inv = 99
            
        try:
            w_stock = int(row.get("Warehouse Stock", 1))
        except (ValueError, TypeError):
            w_stock = 1

        try:
            show_town = int(row.get("Show TOWN", 1))
        except (ValueError, TypeError):
            show_town = 1
        try:
            show_vill = int(row.get("Show VILL", 1))
        except (ValueError, TypeError):
            show_vill = 1
        try:
            show_bs = int(row.get("Show BS", 1))
        except (ValueError, TypeError):
            show_bs = 1

        if not cat_name or not item_name:
            continue

        if cat_name not in categories:
            meta = CATEGORY_META.get(cat_name, {"icon": "📋"})
            categories[cat_name] = {"name": cat_name, "icon": meta["icon"], "items": []}

        if "scale 1 to 10" in unit.lower() or unit.lower() == "scale":
            item = {
                "name":    item_name,
                "input":   "slider",
                "unit":    "/ 10",
                "max":     10.0,
                "step":    1.0,
                "default": 0.0,
                "warehouse_stock": w_stock,
                "show_locs": {
                    "Town Square": show_town,
                    "Teton Village": show_vill,
                    "Big Sky": show_bs,
                    "BS": show_bs,
                }
            }
        else:
            item = {
                "name":    item_name,
                "input":   "stepper",
                "unit":    unit,
                "max":     max_inv,
                "default": 0,
                "warehouse_stock": w_stock,
                "show_locs": {
                    "Town Square": show_town,
                    "Teton Village": show_vill,
                    "Big Sky": show_bs,
                    "BS": show_bs,
                }
            }

        categories[cat_name]["items"].append(item)

    return list(categories.values())


def get_active_categories(all_cats: list, loc_name: str) -> list:
    """Return a copied list of categories filtered by the active location's show flag."""
    filtered = []
    for cat in all_cats:
        active = [
            i for i in cat["items"] 
            if i.get("show_locs", {}).get(loc_name, 1) == 1
        ]
        if active:
            filtered.append({
                "name": cat["name"],
                "icon": cat["icon"],
                "items": active
            })
    return filtered


@st.cache_resource
def _get_gspread_client():
    """Return a cached gspread client using the service account from secrets."""
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])


def get_greeting() -> str:
    hour = datetime.now(ZoneInfo("America/Denver")).hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    return "Good evening"


def get_today_str() -> str:
    return datetime.now(ZoneInfo("America/Denver")).strftime("%A, %B %-d, %Y")


def get_today_short() -> str:
    return datetime.now(ZoneInfo("America/Denver")).strftime("%b %-d")



def format_value(item: dict, value) -> str:
    """Format a value with its unit for review display."""
    if item["input"] == "slider":
        v = float(value) if value is not None else 0.0
        return f"{int(v)} {item['unit']}"
    else:
        v = int(value) if value is not None else 0
        return f"{v} {item['unit']}"


# ==============================================================================
# ##### UI #####
# ==============================================================================
st.set_page_config(
    page_title="Cowboy Coffee Inventory",
    page_icon="☕",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Load categories from the Items tab in Google Sheets (cached for the session)
@st.cache_data(ttl=300)
def get_categories():
    gc      = _get_gspread_client()
    ws      = gc.open_by_key(SPREADSHEET_ID).worksheet(ITEMS_WORKSHEET_NAME)
    records = ws.get_all_records()
    return _build_categories_from_records(records)

CATEGORIES = get_categories()

# Session state init
_SESSION_DEFAULTS = {
    "screen":                "location",
    "location":              None,
    "manager_name":          "",
    "inventory":             {},
    "confirmed_zero":        set(),
    "submitted_time":        None,
    "sheets_status":         None,
    "print_report_location": None,
}
for _key, _default in _SESSION_DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default

def _inject_css():
    """Inject custom CSS — mobile-first, warm design."""
    st.markdown(f"""
<style>
    /* Base layout constraints */
    .stApp {{
        background-color: {COLOR_BG_PAGE};
        max-width: 402px;
        margin: 0 auto;
    }}
    .stApp > header {{
        background-color: transparent !important;
    }}
    section[data-testid="stSidebar"] {{ display: none; }}
    header[data-testid="stHeader"]   {{ display: none !important; }}
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

    /* ── Number input: visually hidden so React can focus/blur it ── */
    div[data-testid="stNumberInput"] {{
        position: absolute !important;
        opacity: 0 !important;
        pointer-events: none !important;
        width: 1px !important;
        height: 1px !important;
        overflow: hidden !important;
        z-index: -100 !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
    }}

    /* ── Hide payload text input completely ── */
    div[data-testid="stTextInput"]:has(input[aria-label="payload_data"]) {{
        display: none !important;
    }}

    /* ── Custom Stepper (JS injects value) ── */
    .cc-stepper {{
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 12px;
        padding: 4px 0;
        min-height: 44px;
    }}
    .cc-minus, .cc-plus {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER_SUBTLE};
        color: {COLOR_TEXT_PRIMARY};
        font-size: 20px;
        font-weight: 300;
        cursor: pointer;
        touch-action: manipulation;
        -webkit-tap-highlight-color: transparent;
        user-select: none;
        -webkit-user-select: none;
        line-height: 1;
        flex-shrink: 0;
    }}
    .cc-minus:active, .cc-plus:active {{
        background: {COLOR_ACCENT_GREEN_LT};
        border-color: {COLOR_ACCENT_GREEN};
        color: {COLOR_ACCENT_GREEN};
    }}
    .cc-value {{
        font-size: 15px;
        font-weight: 600;
        color: {COLOR_TEXT_PRIMARY};
        text-align: center;
        min-width: 28px;
        width: 40px;
        background: transparent;
        border: none;
        outline: none;
        padding: 0;
        margin: 0;
        appearance: textfield;
        -moz-appearance: textfield;
    }}
    .cc-value::-webkit-inner-spin-button, 
    .cc-value::-webkit-outer-spin-button {{ 
        -webkit-appearance: none; 
        margin: 0; 
    }}
    .cc-value:focus {{
        outline: none;
        background-color: #EDE3D5;
        border-radius: 4px;
    }}
    .cc-value.oos {{
        font-size: 13px !important;
        color: #CC6B5A !important;
        font-weight: 800 !important;
    }}

    /* ── OOS dot (left of item name) ── */
    /* Default: gray outline circle. .updated = green fill. .oos = red fill */
    .cc-dot {{
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        margin-top: 7px;
        border-radius: 50%;
        background: transparent;
        border: 2px solid {COLOR_BORDER_SUBTLE};
        cursor: pointer;
        touch-action: manipulation;
        user-select: none;
        -webkit-user-select: none;
        -webkit-tap-highlight-color: transparent;
        flex-shrink: 0;
        box-sizing: border-box;
        transition: background 0.15s ease, border-color 0.15s ease;
    }}
    .cc-dot-disabled {{
        border-color: #E0E0E0 !important;
        background: #F5F5F5 !important;
        cursor: not-allowed !important;
        opacity: 0.5;
    }}
    /* Invisible ::after expands tap target to ~44×44 without affecting layout */
    .cc-dot::after {{
        content: '';
        position: absolute;
        inset: -11px;
    }}
    .cc-dot.updated {{
        background: {COLOR_ACCENT_GREEN};
        border-color: {COLOR_ACCENT_GREEN};
    }}
    .cc-dot.oos {{
        background: #CC6B5A;
        border-color: #CC6B5A;
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

    /* ── Slider OOS overlay ── */
    div[data-testid="stSlider"].cc-slider-oos {{
        opacity: 0.4 !important;
        position: relative !important;
    }}
    div[data-testid="stSlider"].cc-slider-oos::after {{
        content: 'OUT OF STOCK';
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        font-weight: 800;
        font-size: 12px;
        color: #CC6B5A;
        background: {COLOR_BG_PAGE};
        padding: 2px 6px;
        border-radius: 4px;
        pointer-events: none;
        box-shadow: 0 0 4px rgba(0,0,0,0.1);
        z-index: 10;
    }}

    #MainMenu {{ visibility: hidden; }}
    footer    {{ visibility: hidden; }}
    hr {{ border-color: {COLOR_BORDER_SUBTLE}; opacity: 0.4; }}
</style>
""", unsafe_allow_html=True)

_inject_css()


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
        gc      = _get_gspread_client()
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
        today   = datetime.now(ZoneInfo("America/Denver")).date()
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

    if confirmed_zero is None:
        confirmed_zero = set()

    try:
        gc          = _get_gspread_client()
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


# ── Print Report helpers ───────────────────────────────────────────────────────
def fetch_need_data(location: str) -> tuple[list[dict], dict[str, str]]:
    """Return (need_rows, item_to_category_map).

    need_rows: all records from the '[Location] Need' worksheet.
    item_to_cat: {item_name: category_name} from the Items tab.
    """
    tab_name = NEED_WORKSHEET_NAMES.get(location)
    if not tab_name:
        return [], {}

    gc          = _get_gspread_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    need_rows = spreadsheet.worksheet(tab_name).get_all_records()

    item_to_cat: dict[str, str] = {}
    for row in spreadsheet.worksheet(ITEMS_WORKSHEET_NAME).get_all_records():
        name = str(row.get("Item", "")).strip()
        cat  = str(row.get("Category", "")).strip()
        if name:
            item_to_cat[name] = cat

    return need_rows, item_to_cat


def generate_need_pdf(location: str, rows: list[dict], item_to_cat: dict[str, str]) -> bytes:
    """Full inventory need PDF — all rows, priority items first then greyed full list."""
    from fpdf import FPDF

    # ── Detect column names case-insensitively ──
    all_keys = list(rows[0].keys()) if rows else []

    def _find(*candidates) -> str:
        for k in all_keys:
            if k.strip().lower() in [c.lower() for c in candidates]:
                return k
        return ""

    item_col = _find("item", "name")
    need_col = _find("current need", "need")
    unit_col = _find("unit")

    COLS = [c for c in [item_col, need_col, unit_col] if c]

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    COL_W = {
        item_col: page_w * 0.60,
        need_col: page_w * 0.25,
        unit_col: page_w * 0.15,
    }
    ROW_H = 9

    date_str = datetime.now(ZoneInfo("America/Denver")).strftime("%B %-d, %Y")

    # ── Shared helpers ──
    def _page_title(subtitle: str):
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 12, "Cowboy Coffee", ln=True, align="C")
        pdf.set_font("Helvetica", "", 13)
        pdf.cell(0, 8, f"{location} - {subtitle}", ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(130, 100, 80)
        pdf.cell(0, 7, f"Generated {date_str}", ln=True, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(6)

    def _table_header():
        pdf.set_fill_color(61, 50, 41)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        for col in COLS:
            pdf.cell(COL_W.get(col, 40), ROW_H, col, border=0, fill=True, align="L")
        pdf.ln(ROW_H)
        pdf.set_text_color(44, 24, 16)

    def _cat_header(cat_name: str):
        pdf.set_fill_color(168, 139, 107)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 10, f"  {cat_name}", ln=True, fill=True, align="L")
        pdf.ln(1)

    def _footer():
        pdf.ln(4)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(160, 140, 130)
        pdf.cell(0, 6, f"Cowboy Coffee Inventory Manager {APP_VERSION}", align="C")

    if not rows or not COLS:
        _page_title("Inventory Need Report")
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(0, 10, "No items found in Need sheet.", ln=True, align="C")
        _footer()
        return bytes(pdf.output())

    # ── Group rows by category ──
    cat_order = list(CATEGORY_META.keys())
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        item_name = str(row.get(item_col, "")).strip()
        cat = item_to_cat.get(item_name, "")
        grouped.setdefault(cat or "Other", []).append(row)
    if "Other" in grouped and "Other" not in cat_order:
        cat_order.append("Other")

    # ── Pre-compute category max-need values ──
    cat_max_need: dict[str, float] = {}
    for cat_name, cat_rows in grouped.items():
        if cat_name in GREYOUT_LOWPCT_CATS and need_col:
            vals = []
            for row in cat_rows:
                try:
                    vals.append(float(row.get(need_col, 0) or 0))
                except (ValueError, TypeError):
                    pass
            cat_max_need[cat_name] = max(vals) if vals else 0.0

    def _should_grey(row: dict, cat_name: str) -> bool:
        if not need_col:
            return False
        try:
            need_val = float(row.get(need_col, 0) or 0)
        except (ValueError, TypeError):
            need_val = 0.0
        if cat_name in GREYOUT_ZERO_CATS:
            return need_val == 0
        if cat_name in GREYOUT_LOWPCT_CATS:
            max_val = cat_max_need.get(cat_name, 0.0)
            threshold = max_val * 0.80
            return need_val < threshold
        return False

    def _render_categories(row_filter=None):
        """Render all categories, optionally filtering rows with row_filter(row, cat_name) -> bool."""
        first = True
        for cat_name in cat_order:
            cat_rows = grouped.get(cat_name)
            if not cat_rows:
                continue
            display_rows = [r for r in cat_rows if row_filter is None or row_filter(r, cat_name)]
            if not display_rows:
                continue
            if not first:
                pdf.ln(4)
            first = False
            _cat_header(cat_name)
            _table_header()
            pdf.set_font("Helvetica", "", 10)
            for i, row in enumerate(display_rows):
                fill = i % 2 == 0
                pdf.set_fill_color(*(245, 240, 233) if fill else (255, 255, 255))
                pdf.set_text_color(44, 24, 16)
                for col in COLS:
                    pdf.cell(COL_W.get(col, 40), ROW_H, str(row.get(col, "")),
                             border=0, fill=True, align="L")
                pdf.ln(ROW_H)
            pdf.set_text_color(44, 24, 16)

    # ── TABLE 1: Priority items (non-greyed only) ──
    _page_title("Priority Need Report")
    _render_categories(row_filter=lambda r, c: not _should_grey(r, c))
    _footer()

    # ── TABLE 2: Full report (all items, greyed rows styled) ──
    pdf.add_page()
    _page_title("Full Inventory Need Report")

    first = True
    for cat_name in cat_order:
        cat_rows = grouped.get(cat_name)
        if not cat_rows:
            continue
        if not first:
            pdf.ln(4)
        first = False
        _cat_header(cat_name)
        _table_header()
        pdf.set_font("Helvetica", "", 10)
        for i, row in enumerate(cat_rows):
            greyed = _should_grey(row, cat_name)
            if greyed:
                pdf.set_fill_color(220, 220, 220)
                pdf.set_text_color(170, 170, 170)
            else:
                fill = i % 2 == 0
                pdf.set_fill_color(*(245, 240, 233) if fill else (255, 255, 255))
                pdf.set_text_color(44, 24, 16)
            for col in COLS:
                pdf.cell(COL_W.get(col, 40), ROW_H, str(row.get(col, "")),
                         border=0, fill=True, align="L")
            pdf.ln(ROW_H)
        pdf.set_text_color(44, 24, 16)

    _footer()

    return bytes(pdf.output())


def generate_restocking_pdf(location: str, rows: list[dict], item_to_cat: dict[str, str]) -> bytes:
    """Restocking pick list — only items where Refill? == 1, grouped by category."""
    from fpdf import FPDF

    # ── Detect columns ──
    all_keys = list(rows[0].keys()) if rows else []

    def _find(*candidates) -> str:
        for k in all_keys:
            if k.strip().lower() in [c.lower() for c in candidates]:
                return k
        return ""

    item_col   = _find("item", "name")
    need_col   = _find("current need", "need")
    unit_col   = _find("unit")
    refill_col = _find("refill?", "refill")

    # ── Filter to Refill? == 1 ──
    if refill_col:
        rows = [r for r in rows if str(r.get(refill_col, "")).strip() == "1"]

    COLS   = [c for c in [item_col, need_col, unit_col] if c]
    date_str = datetime.now(ZoneInfo("America/Denver")).strftime("%B %-d, %Y")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()

    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    COL_W  = {
        item_col: page_w * 0.60,
        need_col: page_w * 0.25,
        unit_col: page_w * 0.15,
    }
    ROW_H = 9

    # ── Header ──
    pdf.set_fill_color(61, 50, 41)
    pdf.rect(0, 0, 210, 30, style="F")
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(7)
    pdf.cell(0, 9, "Cowboy Coffee", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(200, 185, 165)
    pdf.cell(0, 6, "Restocking Pick List", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(36)
    pdf.set_text_color(44, 24, 16)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, location, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(122, 107, 94)
    pdf.cell(0, 5, f"Generated {date_str}  •  {len(rows)} item{'s' if len(rows) != 1 else ''} to restock",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(232, 223, 210)
    pdf.ln(4)
    pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.ln(5)

    if not rows:
        pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(168, 152, 136)
        pdf.cell(0, 10, "No items marked for restocking.", align="C", new_x="LMARGIN", new_y="NEXT")
    else:
        # Group by category
        cat_order = list(CATEGORY_META.keys())
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            item_name = str(row.get(item_col, "")).strip()
            cat = item_to_cat.get(item_name, "Other")
            grouped.setdefault(cat, []).append(row)
        if "Other" in grouped and "Other" not in cat_order:
            cat_order.append("Other")

        fill_toggle = False
        for cat_name in cat_order:
            cat_rows = grouped.get(cat_name)
            if not cat_rows:
                continue

            if pdf.get_y() > 250:
                pdf.add_page()

            # Category sub-header
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(168, 139, 107)
            pdf.ln(3)
            pdf.cell(0, 6, cat_name.upper(), new_x="LMARGIN", new_y="NEXT")

            # Column header
            pdf.set_fill_color(61, 50, 41)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 9)
            for col in COLS:
                pdf.cell(COL_W.get(col, 40), ROW_H, col, border=0, fill=True,
                         new_x="RIGHT", new_y="LAST")
            pdf.ln(ROW_H)
            pdf.set_text_color(44, 24, 16)
            pdf.set_font("Helvetica", "", 9)

            for row in cat_rows:
                if pdf.get_y() > 265:
                    pdf.add_page()
                bg = (245, 240, 233) if fill_toggle else (255, 255, 255)
                pdf.set_fill_color(*bg)
                for col in COLS:
                    pdf.cell(COL_W.get(col, 40), ROW_H, str(row.get(col, "")),
                             border=0, fill=True, new_x="RIGHT", new_y="LAST")
                pdf.ln(ROW_H)
                fill_toggle = not fill_toggle

    # ── Footer ──
    pdf.set_y(-16)
    pdf.set_draw_color(232, 223, 210)
    pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(168, 152, 136)
    pdf.cell(0, 5, f"Cowboy Coffee  •  {APP_VERSION}", align="C")

    return bytes(pdf.output())


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
        f'{get_today_str()}</p>'
        f'<p style="text-align:center; color:{COLOR_BORDER_SUBTLE}; font-size:11px; margin-top:0.1rem;">'
        f'{APP_VERSION}</p>',
        unsafe_allow_html=True,
    )

    # ── Generate Report button ──
    st.markdown(
        f'<div style="display:flex; align-items:center; gap:10px; margin:1.2rem 0 0.6rem;">'
        f'<div style="flex:1; height:1px; background:{COLOR_BORDER_SUBTLE};"></div>'
        f'<span style="color:{COLOR_TEXT_TERTIARY}; font-size:11px; white-space:nowrap; letter-spacing:0.05em;">TOOLS</span>'
        f'<div style="flex:1; height:1px; background:{COLOR_BORDER_SUBTLE};"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button(
        "📋  **Generate Report**\n\nView items that need to be refilled",
        key="print_report_btn",
        use_container_width=True,
    ):
        st.session_state.screen = "print_report"
        st.session_state.print_report_location = None
        st.rerun()


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
            st.rerun(scope="app")


@st.fragment
def render_reporting_screen():
    # Green submit button
    st.markdown(
        f"<style>button[data-testid='stBaseButton-primary'],"
        f"button[data-testid='stBaseButton-formSubmit'] "
        f"{{ background-color: {COLOR_ACCENT_GREEN} !important; }}</style>",
        unsafe_allow_html=True,
    )

    # Header (outside form so ← works as a normal button)
    col_back, col_title, col_date = st.columns([1, 4, 2])
    with col_back:
        if st.button("←", key="back_to_loc"):
            st.session_state.screen         = "location"
            st.session_state.inventory      = {}
            st.session_state.confirmed_zero = set()
            st.rerun(scope="app")
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

    # Ensure form widget keys exist whether it's a fresh session or returning from review
    active_categories = get_active_categories(CATEGORIES, st.session_state.location)

    for ci, cat in enumerate(active_categories):
        for ii, item in enumerate(cat["items"]):
            fkey = f"inp_{ci}_{ii}"
            ooskey = f"oos_{ci}_{ii}"
            name = item["name"]
            
            if fkey not in st.session_state:
                if name in st.session_state.confirmed_zero:
                    if item["input"] == "slider":
                        st.session_state[fkey] = 0.0
                        st.session_state[ooskey] = -1
                    else:
                        st.session_state[fkey] = -1
                else:
                    val = st.session_state.inventory.get(name, item["default"]) if st.session_state.inventory else item["default"]
                    if item["input"] == "slider":
                        st.session_state[fkey] = float(val)
                        st.session_state[ooskey] = 0
                    else:
                        st.session_state[fkey] = int(val)

    # ── Form: all inputs are client-side until Submit ─────────────────────
    with st.form("inventory_form"):
        # ── Progress bar (live-updated by JS, no server round-trips) ─────────
        total_items = sum(len(cat["items"]) for cat in active_categories)
        
        # Inject CSS to make the parent Streamlit container sticky, bypassing wrapper limits
        st.markdown(f"""
        <style>
            div[data-testid="stVerticalBlock"] > div.element-container:has(#cc-pb-container) {{
                position: -webkit-sticky;
                position: sticky;
                top: 0rem;
                z-index: 999999;
                background-color: {COLOR_BG_PAGE};
            }}
            #cc-pb-container {{
                padding: 15px 0 10px 0;
                margin-bottom: 20px;
                margin-top: -15px;
                border-bottom: 1px solid {COLOR_BORDER_SUBTLE};
            }}
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown(
            f"<div id='cc-pb-container'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>"
            f"<span style='font-size:12px;color:{COLOR_TEXT_SECONDARY};font-weight:500;'>Items reported</span>"
            f"<span id='cc-pl' style='font-size:12px;font-weight:700;color:{COLOR_TEXT_PRIMARY};'>0 / {total_items}</span>"
            f"</div>"
            f"<div style='background:{COLOR_BORDER_SUBTLE};border-radius:3px;height:6px;'>"
            f"<div id='cc-pb' style='background:{COLOR_ACCENT_GREEN};border-radius:3px;height:6px;width:0%;transition:width 0.3s ease;'></div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        for cat_idx, cat in enumerate(active_categories):
            count = len(cat["items"])
            with st.expander(f"{cat['icon']} **{cat['name']}** `{count}`", expanded=True):
                for item_idx, item in enumerate(cat["items"]):
                    name_col, inp_col = st.columns([3, 2])
                    with name_col:
                        is_disabled = (item.get("warehouse_stock", 1) == 0)
                        dim_style = "; opacity: 0.5;" if is_disabled else ""
                        strike_open = "<del>" if is_disabled else ""
                        strike_close = "</del>" if is_disabled else ""
                        
                        dot_class = "cc-dot" 
                        if item["input"] == "slider":
                            dot_class += " cc-slider-dot"
                        if is_disabled:
                            dot_class += " cc-dot-disabled"
                            
                        dot_html = f'<span class="{dot_class}" data-item-name="{item["name"]}"></span>'
                        
                        st.markdown(
                            f"<div style='display:flex;align-items:flex-start;min-height:44px;gap:8px;padding:4px 0{dim_style}'>"
                            f"{dot_html}"
                            f"<span style='font-size:14px;font-weight:500;color:{COLOR_TEXT_PRIMARY};"
                            f"line-height:1.4; word-break:break-word; margin-top:8px;'>"
                            f"{strike_open}{item['name']}{strike_close}</span></div>",
                            unsafe_allow_html=True,
                        )
                    with inp_col:
                        fkey = f"inp_{cat_idx}_{item_idx}"
                        if item["input"] == "stepper":
                            # Visible HTML stepper (JS bridges clicks → hidden input)
                            st.markdown(
                                f'<div class="cc-stepper" data-item-name="{item["name"]}" style="{"opacity:0.4; pointer-events:none;" if is_disabled else ""}">'
                                '<span class="cc-minus">&minus;</span>'
                                '<span class="cc-value">0</span>'
                                '<span class="cc-plus">+</span>'
                                '</div>',
                                unsafe_allow_html=True,
                            )
                            # Hidden data widget (read by st.form on submit)
                            # min_value=-1 allows -1 as OOS sentinel
                            st.number_input(
                                item["name"],
                                min_value=0 if is_disabled else -1,
                                max_value=0 if is_disabled else 99,
                                step=1,
                                key=fkey,
                                disabled=is_disabled,
                                label_visibility="collapsed",
                            )
                        elif item["input"] == "slider":
                            st.slider(
                                item["name"],
                                min_value=0,
                                max_value=0 if is_disabled else int(item["max"]),
                                step=1,
                                key=fkey,
                                disabled=is_disabled,
                                label_visibility="collapsed",
                            )
                            # Hidden OOS flag (-1 = OOS, 0 = not OOS)
                            st.number_input(
                                f"{item['name']} OOS",
                                min_value=0 if is_disabled else -1,
                                max_value=0,
                                step=1,
                                key=f"oos_{cat_idx}_{item_idx}",
                                disabled=is_disabled,
                                label_visibility="collapsed",
                            )

        submitted = st.form_submit_button(
            "Submit Inventory", type="primary", use_container_width=True,
        )

    # ── Handle form submission ────────────────────────────────────────────
    if submitted:
        # Pass 1: read all form widget values → inventory dict via their native Session State keys
        for ci, cat in enumerate(active_categories):
            for ii, item in enumerate(cat["items"]):
                fkey = f"inp_{ci}_{ii}"
                ooskey = f"oos_{ci}_{ii}"
                
                # Fetch the value directly from the hidden Streamlit widget that was updated via JS nativeSet
                val = st.session_state.get(fkey)
                if val is None:
                    val = item["default"]

                # OOS Evaluation depends on Stepper vs Slider logic
                if item["input"] == "slider":
                    oos_val = st.session_state.get(ooskey, 0)
                    if oos_val == -1:
                        st.session_state.confirmed_zero.add(item["name"])
                        st.session_state.inventory[item["name"]] = 0
                        continue
                    else:
                        st.session_state.confirmed_zero.discard(item["name"])
                else:
                    if int(float(val)) == -1:
                        st.session_state.confirmed_zero.add(item["name"])
                        st.session_state.inventory[item["name"]] = 0
                        continue
                    else:
                        st.session_state.confirmed_zero.discard(item["name"])

                # Normal numerical value
                st.session_state.inventory[item["name"]] = val

        # Pass 2: items at zero without confirmed OOS need the dialog
        unreported = [
            item["name"]
            for cat in active_categories
            for item in cat["items"]
            if item["name"] not in st.session_state.confirmed_zero
            and int(float(st.session_state.inventory.get(item["name"], item["default"]) or 0)) == 0
        ]

        if unreported:
            _oos_confirm_dialog(unreported)
        else:
            st.session_state.screen = "review"
            st.rerun(scope="app")

    _inject_stepper_js()


def _inject_stepper_js():
    """Bridge HTML stepper/slider clicks to hidden st.number_input values.

    The real st.number_input widgets are display:none (CSS). The user
    sees .cc-stepper HTML rendered by st.markdown. This script connects
    the two: clicking - or + on the HTML stepper updates the hidden
    input via React's native setter, so st.form reads the correct value
    on submit. Also bridges OOS dots for slider items and tracks slider
    changes for the progress bar.
    """
    components.html("""<script>
(function() {
    var D = window.parent.document, W = window.parent;

    /* Set a hidden input's value so that Streamlit's React state picks it up.
       Strategy 1: Walk React's fiber tree to find and invoke the component's
       own onChange handler directly — this updates React state synchronously.
       Strategy 2 (fallback): Native setter + _valueTracker reset + DOM events. */
    function nativeSet(inp, val) {
        var valStr = String(val);

        inp.focus();
        
        /* Set the actual DOM value first */
        var setter = Object.getOwnPropertyDescriptor(
            W.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(inp, valStr);

        /* Trigger React onChange via native events fallback */
        var tracker = inp._valueTracker;
        if (tracker) {
            tracker.setValue("");
        }
        
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        inp.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Enter', code: 'Enter' }));
        inp.dispatchEvent(new KeyboardEvent('keyup',  { bubbles: true, cancelable: true, key: 'Enter', code: 'Enter' }));
        
        inp.blur();
    }

    /* Sync the dot circle color: gray=unreported, green=updated, red=OOS */
    function syncDot(dot, val) {
        if (val === -1) {
            dot.classList.remove('updated');
            dot.classList.add('oos');
        } else if (val > 0) {
            dot.classList.remove('oos');
            dot.classList.add('updated');
        } else {
            dot.classList.remove('oos');
            dot.classList.remove('updated');
        }
    }

    /* Recount all items by row and update the progress bar.
       Uses requestAnimationFrame to batch DOM writes and avoid
       triggering the MutationObserver in an infinite loop. */
    var _progQueued = false;
    function updateProgress() {
        if (_progQueued) return;
        _progQueued = true;
        W.requestAnimationFrame(function() {
            _progQueued = false;
            var rows = D.querySelectorAll('[data-testid="stHorizontalBlock"]');
            var total = 0, reported = 0;
            rows.forEach(function(row) {
                var stepper = row.querySelector('.cc-stepper');
                var slider  = row.querySelector('[data-testid="stSlider"] [role="slider"]');
                if (stepper) {
                    total++;
                    var inp = row.querySelector('input[type="number"]');
                    if (inp) {
                        var v = parseInt(inp.value);
                        if (!isNaN(v) && v !== 0) reported++;
                    }
                } else if (slider) {
                    total++;
                    var sv = parseInt(slider.getAttribute('aria-valuenow'));
                    /* Check the hidden OOS flag input */
                    var oosInp = row.querySelector('input[type="number"]');
                    var oosVal = oosInp ? parseInt(oosInp.value) : 0;
                    if ((!isNaN(sv) && sv > 0) || oosVal === -1) reported++;
                }
            });
            var pb = D.getElementById('cc-pb');
            var pl = D.getElementById('cc-pl');
            if (pb && pl && total > 0) {
                pb.style.width = Math.round(reported / total * 100) + '%';
                pl.textContent = reported + ' / ' + total;
            }
        });
    }

    /* Show normal count in stepper */
    function showCount(el, n) {
        if (el.tagName === 'INPUT') { el.value = String(n); }
        else { el.textContent = String(n); }
        el.classList.remove('oos');
    }
    /* Show OOS label in stepper */
    function showOOS(el) {
        if (el.tagName === 'INPUT') { el.value = 'OOS'; }
        else { el.textContent = 'OOS'; }
        el.classList.add('oos');
    }

    /* ── Bridge a stepper element to its hidden number input ── */
    function bridge(stepper) {
        if (stepper.__cc) return;
        stepper.__cc = true;

        var col = stepper.closest('[data-testid="stColumn"]');
        if (!col) return;
        var inp = col.querySelector('input[type="number"]');
        if (!inp) return;

        /* Dynamically replace the <span class="cc-value"> with a real <input> */
        var origSpan = stepper.querySelector('.cc-value');
        var valInput = D.createElement('input');
        valInput.type = 'tel';
        valInput.className = origSpan.className;
        valInput.value = origSpan.textContent || '0';
        valInput.setAttribute('inputmode', 'numeric');
        valInput.setAttribute('pattern', '[0-9]*');
        origSpan.parentNode.replaceChild(valInput, origSpan);
        var valSpan = valInput;  /* Use valSpan name for consistency */

        var minus = stepper.querySelector('.cc-minus');
        var plus  = stepper.querySelector('.cc-plus');

        var row = col.closest('[data-testid="stHorizontalBlock"]');
        var dot = row ? row.querySelector('.cc-dot') : null;

        var init = Math.round(parseFloat(inp.value) || 0);
        stepper._ccVal = init;
        if (init === -1) { showOOS(valSpan); }
        else             { showCount(valSpan, init); }
        if (dot) syncDot(dot, init);

        if (dot) {
            dot.addEventListener('click', function(e) {
                e.preventDefault();
                var v = parseFloat(inp.value) || 0;
                if (v === -1) {
                    stepper._ccVal = 0;
                    nativeSet(inp, 0);
                    syncDot(dot, 0);
                    showCount(valSpan, 0);
                } else {
                    stepper._ccVal = -1;
                    nativeSet(inp, -1);
                    syncDot(dot, -1);
                    showOOS(valSpan);
                }
                updateProgress();
            });
        }

        /* ── Manual keypad typing support ── */
        var finalizeInput = function() {
            if (valSpan.value.toUpperCase() === 'OOS') return;
            var raw = valSpan.value.replace(/[^0-9]/g, '');
            var v = parseInt(raw, 10);
            if (isNaN(v)) v = 0;
            if (v > 99) v = 99;
            stepper._ccVal = v;
            nativeSet(inp, v);
            showCount(valSpan, v);
            if (dot) syncDot(dot, v);
            updateProgress();
        };

        valSpan.addEventListener('focus', function() {
            /* Select all text on focus so the user can immediately type over it */
            setTimeout(function() { valSpan.select(); }, 0);
        });

        valSpan.addEventListener('blur', finalizeInput);

        valSpan.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                valSpan.blur();
            }
        });

        minus.addEventListener('click', function(e) {
            e.preventDefault();
            var v = parseFloat(inp.value) || 0;
            if (v <= 0) return;
            var nv = v - 1;
            stepper._ccVal = Math.round(nv);
            nativeSet(inp, nv);
            showCount(valSpan, Math.round(nv));
            if (dot) syncDot(dot, Math.round(nv));
            updateProgress();
        });

        plus.addEventListener('click', function(e) {
            e.preventDefault();
            var v  = parseFloat(inp.value) || 0;
            var mx = parseFloat(inp.max);
            var nv;
            if (v === -1) { nv = 1; }
            else { nv = isNaN(mx) ? v + 1 : Math.min(mx, v + 1); }
            stepper._ccVal = Math.round(nv);
            nativeSet(inp, nv);
            showCount(valSpan, Math.round(nv));
            if (dot) syncDot(dot, Math.round(nv));
            updateProgress();
        });
    }

    /* ── Bridge a slider-dot to its hidden OOS number input ── */
    function bridgeSliderDot(dot) {
        if (dot.__ccBridged) return;
        dot.__ccBridged = true;

        var row = dot.closest('[data-testid="stHorizontalBlock"]');
        if (!row) return;

        var oosInp = row.querySelector('input[type="number"]');
        if (!oosInp) return;

        var sliderContainer = row.querySelector('[data-testid="stSlider"]');
        var slider = sliderContainer ? sliderContainer.querySelector('[role="slider"]') : null;

        /* Sync initial state */
        var oosVal    = parseFloat(oosInp.value) || 0;
        var sliderVal = slider ? parseInt(slider.getAttribute('aria-valuenow')) : 0;
        dot._ccOosVal = oosVal;
        if (oosVal === -1)       { 
            syncDot(dot, -1); 
            if (sliderContainer) sliderContainer.classList.add('cc-slider-oos');
        }
        else if (sliderVal > 0)  { 
            syncDot(dot, sliderVal); 
        }

        dot.addEventListener('click', function(e) {
            e.preventDefault();
            var v = parseFloat(oosInp.value) || 0;
            if (v === -1) {
                /* un-OOS */
                dot._ccOosVal = 0;
                nativeSet(oosInp, 0);
                var sv = slider ? parseInt(slider.getAttribute('aria-valuenow')) : 0;
                syncDot(dot, sv > 0 ? sv : 0);
                if (sliderContainer) sliderContainer.classList.remove('cc-slider-oos');
            } else {
                /* mark OOS */
                dot._ccOosVal = -1;
                nativeSet(oosInp, -1);
                syncDot(dot, -1);
                if (sliderContainer) sliderContainer.classList.add('cc-slider-oos');
            }
            updateProgress();
        });

        /* Watch slider value changes to auto-clear OOS and update dot */
        if (slider) {
            var sliderObs = new MutationObserver(function() {
                var sv = parseInt(slider.getAttribute('aria-valuenow'));
                if (!isNaN(sv) && sv > 0 && parseFloat(oosInp.value) === -1) {
                    /* Slider moved above 0 → clear OOS */
                    dot._ccOosVal = 0;
                    nativeSet(oosInp, 0);
                    if (sliderContainer) sliderContainer.classList.remove('cc-slider-oos');
                }
                syncDot(dot, parseFloat(oosInp.value) === -1 ? -1 : (sv > 0 ? sv : 0));
                updateProgress();
            });
            sliderObs.observe(slider, {attributes: true, attributeFilter: ['aria-valuenow']});
        }
    }

    function bridgeAll() {
        D.querySelectorAll('.cc-stepper').forEach(bridge);
        D.querySelectorAll('.cc-slider-dot').forEach(bridgeSliderDot);
    }

    /* Flush all tracked JS values into the single hidden JSON payload input. */
    // flushAll removed in favor of 100% Native Streamlit session state tracking

    /* Intercept the submit button click: block it, flush all values into
       the hidden inputs, then re-click after a short delay so React has
       time to process the state updates before the form actually submits. */
    function interceptSubmit() {
        var btns = Array.from(D.querySelectorAll('button'));
        var btn = btns.find(function(b) {
            return b.textContent && b.textContent.indexOf("Submit Inventory") !== -1;
        });

        if (!btn || btn._ccIntercepted) return;
        btn._ccIntercepted = true;
        btn.addEventListener('click', function(e) {
            if (btn._ccFlushed) {
                /* Second click (re-triggered) — let Streamlit handle it */
                btn._ccFlushed = false;
                return;
            }
            /* First click — block, then re-click after delay */
            e.preventDefault();
            e.stopImmediatePropagation();
            btn._ccFlushed = true;
            setTimeout(function() { btn.click(); }, 500);
        }, true); /* capture phase — fires before Streamlit's handler */
    }

    function setup() {
        bridgeAll();
        interceptSubmit();
        updateProgress();
    }

    setup(); setTimeout(setup, 250); setTimeout(setup, 700);

    /* Observer bridges new elements AND re-attaches submit interceptor.
       updateProgress is safe here because it uses requestAnimationFrame. */
    if (W.__ccN) W.__ccN.disconnect();
    W.__ccN = new MutationObserver(function() {
        bridgeAll();
        interceptSubmit();
        updateProgress();
    });
    W.__ccN.observe(D.body, {childList: true, subtree: true});
})();
</script>""", height=0, scrolling=False)


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
        f"{st.session_state.location} · {get_today_short()}, {datetime.now(ZoneInfo('America/Denver')).year}</p>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    active_categories = get_active_categories(CATEGORIES, st.session_state.location)
    for cat in active_categories:
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
        now = datetime.now(ZoneInfo("America/Denver"))
        st.session_state.submitted_time = now.strftime("%-I:%M %p")

        # Write to Google Sheets
        ok, err = write_to_google_sheets(
            location=st.session_state.location,
            manager_name=st.session_state.manager_name,
            now_dt=now,
            inventory=st.session_state.inventory,
            categories=active_categories,
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


# ── SCREEN: Print Report ──────────────────────────────────────────────────────
def render_print_report_screen():
    # Header
    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("←", key="print_back"):
            st.session_state.screen = "location"
            st.session_state.print_report_location = None
            st.rerun()
    with col_title:
        st.markdown(
            f"<p style='font-size:20px; font-weight:700; color:{COLOR_TEXT_PRIMARY}; margin:0; padding-top:4px;'>"
            "Print Report</p>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:{COLOR_TEXT_SECONDARY}; font-size:14px;'>Select a location to generate the Inventory Need PDF.</p>",
        unsafe_allow_html=True,
    )

    selected_loc = st.session_state.get("print_report_location")

    if not selected_loc:
        for loc in LOCATIONS:
            if loc["name"] not in NEED_WORKSHEET_NAMES:
                continue
            if st.button(
                f"{loc['icon']}  **{loc['name']}**",
                key=f"print_loc_{loc['name']}",
                use_container_width=True,
            ):
                st.session_state.print_report_location = loc["name"]
                st.rerun()
    else:
        st.markdown(
            f"<p style='font-size:15px; font-weight:600; color:{COLOR_TEXT_PRIMARY};'>" 
            f"{selected_loc}</p>",
            unsafe_allow_html=True,
        )

        # Generate both PDFs once per location — cache in session_state.
        cache_key = f"_pdf_cache_{selected_loc}"
        if cache_key not in st.session_state:
            # Step 1: fetch sheet data
            rows, item_to_cat = None, None
            with st.spinner("Fetching need data from Google Sheets…"):
                try:
                    rows, item_to_cat = fetch_need_data(selected_loc)
                except Exception as exc:
                    st.error(f"Could not load '{selected_loc} Need' sheet: {exc}")

            # Step 2: generate PDFs (separate so sheet errors and PDF errors are distinct)
            if rows is not None:
                with st.spinner("Generating reports…"):
                    try:
                        restock_bytes = generate_restocking_pdf(selected_loc, rows, item_to_cat)
                        full_bytes    = generate_need_pdf(selected_loc, rows, item_to_cat)
                        slug          = selected_loc.lower().replace(" ", "_")
                        st.session_state[cache_key] = {
                            "restock_bytes": restock_bytes,
                            "restock_file":  f"{slug}_restocking_report.pdf",
                            "full_bytes":    full_bytes,
                            "full_file":     f"{slug}_full_report.pdf",
                            "num_rows":      len(rows),
                        }
                    except ModuleNotFoundError as exc:
                        st.error(
                            f"PDF library not installed: **{exc}**\n\n"
                            "Make sure `fpdf2` is in your `requirements.txt` and redeploy the app."
                        )
                    except Exception as exc:
                        st.error(f"Could not generate PDF: {exc}")

        cached = st.session_state.get(cache_key)
        if cached:
            st.markdown(
                f"<p style='font-size:12px; color:{COLOR_TEXT_TERTIARY}; margin:0 0 0.8rem;'>"
                f"{cached['num_rows']} items loaded from Google Sheets.</p>",
                unsafe_allow_html=True,
            )

            # Restocking Report (Refill? == 1 only)
            st.markdown(
                f"<p style='font-size:13px; font-weight:700; color:{COLOR_TEXT_PRIMARY}; margin:0.2rem 0 0.1rem;'>"
                f"Restocking Report</p>"
                f"<p style='font-size:12px; color:{COLOR_TEXT_SECONDARY}; margin:0 0 0.4rem;'>"
                f"Items flagged for refill only</p>",
                unsafe_allow_html=True,
            )
            st.download_button(
                label="⬇️  Download Restocking Report",
                data=cached["restock_bytes"],
                file_name=cached["restock_file"],
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key="dl_restock",
            )

            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

            # Full Report (all items)
            st.markdown(
                f"<p style='font-size:13px; font-weight:700; color:{COLOR_TEXT_PRIMARY}; margin:0.2rem 0 0.1rem;'>"
                f"Full Report</p>"
                f"<p style='font-size:12px; color:{COLOR_TEXT_SECONDARY}; margin:0 0 0.4rem;'>"
                f"Complete inventory need report for all items</p>",
                unsafe_allow_html=True,
            )
            st.download_button(
                label="⬇️  Download Full Report",
                data=cached["full_bytes"],
                file_name=cached["full_file"],
                mime="application/pdf",
                use_container_width=True,
                key="dl_full",
            )

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        if st.button("← Change Location", key="print_change_loc"):
            st.session_state.print_report_location = None
            st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────
_SCREENS = {
    "location":     render_location_screen,
    "reporting":    render_reporting_screen,
    "review":       render_review_screen,
    "success":      render_success_screen,
    "print_report": render_print_report_screen,
}
_SCREENS[st.session_state.screen]()

# Sidebar
st.sidebar.markdown(f"**{APP_TITLE}** {APP_VERSION}")
st.sidebar.caption("Inventory reporting app.")
st.sidebar.divider()
st.sidebar.caption(f"Loaded {sum(len(c['items']) for c in CATEGORIES)} items across {len(CATEGORIES)} categories.")
