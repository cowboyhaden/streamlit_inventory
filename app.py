import streamlit as st
from datetime import datetime, date
import gspread

# ==============================================================================
# ##### CONFIGURATION #####
# ==============================================================================
APP_VERSION = "v1.1.0"
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
        max_inv   = int(row.get("Max Inventory", 0))

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
    gc      = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    ws      = gc.open_by_key(SPREADSHEET_ID).worksheet(ITEMS_WORKSHEET_NAME)
    records = ws.get_all_records()
    return _build_categories_from_records(records)

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

    /* ── Number input (stepper replacement) ── */
    div[data-testid="stNumberInput"] {{
        margin-top: -4px !important;
    }}
    div[data-testid="stNumberInput"] input {{
        text-align: center !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        color: {COLOR_TEXT_PRIMARY} !important;
        border: 1px solid {COLOR_BORDER_SUBTLE} !important;
        border-radius: 10px !important;
        padding: 4px 8px !important;
    }}
    div[data-testid="stNumberInput"] button {{
        color: {COLOR_TEXT_PRIMARY} !important;
    }}
    div[data-testid="stNumberInput"] button:hover {{
        color: {COLOR_ACCENT_GREEN} !important;
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

    # ── Form: all inputs are client-side until Submit ─────────────────────
    with st.form("inventory_form"):
        for cat_idx, cat in enumerate(CATEGORIES):
            count = len(cat["items"])
            with st.expander(f"{cat['icon']} **{cat['name']}** `{count}`", expanded=True):
                for item_idx, item in enumerate(cat["items"]):
                    name_col, inp_col = st.columns([3, 2])
                    with name_col:
                        st.markdown(
                            f"<div style='display:flex;align-items:center;height:38px;overflow:hidden;'>"
                            f"<span style='font-size:14px;font-weight:500;color:{COLOR_TEXT_PRIMARY};"
                            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
                            f"{item['name']}</span></div>",
                            unsafe_allow_html=True,
                        )
                    with inp_col:
                        fkey = f"inp_{cat_idx}_{item_idx}"
                        if item["input"] == "stepper":
                            st.number_input(
                                item["name"],
                                min_value=0,
                                max_value=item["max"],
                                step=1,
                                key=fkey,
                                label_visibility="collapsed",
                            )
                        elif item["input"] == "slider":
                            st.slider(
                                item["name"],
                                min_value=0,
                                max_value=int(item["max"]),
                                step=1,
                                key=fkey,
                                label_visibility="collapsed",
                            )

        submitted = st.form_submit_button(
            "Submit Inventory", type="primary", use_container_width=True,
        )

    # ── Handle form submission ────────────────────────────────────────────
    if submitted:
        # Sync form widget values → inventory dict
        for ci, cat in enumerate(CATEGORIES):
            for ii, item in enumerate(cat["items"]):
                val = st.session_state[f"inp_{ci}_{ii}"]
                st.session_state.inventory[item["name"]] = val

        # Find items left at zero
        unreported = [
            item["name"]
            for cat in CATEGORIES
            for item in cat["items"]
            if item["name"] not in st.session_state.confirmed_zero
            and (float(st.session_state.inventory.get(item["name"], item["default"])) == 0
                 if item["input"] == "slider"
                 else int(st.session_state.inventory.get(item["name"], item["default"]) or 0) == 0)
        ]

        if unreported:
            _oos_confirm_dialog(unreported)
        else:
            st.session_state.screen = "review"
            st.rerun(scope="app")


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
if screen == "reporting":
    # ── Optimistic UI + dot-state observer ──────────────────────────────────
    # Runs once per full page load (outside @st.fragment); persists through
    # all fragment reruns via window.parent references.
    #
    # Key idea: when the user taps +/−/dot rapidly, the capture-phase click
    # handler updates the display INSTANTLY.  Each click still triggers a
    # Streamlit server rerun, but server responses from earlier clicks would
    # overwrite the later optimistic values — causing flicker.  To prevent
    # that, optimistic values are stored in a map keyed by item name.  The
    # MutationObserver re-applies them for 800 ms after the last tap, so
    # intermediate server reruns never flash a stale number on screen.
    # After the hold window expires the server's final value takes over.
    components.html("""
    <script>
    (function() {
        var D = window.parent.document, W = window.parent;
        var HOLD = 800;                         /* ms to hold optimistic value */
        if (!W.__ccOpt) W.__ccOpt = {};         /* { 's:ItemName': {t,c,sz,ex}, 'd:ItemName': {v,ex} } */

        /* ── Helper: resolve item name from a button ── */
        function itemName(btn, isStepper) {
            var row;
            if (isStepper) {
                var inner = btn.closest('[data-testid="stHorizontalBlock"]');
                var col   = inner && inner.closest('[data-testid="stColumn"]');
                row       = col   && col.closest('[data-testid="stHorizontalBlock"]');
            } else {
                var wrap = btn.closest('[data-testid="stButton"]');
                row      = wrap && wrap.closest('[data-testid="stHorizontalBlock"]');
            }
            if (!row) return null;
            var cols = row.querySelectorAll(':scope > div[data-testid="stColumn"]');
            return cols.length >= 2 ? cols[1].textContent.trim() : null;
        }

        /* ── MutationObserver: classify dots + re-apply optimistic values ── */
        var raf = 0;
        function refresh() {
            var now = Date.now();

            /* Classify dot buttons */
            D.querySelectorAll('button[data-testid="stBaseButton-secondary"]').forEach(function(btn) {
                var t = btn.textContent.trim();
                var w = btn.closest('[data-testid="stButton"]');
                if (!w) return;
                if (t === '\u25cb' || t === '\u25cf') {
                    var nm = itemName(btn, false);
                    var o  = nm && W.__ccOpt['d:' + nm];
                    if (o && o.ex > now) w.setAttribute('data-dot-state', o.v);
                    else w.setAttribute('data-dot-state', t === '\u25cb' ? 'empty' : 'oos');
                } else {
                    w.removeAttribute('data-dot-state');
                }
            });

            /* Re-apply optimistic stepper values */
            D.querySelectorAll('[data-testid="stExpander"] [data-testid="stHorizontalBlock"]').forEach(function(row) {
                var cols = row.querySelectorAll(':scope > div[data-testid="stColumn"]');
                if (cols.length !== 3) return;
                var inner = cols[2].querySelector('[data-testid="stHorizontalBlock"]');
                if (!inner) return;
                var nm = cols[1].textContent.trim();
                var o  = W.__ccOpt['s:' + nm];
                if (o && o.ex > now) {
                    var ic = inner.querySelectorAll(':scope > div[data-testid="stColumn"]');
                    if (ic.length === 3) {
                        var d = ic[1].querySelector('div[style*="text-align"]');
                        if (d && d.textContent.trim() !== o.t) {
                            d.textContent = o.t; d.style.color = o.c; d.style.fontSize = o.sz;
                        }
                    }
                }
            });

            /* Purge expired entries */
            for (var k in W.__ccOpt) { if (W.__ccOpt[k].ex < now) delete W.__ccOpt[k]; }
        }

        if (W.__ccDotObs) W.__ccDotObs.disconnect();
        var obs = new MutationObserver(function() {
            cancelAnimationFrame(raf); raf = requestAnimationFrame(refresh);
        });
        obs.observe(D.body, { childList: true, subtree: true });
        W.__ccDotObs = obs;
        refresh();

        /* ── Capture-phase click handler (registered once) ── */
        if (!W.__ccOptClick) {
            D.addEventListener('click', function(e) {
                var btn = e.target.closest('button[data-testid="stBaseButton-secondary"]');
                if (!btn) return;
                var text = btn.textContent.trim();
                var wrap = btn.closest('[data-testid="stButton"]');
                var ex   = Date.now() + HOLD;

                /* ── Dot toggle ── */
                if (wrap && (text === '\u25cb' || text === '\u25cf')) {
                    var ns = text === '\u25cb' ? 'oos' : 'empty';
                    wrap.setAttribute('data-dot-state', ns);
                    var nm = itemName(btn, false);
                    if (nm) W.__ccOpt['d:' + nm] = { v: ns, ex: ex };

                    /* Also flip the stepper display 0 ↔ OOS */
                    var row = wrap.closest('[data-testid="stHorizontalBlock"]');
                    if (!row) return;
                    var cs = row.querySelectorAll(':scope > div[data-testid="stColumn"]');
                    if (cs.length < 3) return;
                    var ih = cs[2].querySelector('[data-testid="stHorizontalBlock"]');
                    if (!ih) return;
                    var ic = ih.querySelectorAll(':scope > div[data-testid="stColumn"]');
                    if (ic.length !== 3) return;
                    var dd = ic[1].querySelector('div[style*="text-align"]');
                    if (!dd) return;
                    if (ns === 'oos' && dd.textContent.trim() === '0') {
                        dd.textContent = 'OOS'; dd.style.color = '#CC6B5A'; dd.style.fontSize = '12px';
                        if (nm) W.__ccOpt['s:' + nm] = { t:'OOS', c:'#CC6B5A', sz:'12px', ex: ex };
                    } else if (ns === 'empty' && dd.textContent.trim() === 'OOS') {
                        dd.textContent = '0'; dd.style.color = '#2C1810'; dd.style.fontSize = '15px';
                        if (nm) W.__ccOpt['s:' + nm] = { t:'0', c:'#2C1810', sz:'15px', ex: ex };
                    }
                    return;
                }

                /* ── Stepper +/− ── */
                if (text === '\u2212' || text === '+') {
                    var hb = btn.closest('[data-testid="stHorizontalBlock"]');
                    if (!hb) return;
                    var ic = hb.querySelectorAll(':scope > div[data-testid="stColumn"]');
                    if (ic.length !== 3) return;
                    var d = ic[1].querySelector('div[style*="text-align"]');
                    if (!d) return;
                    var nm  = itemName(btn, true);
                    var cur = d.textContent.trim();
                    var nt, nc = '#2C1810', nsz = '15px';

                    if (cur === 'OOS') {
                        if (text === '+') { nt = '1'; } else return;
                    } else {
                        var n = parseInt(cur, 10);
                        if (isNaN(n)) return;
                        nt = String(text === '+' ? n + 1 : Math.max(0, n - 1));
                    }

                    d.textContent = nt; d.style.color = nc; d.style.fontSize = nsz;
                    if (nm) W.__ccOpt['s:' + nm] = { t: nt, c: nc, sz: nsz, ex: ex };
                }
            }, true);
            W.__ccOptClick = true;
        }
    })();
    </script>
    """, height=0, scrolling=False)
    render_reporting_screen()
elif screen == "location": render_location_screen()
elif screen == "review":   render_review_screen()
elif screen == "success":  render_success_screen()

# Sidebar
st.sidebar.markdown(f"**{APP_TITLE}** {APP_VERSION}")
st.sidebar.caption("Inventory reporting app.")
st.sidebar.divider()
st.sidebar.caption(f"Loaded {sum(len(c['items']) for c in CATEGORIES)} items across {len(CATEGORIES)} categories.")
