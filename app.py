import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, date
from zoneinfo import ZoneInfo
import gspread
import json

# ==============================================================================
# ##### CONFIGURATION #####
# ==============================================================================
APP_VERSION = "v1.4.13"
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
            max_inv = int(row.get("Max Inventory", 0) or 0)
        except (ValueError, TypeError):
            max_inv = 0

        if not cat_name or not item_name:
            continue

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
@st.cache_data
def get_categories():
    gc      = _get_gspread_client()
    ws      = gc.open_by_key(SPREADSHEET_ID).worksheet(ITEMS_WORKSHEET_NAME)
    records = ws.get_all_records()
    return _build_categories_from_records(records)

CATEGORIES = get_categories()

# Session state init
_SESSION_DEFAULTS = {
    "screen":         "location",
    "location":       None,
    "manager_name":   "",
    "inventory":      {},
    "confirmed_zero": set(),
    "submitted_time": None,
    "sheets_status":  None,
}
for _key, _default in _SESSION_DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default

def _inject_css():
    """Inject custom CSS — mobile-first, warm design."""
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

    /* ── Custom HTML stepper (rendered via st.markdown) ── */
    .cc-stepper {{
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 6px;
        height: 44px;
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
    }}
    .cc-value.oos {{
        font-size: 12px;
        color: #CC6B5A;
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

    # Reset form widget keys on a fresh session (prevents stale values)
    if not st.session_state.inventory:
        for ci, cat in enumerate(CATEGORIES):
            for ii, item in enumerate(cat["items"]):
                st.session_state[f"inp_{ci}_{ii}"] = (
                    float(item["default"]) if item["input"] == "slider" else int(item["default"])
                )
                if item["input"] == "slider":
                    st.session_state[f"oos_{ci}_{ii}"] = 0

    # ── Progress bar (live-updated by JS, no server round-trips) ─────────
    total_items = sum(len(cat["items"]) for cat in CATEGORIES)
    st.markdown(
        f"<div style='position: sticky; top: 0; z-index: 99; background: {COLOR_BG_PAGE}; "
        f"padding: 10px 0; margin-bottom: 1rem; margin-top: -10px;'>"
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

    # ── Form: all inputs are client-side until Submit ─────────────────────
    with st.form("inventory_form"):
        for cat_idx, cat in enumerate(CATEGORIES):
            count = len(cat["items"])
            with st.expander(f"{cat['icon']} **{cat['name']}** `{count}`", expanded=True):
                for item_idx, item in enumerate(cat["items"]):
                    name_col, inp_col = st.columns([3, 2])
                    with name_col:
                        if item["input"] == "stepper":
                            dot_html = f'<span class="cc-dot" data-item-name="{item["name"]}"></span>'
                        elif item["input"] == "slider":
                            dot_html = f'<span class="cc-dot cc-slider-dot" data-item-name="{item["name"]}"></span>'
                        else:
                            dot_html = ""
                        st.markdown(
                            f"<div style='display:flex;align-items:center;min-height:44px;gap:8px;padding:4px 0;'>"
                            f"{dot_html}"
                            f"<span style='font-size:14px;font-weight:500;color:{COLOR_TEXT_PRIMARY};"
                            f"line-height:1.2; word-break:break-word;'>"
                            f"{item['name']}</span></div>",
                            unsafe_allow_html=True,
                        )
                    with inp_col:
                        fkey = f"inp_{cat_idx}_{item_idx}"
                        if item["input"] == "stepper":
                            # Hidden data widget (read by st.form on submit)
                            # min_value=-1 allows -1 as OOS sentinel
                            st.number_input(
                                item["name"],
                                min_value=-1,
                                max_value=item["max"],
                                step=1,
                                key=fkey,
                                label_visibility="collapsed",
                            )
                            # Visible HTML stepper (JS bridges clicks → hidden input)
                            st.markdown(
                                f'<div class="cc-stepper" data-item-name="{item["name"]}">'
                                '<span class="cc-minus">&minus;</span>'
                                '<span class="cc-value">0</span>'
                                '<span class="cc-plus">+</span>'
                                '</div>',
                                unsafe_allow_html=True,
                            )
                        elif item["input"] == "slider":
                            # Hidden OOS flag (-1 = OOS, 0 = not OOS)
                            st.number_input(
                                f"{item['name']} OOS",
                                min_value=-1,
                                max_value=0,
                                step=1,
                                key=f"oos_{cat_idx}_{item_idx}",
                                label_visibility="collapsed",
                            )
                            st.slider(
                                item["name"],
                                min_value=0,
                                max_value=int(item["max"]),
                                step=1,
                                key=fkey,
                                label_visibility="collapsed",
                            )

        st.text_input("payload_data", key="inventory_payload", label_visibility="collapsed")
        
        submitted = st.form_submit_button(
            "Submit Inventory", type="primary", use_container_width=True,
        )

    # ── Handle form submission ────────────────────────────────────────────
    if submitted:
        # Parse the JSON payload from the hidden input
        try:
            payload_str = st.session_state.get("inventory_payload", "{}")
            payload = json.loads(payload_str) if payload_str else {}
        except Exception:
            payload = {}

        # Pass 1: read all form widget values → inventory dict
        for ci, cat in enumerate(CATEGORIES):
            for ii, item in enumerate(cat["items"]):
                val = payload.get(item["name"])
                if val is None:
                    # Fallback to session state defaults or slider
                    val = st.session_state.get(f"inp_{ci}_{ii}", item["default"])

                if int(float(val)) == -1:
                    # OOS dot was tapped → confirmed OOS
                    st.session_state.confirmed_zero.add(item["name"])
                    st.session_state.inventory[item["name"]] = 0
                else:
                    st.session_state.inventory[item["name"]] = val

        # Pass 2: items at zero without confirmed OOS need the dialog
        unreported = [
            item["name"]
            for cat in CATEGORIES
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
    function showCount(valSpan, n) {
        valSpan.textContent = String(n);
        valSpan.classList.remove('oos');
    }
    /* Show OOS label in stepper */
    function showOOS(valSpan) {
        valSpan.textContent = 'OOS';
        valSpan.classList.add('oos');
    }

    /* ── Bridge a stepper element to its hidden number input ── */
    function bridge(stepper) {
        if (stepper.__cc) return;
        stepper.__cc = true;

        var col = stepper.closest('[data-testid="stColumn"]');
        if (!col) return;
        var inp = col.querySelector('input[type="number"]');
        if (!inp) return;

        var valSpan = stepper.querySelector('.cc-value');
        var minus   = stepper.querySelector('.cc-minus');
        var plus    = stepper.querySelector('.cc-plus');

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

        var slider = row.querySelector('[data-testid="stSlider"] [role="slider"]');

        /* Sync initial state */
        var oosVal    = parseFloat(oosInp.value) || 0;
        var sliderVal = slider ? parseInt(slider.getAttribute('aria-valuenow')) : 0;
        dot._ccOosVal = oosVal;
        if (oosVal === -1)       { syncDot(dot, -1); }
        else if (sliderVal > 0)  { syncDot(dot, sliderVal); }

        dot.addEventListener('click', function(e) {
            e.preventDefault();
            var v = parseFloat(oosInp.value) || 0;
            if (v === -1) {
                /* un-OOS */
                dot._ccOosVal = 0;
                nativeSet(oosInp, 0);
                var sv = slider ? parseInt(slider.getAttribute('aria-valuenow')) : 0;
                syncDot(dot, sv > 0 ? sv : 0);
            } else {
                /* mark OOS */
                dot._ccOosVal = -1;
                nativeSet(oosInp, -1);
                syncDot(dot, -1);
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
    function flushAll() {
        var payload = {};
        
        D.querySelectorAll('.cc-stepper').forEach(function(s) {
            if (!s.__cc) return;
            var itemName = s.getAttribute('data-item-name');
            if (itemName) {
                payload[itemName] = s._ccVal !== undefined ? s._ccVal : 0;
            }
        });
        
        D.querySelectorAll('.cc-slider-dot').forEach(function(dot) {
            if (!dot.__ccBridged) return;
            var itemName = dot.getAttribute('data-item-name');
            if (itemName) {
                var row = dot.closest('[data-testid="stHorizontalBlock"]') || dot.parentNode.parentNode.parentNode;
                if (!row) return;
                var slider = row.querySelector('[data-testid="stSlider"] [role="slider"]');
                var sv = slider ? parseInt(slider.getAttribute('aria-valuenow')) : 0;
                payload[itemName] = (dot._ccOosVal === -1) ? -1 : (isNaN(sv) ? 0 : sv);
            }
        });

        var textInputs = Array.from(D.querySelectorAll('[data-testid="stTextInput"] input'));
        var payloadInp = textInputs.find(function(i) { 
            var aria = i.getAttribute('aria-label') || "";
            return aria.indexOf("payload_data") !== -1;
        });
        
        if (!payloadInp && textInputs.length > 0) {
            payloadInp = textInputs[textInputs.length - 1];
        }

        if (payloadInp) {
            var strPayload = JSON.stringify(payload);
            nativeSet(payloadInp, strPayload);
        }
    }

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
            /* First click — block, flush values, then re-click after delay */
            e.preventDefault();
            e.stopImmediatePropagation();
            flushAll();
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
        now = datetime.now(ZoneInfo("America/Denver"))
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
_SCREENS = {
    "location":  render_location_screen,
    "reporting": render_reporting_screen,
    "review":    render_review_screen,
    "success":   render_success_screen,
}
_SCREENS[st.session_state.screen]()

# Sidebar
st.sidebar.markdown(f"**{APP_TITLE}** {APP_VERSION}")
st.sidebar.caption("Inventory reporting app.")
st.sidebar.divider()
st.sidebar.caption(f"Loaded {sum(len(c['items']) for c in CATEGORIES)} items across {len(CATEGORIES)} categories.")
