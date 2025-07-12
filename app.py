"""
Dash app for Value and Quality Everything
- 3x3 colored scatter plot (Plotly)
- Submission form (value, quality, type, category, name, location, user_id)
- SQLite database (SQLAlchemy)
- Google login (OAuth 2.0)
"""

import os
import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base
from flask import session, redirect as flask_redirect, url_for, session as flask_session
from flask_dance.contrib.google import make_google_blueprint, google
from dotenv import load_dotenv
from dash import dash_table  # Updated import for dash_table
from datetime import datetime
from dash.dependencies import ALL

print(f"[ABSDEBUG] Loading app.py from {__file__}", flush=True)

# Load environment variables from .env
load_dotenv()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")

# --- Database setup (SQLite, persistent for Render) ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./submissions.db")
if DATABASE_URL.startswith("sqlite"):
    engine = sa.create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        # Use default isolation_level (None) for transactional mode
    )
    print("[DB] SQLite engine created with timeout=30, check_same_thread=False, default isolation_level (transactional)", flush=True)
else:
    engine = sa.create_engine(
        DATABASE_URL,
        isolation_level=None  # Use default for non-SQLite
    )
    print(f"[DB] Engine created for {DATABASE_URL}", flush=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Submission(Base):
    __tablename__ = "submissions"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    value = sa.Column(sa.Float, nullable=False)
    quality = sa.Column(sa.Float, nullable=False)
    type = sa.Column(sa.String, nullable=False)
    category = sa.Column(sa.String, nullable=False)
    name = sa.Column(sa.String(100), nullable=False)
    location = sa.Column(sa.String, nullable=False)
    user_id = sa.Column(sa.String, nullable=True)  # Changed from Integer to String for email
    date_submitted = sa.Column(sa.DateTime, nullable=True, default=datetime.utcnow)

class SubmissionUpvote(Base):
    __tablename__ = "submission_upvotes"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    submission_id = sa.Column(sa.Integer, sa.ForeignKey("submissions.id"), nullable=False)
    category = sa.Column(sa.String, nullable=False)  # Store category for reference
    type = sa.Column(sa.String, nullable=False)      # Store type for reference
    voter_id = sa.Column(sa.String, nullable=False)  # user name or email
    timestamp = sa.Column(sa.DateTime, default=datetime.utcnow)
    __table_args__ = (sa.UniqueConstraint('submission_id', 'voter_id', name='_submission_voter_uc'),)

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[WARNING] Could not create tables: {e}")

# --- SQLite performance optimizations (PRAGMA) ---
try:
    with engine.connect() as conn:
        conn.execute(sa.text("PRAGMA journal_mode=WAL;"))
        conn.execute(sa.text("PRAGMA synchronous=NORMAL;"))
except Exception as e:
    print(f"[WARNING] Could not set PRAGMA options: {e}")

# --- Add indexes for upvote performance ---
try:
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_upvotes_submission_id ON submission_upvotes (submission_id);"))
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_upvotes_voter_id ON submission_upvotes (voter_id);"))
except Exception as e:
    print(f"[WARNING] Could not create indexes: {e}")

# --- Helper: get all submissions ---
def get_submissions():
    with SessionLocal() as db:
        return db.query(Submission).all()

# --- Helper: get submissions for a user ---
def get_user_submissions(user_name, user_email=None):
    # Return submissions where user_id matches name or email (case-insensitive)
    if not user_name and not user_email:
        return []
    with SessionLocal() as db:
        filters = []
        if user_name:
            filters.append(sa.func.lower(Submission.user_id) == user_name.strip().lower())
        if user_email:
            filters.append(sa.func.lower(Submission.user_id) == user_email.strip().lower())
        return db.query(Submission).filter(sa.or_(*filters)).all()

def get_current_user_email():
    user = get_current_user()
    if user:
        return user.get("email")
    return None

# --- Helper: add a submission ---
def add_submission(data):
    user_id = get_current_user_id()
    data["user_id"] = user_id
    data["date_submitted"] = datetime.utcnow()
    with SessionLocal() as db:
        sub = Submission(**data)
        db.add(sub)
        db.commit()
        # Automatically upvote own submission (commented out)
        # db.add(SubmissionUpvote(submission_id=sub.id, voter_id=user_id, category=data["category"], type=data["type"]))
        # db.commit()
    # Refresh upvote cache after adding a new submission
    load_upvote_cache()

# --- Helper: delete all submissions ---
def delete_all_submissions():
    with SessionLocal() as db:
        db.query(Submission).delete()
        db.commit()

# delete_all_submissions()  # Clear all submissions on app start (uncomment to use)

# --- Helper: delete a submission by id and user_id ---
def delete_submission_real(sub_id, user_id, user_email=None):
    import sys
    import traceback
    import os
    print(f"[DEBUG] delete_submission_real PID: {os.getpid()}", flush=True)
    admin_env = os.getenv("ADMIN_EMAIL", "admin@example.com").strip().lower()
    norm_user_id = (user_id or "").strip().lower()
    norm_user_email = (user_email or "").strip().lower()
    print(f"[DEBUG] admin_env={admin_env}, norm_user_id={norm_user_id}, norm_user_email={norm_user_email}", flush=True)
    try:
        print(f"[DEBUG] About to create SessionLocal() for sub_id={sub_id}", flush=True)
        db = SessionLocal()
        print(f"[DEBUG] Created SessionLocal() for sub_id={sub_id}", flush=True)
        with db:
            print(f"[DEBUG] Opened DB session in delete_submission_real for sub_id={sub_id}", flush=True)
            if norm_user_id == admin_env or norm_user_email == admin_env:
                print(f"[DEBUG] ADMIN DELETE PATH for sub_id={sub_id}", flush=True)
                match_count = db.query(Submission).filter(Submission.id == sub_id).count()
                print(f"[DEBUG] ADMIN: submissions matching sub_id={sub_id}: {match_count}", flush=True)
                upvotes_deleted = db.query(SubmissionUpvote).filter(SubmissionUpvote.submission_id == sub_id).delete(synchronize_session=False)
                subs_deleted = db.query(Submission).filter(Submission.id == sub_id).delete(synchronize_session=False)
                db.commit()
                print(f"[DEBUG] ADMIN DELETE: upvotes_deleted={upvotes_deleted}, subs_deleted={subs_deleted}", flush=True)
                print(f"[DEBUG] ADMIN DELETE: committed for sub_id={sub_id}", flush=True)
            else:
                sub = db.query(Submission).filter(
                    Submission.id == sub_id,
                    sa.or_(sa.func.lower(Submission.user_id) == norm_user_id, sa.func.lower(Submission.user_id) == norm_user_email)
                ).first()
                if sub:
                    print(f"[DEBUG] USER DELETE PATH for sub_id={sub_id}", flush=True)
                    upvotes_deleted = db.query(SubmissionUpvote).filter(SubmissionUpvote.submission_id == sub_id).delete(synchronize_session=False)
                    db.delete(sub)
                    db.commit()
                    print(f"[DEBUG] USER DELETE: upvotes_deleted={upvotes_deleted}, sub_id={sub_id}", flush=True)
                    print(f"[DEBUG] USER DELETE: committed for sub_id={sub_id}", flush=True)
        print(f"[DEBUG] delete_submission_real exit for sub_id={sub_id}", flush=True)
    except Exception as e:
        print(f"[ERROR] Exception in delete_submission_real for sub_id={sub_id}: {e}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()

# --- Helper: average duplicate submissions ---
def get_averaged_subs(subs):
    from collections import defaultdict
    grouped = defaultdict(list)
    for s in subs:
        key = (s.name, s.category, s.type, s.location)
        grouped[key].append(s)
    avg_subs = []
    for key, group in grouped.items():
        avg_value = sum(s.value for s in group) / len(group)
        avg_quality = sum(s.quality for s in group) / len(group)
        s0 = group[0]
        avg_subs.append(type('AvgSub', (), {
            'name': s0.name, 'category': s0.category, 'type': s0.type, 'location': s0.location,
            'value': avg_value, 'quality': avg_quality
        }))
    return avg_subs

# --- Always render the user-table DataTable, even if empty ---
def get_user_table(user_id=None, show_mine=True, filter_category="All", user_email=None):
    if show_mine and user_id:
        subs = get_user_submissions(user_id, user_email)
    else:
        subs = get_submissions()
    if filter_category and filter_category != "All":
        subs = [s for s in subs if s.category == filter_category]
    
    from datetime import datetime
    def format_date(date_val):
        if not date_val:
            return "-"
        if isinstance(date_val, str):
            try:
                # Try parsing as ISO or YYYY-MM-DD
                return datetime.fromisoformat(date_val).strftime("%Y-%m-%d")
            except Exception:
                return date_val[:10]  # fallback: just take first 10 chars
        return date_val.strftime("%Y-%m-%d")
    data = [
        {"id": s.id,
         "value": s.value,
         "quality": s.quality,
         "type": s.type,
         "category": s.category,
         "name": s.name,
         "location": s.location,
         "user_id": s.user_id if s.user_id else "?",  # Show full user_id
         "date_submitted": format_date(getattr(s, "date_submitted", None)),
         "remove": "Delete"}
        for s in subs
    ]
    columns = [
        {"name": "ID", "id": "id"},
        {"name": "Value", "id": "value"},
        {"name": "Quality", "id": "quality"},
        {"name": "Type", "id": "type"},
        {"name": "Category", "id": "category"},
        {"name": "Name", "id": "name"},
        {"name": "Location", "id": "location"},
        {"name": "User", "id": "user_id"},
        {"name": "Date", "id": "date_submitted"},
        {"name": "Remove", "id": "remove"},
    ]
    return dash_table.DataTable(
        data=data,
        columns=columns,
        style_table={"width": "100%", "overflowX": "auto", "background": "#fff"},
        style_cell={"textAlign": "left", "padding": "8px", "minWidth": 80, "maxWidth": 300, "whiteSpace": "normal"},
        style_header={"fontWeight": "bold", "background": "#f8f9fa"},
        row_deletable=False,
        id="user-table",
        style_as_list_view=True,
        page_size=20,
        editable=False,
        cell_selectable=True,
        style_data_conditional=[
            {"if": {"column_id": "remove"}, "textAlign": "center", "color": "#fff", "backgroundColor": prussian_blue, "cursor": "pointer", "fontWeight": "bold"},
        ],
    )

# --- Google OAuth setup ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

google_bp = make_google_blueprint(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    scope=[
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid"
    ],
    redirect_url="/",
)

# Register blueprint with Flask server
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "VQ Everything"
app.server.register_blueprint(google_bp, url_prefix="/login")

# Set Flask secret key for session management and OAuth
app.server.secret_key = os.getenv("FLASK_SECRET_KEY")

# Helper to get current user info
from flask import session as flask_session

@app.server.before_request
def clear_user_info_on_new_login():
    from flask import session as flask_session
    if "google_oauth_token" in flask_session and "user_info" in flask_session:
        flask_session.pop("user_info", None)


def get_current_user():
    try:
        from flask import session as flask_session
        user_info = flask_session.get("user_info")
        if user_info:
            print("[UserCache] Returning cached Google user info from session.")
            return user_info
        if "google_oauth_token" not in flask_session:
            return None
        print("[UserCache] Fetching Google user info from API...")
        resp = google.get("/oauth2/v2/userinfo")
        if resp.ok:
            user_info = resp.json()
            flask_session["user_info"] = user_info
            print("[UserCache] Google user info cached in session.")
            return user_info
    except Exception:
        return None
    return None

def get_current_user_id():
    user = get_current_user()
    if user:
        # Use Google name instead of email for privacy
        return user.get("name")
    return None

def get_user_initials(name):
    if not name:
        return "?"
    parts = name.strip().split()
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()

prussian_blue = "#003153"

region_colors = [
    ["#63be7b", "#aeddbc", "#fbdfe2"],
    ["#9ed6ae", "#fbe2e4", "#f9a9ab"],
    ["#ffffff", "#facbce", "#f8696b"],
]

def get_initial_figure():
    subs = get_submissions()
    fig = go.Figure()
    # Draw grid regions (flip axes: Value on x, Quality on y)
    for i in range(3):
        for j in range(3):
            fig.add_shape(type="rect",
                x0=i*100/3, x1=(i+1)*100/3,
                y0=j*100/3, y1=(j+1)*100/3,
                fillcolor=region_colors[j][i],
                opacity=0.3,
                line={"width": 1, "color": "#222"},
                layer="below"
            )
    # Draw bold grid lines (vertical for Value, horizontal for Quality)
    for k in range(1, 3):
        fig.add_shape(type="line", x0=k*100/3, x1=k*100/3, y0=0, y1=100, line={"color": "#222", "width": 2})
        fig.add_shape(type="line", y0=k*100/3, y1=k*100/3, x0=0, x1=100, line={"color": "#222", "width": 2})
    # Add points (flip axes)
    if subs:
        fig.add_trace(go.Scatter(
            x=[s.value for s in subs],
            y=[s.quality for s in subs],
            text=[f"{s.name}<br>{s.category}<br>Value: {s.value:.0f}<br>Quality: {s.quality:.0f}" for s in subs],
            hoverinfo="text",
            mode="markers",
            marker={"size": 14, "color": prussian_blue, "line": {"width": 2, "color": "#fff"}},
        ))
    # Remove axis numbers and titles, use only subtitles as annotations (use paper coordinates for robust placement)
    fig.update_layout(
        autosize=False,
        width=500, height=500,
        margin={"l": 110, "r": 20, "t": 90, "b": 40},
        xaxis={
            "range": [0, 100],
            "title": None,
            "showgrid": False,
            "zeroline": False,
            "scaleanchor": "y",
            "scaleratio": 1,
            "showticklabels": False,
        },
        yaxis={
            "range": [100, 0],
            "title": None,
            "showgrid": False,
            "zeroline": False,
            "scaleanchor": "x",
            "scaleratio": 1,
            "showticklabels": False,
        },
        plot_bgcolor="#fff",
        paper_bgcolor="#fff",
        annotations=[
            # Value (x) subtitles at the top (use yref='paper')
            dict(x=1/6, y=1.08, text="Cheap", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            dict(x=0.5, y=1.08, text="Mod Value", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            dict(x=5/6, y=1.08, text="Expensive", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            # Quality (y) subtitles at the left, vertical (use xref='paper')
            dict(x=-0.13, y=1/6, text="High Q", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
            dict(x=-0.13, y=0.5, text="Mod Q", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
            dict(x=-0.13, y=5/6, text="Low Q", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
        ]
    )
    return fig

# --- User login/logout UI ---
def get_login_section():
    user = get_current_user()
    if user:
        return html.Div([
            html.Span(f"Logged in as {user.get('name', user.get('email', 'User'))}", style={"marginRight": 15, "fontWeight": 500, "color": prussian_blue}),
            html.A("Log out", href="/logout", style={"marginRight": 10, "color": "#fff", "background": "#6c757d", "padding": "6px 12px", "borderRadius": "4px", "textDecoration": "none", "fontWeight": 500}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": 20})
    else:
        return html.Div([
            html.A("Log in with Google", href="/login/google", style={"background": prussian_blue, "color": "#fff", "padding": "6px 12px", "borderRadius": "4px", "textDecoration": "none", "fontWeight": 500}),
        ], style={"marginBottom": 20})

app.layout = dbc.Container([
    dcc.Location(id="url", refresh=True),
    dcc.Store(id="login-state"),
    dcc.Store(id="show-mine-toggle", data=False),  # Default to False (All Submissions)
    dcc.Store(id="selected-restaurant"),  # Store for clicked restaurant info
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(id="profile-title")),
            dbc.ModalBody(id="profile-body"),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-profile-modal", className="ms-auto", n_clicks=0)
            ),
        ],
        id="profile-modal",
        is_open=False,
        size="lg",
        centered=True,
    ),
    html.H1("VQ Everything", style={"color": prussian_blue, "fontWeight": 700, "marginTop": 30}),
    html.Div(id="login-section"),
    dbc.Row([
        dbc.Col([
            # Toggle for show only my items / show all
            html.Div([
                dbc.Label("Show:", style={"marginRight": 10, "fontWeight": 500, "color": prussian_blue}),
                dbc.RadioItems(
                    id="show-mine-radio",
                    options=[
                        {"label": "All Submissions", "value": False},
                        {"label": "My Submissions", "value": True},
                    ],
                    value=False,  # Default to All Submissions
                    inline=True,
                    style={"marginBottom": 10}
                ),
            ], style={"marginBottom": 10, "display": "flex", "alignItems": "center"}),
            # Category filter above the chart
            html.Div([
                dbc.Label("Filter by Category:", style={"marginRight": 10, "fontWeight": 500, "color": prussian_blue}),
                dcc.Dropdown(
                    id="category-filter",
                    options=[{"label": c, "value": c} for c in [
                        "All", "Steak", "Sushi", "Pizza", "Burgers", "Pasta", "Indian", "Chinese", "Thai", "Mexican", "Korean", "BBQ", "Seafood", "Vegan", "Middle Eastern", "French", "Spanish", "Vietnamese", "Greek", "Turkish", "Lebanese", "Caribbean", "African", "Tapas", "Deli", "Bakery", "Cafe", "Japanese", "Other"
                    ]],
                    value="All",
                    clearable=False,
                    style={"width": 250, "display": "inline-block"}
                ),
            ], style={"marginBottom": 20, "display": "flex", "alignItems": "center"}),
            html.Div([
                dcc.Graph(id="scatter-plot", config={"displayModeBar": False}, style={"width": "100%"}),
            ], id="plot-container", style={"width": "100%", "aspectRatio": "1 / 1", "maxWidth": 800, "maxHeight": 800, "margin": "0 auto"}),
        ], width=6, style={"minWidth": 350, "marginTop": 20}),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Add a Submission", style={"color": prussian_blue})),
                dbc.CardBody([
                    dbc.Form([
                        dbc.Label("Value (0-100%)"),
                        dbc.Input(id="value", type="number", min=0, max=100, step=0.01, required=True),
                        dbc.Label("Quality (0-100%)"),
                        dbc.Input(id="quality", type="number", min=0, max=100, step=0.01, required=True),
                        dbc.Label("Type"),
                        dcc.Dropdown(id="type", options=[{"label": "Restaurant", "value": "Restaurant"}], value="Restaurant", searchable=True),
                        dbc.Label("Category"),
                        dcc.Dropdown(id="category", options=[{"label": c, "value": c} for c in [
                            "Steak", "Sushi", "Pizza", "Burgers", "Pasta", "Indian", "Chinese", "Thai", "Mexican", "Korean", "BBQ", "Seafood", "Vegan", "Middle Eastern", "French", "Spanish", "Vietnamese", "Greek", "Turkish", "Lebanese", "Caribbean", "African", "Tapas", "Deli", "Bakery", "Cafe", "Japanese", "Other"
                        ]], value="Steak", searchable=True),
                        dbc.Label("Name"),
                        dbc.Input(id="name", type="text", maxLength=100, required=True),
                        dbc.Label("Location"),
                        dcc.Dropdown(id="location", options=[{"label": c, "value": c} for c in ["London", "New York", "Paris", "Tokyo", "Berlin", "Sydney", "Rome", "Toronto", "San Francisco", "Singapore"]], value="London", searchable=True),
                        html.Br(),
                        dbc.Button("Submit", id="submit-btn", color="primary", style={"background": prussian_blue}, disabled=True),
                        html.Div(id="form-alert", style={"marginTop": 10}),
                    ])
                ])
            ])
        ], width=6, style={"minWidth": 350, "marginTop": 125, "paddingTop": 95}),  # Increased paddingTop to 20px
    ], align="start", style={"marginTop": 40}),
    # Hidden empty user-table to satisfy Dash callback requirements
    dash_table.DataTable(
        id="user-table",
        data=[],
        columns=[
            {"name": "ID", "id": "id"},
            {"name": "Value", "id": "value"},
            {"name": "Quality", "id": "quality"},
            {"name": "Type", "id": "type"},
            {"name": "Category", "id": "category"},
            {"name": "Name", "id": "name"},
            {"name": "Location", "id": "location"},
            {"name": "User", "id": "user_id"},
            {"name": "Date", "id": "date_submitted"},
            {"name": "Remove", "id": "remove"},
        ],
        style_table={"display": "none"},  # Use style_table instead of style
    ),
    html.Div(id="user-table-container", style={"marginTop": 40, "paddingLeft": 20, "paddingRight": 20, "paddingBottom": 30}),
], fluid=True)

# --- Upvote in-memory cache (thread-safe, periodic DB flush) ---
import threading
import time

def load_upvote_cache():
    """Load all upvotes from the database into the in-memory cache."""
    global upvote_cache, upvote_user_cache
    print(f"[CACHEDEBUG] load_upvote_cache called", flush=True)
    with upvote_lock:
        upvote_cache.clear()
        upvote_user_cache.clear()
        with SessionLocal() as db:
            upvote_rows = db.query(SubmissionUpvote).all()
            for upvote in upvote_rows:
                upvote_cache[upvote.submission_id] = upvote_cache.get(upvote.submission_id, 0) + 1
                user_set = upvote_user_cache.setdefault(upvote.submission_id, set())
                user_set.add(upvote.voter_id)
    print(f"[CACHEDEBUG] upvote_cache after load: {upvote_cache}", flush=True)
    print(f"[CACHEDEBUG] upvote_user_cache after load: {upvote_user_cache}", flush=True)

# Global upvote cache and lock
upvote_cache = {}
upvote_user_cache = {}
pending_upvote_changes = []  # List of (submission_id, voter_id, category, type_, action)
upvote_lock = threading.Lock()
CACHE_FLUSH_INTERVAL = 30  # seconds

# Load upvote cache on startup
load_upvote_cache()

def get_upvote_count(submission_id):
    with upvote_lock:
        return upvote_cache.get(submission_id, 0)

def has_user_upvoted(submission_id, voter_id):
    with upvote_lock:
        return voter_id in upvote_user_cache.get(submission_id, set())

def toggle_upvote(submission_id, voter_id, category, type_):
    print(f"[CACHEDEBUG] toggle_upvote called for submission_id={submission_id}, voter_id={voter_id}", flush=True)
    with upvote_lock:
        user_set = upvote_user_cache.setdefault(submission_id, set())
        if voter_id in user_set:
            user_set.remove(voter_id)
            upvote_cache[submission_id] = upvote_cache.get(submission_id, 0) - 1
            pending_upvote_changes.append((submission_id, voter_id, category, type_, "remove"))
            print(f"[CACHEDEBUG] upvote REMOVED: {upvote_cache}", flush=True)
        else:
            user_set.add(voter_id)
            upvote_cache[submission_id] = upvote_cache.get(submission_id, 0) + 1
            pending_upvote_changes.append((submission_id, voter_id, category, type_, "add"))
            print(f"[CACHEDEBUG] upvote ADDED: {upvote_cache}", flush=True)
    flush_upvote_changes()

def flush_upvote_changes():
    """Write all pending upvote changes to the database immediately."""
    global pending_upvote_changes
    with upvote_lock:
        if not pending_upvote_changes:
            return
        with SessionLocal() as db:
            for submission_id, voter_id, category, type_, action in pending_upvote_changes:
                if action == "add":
                    # Insert if not exists
                    exists = db.query(SubmissionUpvote).filter_by(submission_id=submission_id, voter_id=voter_id).first()
                    if not exists:
                        db.add(SubmissionUpvote(submission_id=submission_id, voter_id=voter_id, category=category, type=type_))
                elif action == "remove":
                    db.query(SubmissionUpvote).filter_by(submission_id=submission_id, voter_id=voter_id).delete(synchronize_session=False)
            db.commit()
        pending_upvote_changes.clear()

# --- New weighting methodology for restaurant submissions ---
def get_restaurant_weights(subs, vote_factor=1.0, date_factor=0.3):
    N = len(subs)
    if N == 0:
        return [], []
    base_weight = 1.0 / N
    upvotes_list = [get_upvote_count(s.id) for s in subs]
    avg_upvotes = sum(upvotes_list) / N if N else 1
    now = datetime.utcnow()
    date_scores = [get_date_weight(s, now=now) for s in subs]
    avg_date_score = sum(date_scores) / N if N else 1
    # Vote scalar: relative to average, but always >= 0.5
    vote_scalars = [max(0.5, (v / avg_upvotes if avg_upvotes > 0 else 1.0)) for v in upvotes_list]
    # Date scalar: relative to average, but always >= 0.5
    date_scalars = [max(0.5, (d / avg_date_score if avg_date_score > 0 else 1.0)) for d in date_scores]
    # Final score: base_weight * (1 + vote_factor * (vote_scalar-1)) * (1 + date_factor * (date_scalar-1))
    final_scores = [
        base_weight * (1 + vote_factor * (vs-1)) * (1 + date_factor * (ds-1))
        for vs, ds in zip(vote_scalars, date_scalars)
    ]
    total_score = sum(final_scores)
    if total_score == 0:
        norm_weights = [100.0 / N] * N
    else:
        norm_weights = [(w / total_score) * 100 for w in final_scores]
    return norm_weights, upvotes_list

def get_date_weight(sub, now=None):
    """
    Returns a recency weight for a submission.
    More recent = higher weight. Exponential decay, 90 days half-life. Lower bound 0.25.
    """
    if not hasattr(sub, "date_submitted") or not sub.date_submitted:
        return 1.0
    if now is None:
        now = datetime.utcnow()
    days_ago = (now - sub.date_submitted).days
    # Half-life of 90 days: weight = 0.5 ** (days_ago / 90), but never less than 0.25
    return max(0.25, 0.5 ** (days_ago / 90))

# --- Update main chart to use weights instead of averages ---
def get_main_chart_subs(filter_category=None):
    subs = get_submissions()
    if filter_category and filter_category != "All":
        subs = [s for s in subs if s.category == filter_category]
    from collections import defaultdict
    grouped = defaultdict(list)
    for s in subs:
        key = (s.name, s.category)
        grouped[key].append(s)
    chart_subs = []
    chart_counts = []
    for group in grouped.values():
        norm_weights, _ = get_restaurant_weights(group)
        total_weight = sum(norm_weights)
        if total_weight == 0:
            avg_value = sum(s.value for s in group) / len(group)
            avg_quality = sum(s.quality for s in group) / len(group)
        else:
            avg_value = sum(s.value * w for s, w in zip(group, norm_weights)) / sum(norm_weights)
            avg_quality = sum(s.quality * w for s, w in zip(group, norm_weights)) / sum(norm_weights)
        s0 = group[0]
        chart_subs.append(type('ChartSub', (), {
            'name': s0.name,
            'category': s0.category,
            'type': s0.type,
            'location': s0.location,
            'value': avg_value,
            'quality': avg_quality
        }))
        chart_counts.append(len(group))
    return chart_subs, chart_counts

def get_main_chart_subs_from_list(subs):
    if not subs:
        return [], []
    from collections import defaultdict
    grouped = defaultdict(list)
    for s in subs:
        key = (s.name, s.category)
        grouped[key].append(s)
    chart_subs = []
    chart_counts = []
    for group in grouped.values():
        norm_weights, _ = get_restaurant_weights(group)
        total_weight = sum(norm_weights)
        if total_weight == 0:
            avg_value = sum(s.value for s in group) / len(group)
            avg_quality = sum(s.quality for s in group) / len(group)
        else:
            avg_value = sum(s.value * w for s, w in zip(group, norm_weights)) / sum(norm_weights)
            avg_quality = sum(s.quality * w for s, w in zip(group, norm_weights)) / sum(norm_weights)
        s0 = group[0]
        chart_subs.append(type('ChartSub', (), {
            'name': s0.name,
            'category': s0.category,
            'type': s0.type,
            'location': s0.location,
            'value': avg_value,
            'quality': avg_quality
        }))
        chart_counts.append(len(group))
    return chart_subs, chart_counts

# --- Update main chart callback ---
@app.callback(
    Output("scatter-plot", "figure"),
    Output("user-table-container", "children"),
    Input("category-filter", "value"),
    Input("show-mine-toggle", "data"),
    Input("user-table", "active_cell"),
    Input("submit-btn", "n_clicks"),
    Input("form-alert", "children"),  # NEW: triggers on submission
    Input("profile-modal", "is_open"), # NEW: triggers on modal open/close
    State("user-table", "data"),
    State("login-state", "data"),
    State("value", "value"),
    State("quality", "value"),
    State("type", "value"),
    State("category", "value"),
    State("name", "value"),
    State("location", "value"),
    State("category-filter", "value"),
    State("show-mine-toggle", "data"),
    # No prevent_initial_call so it runs on page load
)
def combined_scatter_and_remove(
    filter_category, show_mine, active_cell, n_clicks, form_alert, modal_is_open,
    data, login_state, value, quality, type_, category, name, location, filter_category2, show_mine2
):
    ctx = callback_context
    user_id = None
    user_email = None
    try:
        user_id = get_current_user_id()
        user_email = get_current_user_email()
    except Exception:
        user_id = None
        user_email = None
    norm_user_id = (user_id or "").strip().lower()
    norm_user_email = (user_email or "").strip().lower()
    admin_env = os.getenv("ADMIN_EMAIL", "admin@example.com").strip().lower()
    is_admin = (norm_user_email == admin_env) or (norm_user_id == admin_env)
    deleted = False
    # Remove action
    if ctx.triggered and ctx.triggered[0]["prop_id"].startswith("user-table.active_cell") and active_cell and active_cell.get("column_id") == "remove":
        row = data[active_cell["row"]]
        print(f"[DEBUG] Attempting delete: row_id={row['id']} user_id={user_id} user_email={user_email} is_admin={is_admin}")
        print(f"[ABSDEBUG] About to call delete_submission for row_id={row['id']}", flush=True)
        print(f"[ABSDEBUG] delete_submission_real ref: {delete_submission_real}", flush=True)
        print(f"[ABSDEBUG] CALLBACK PID: {os.getpid()}", flush=True)
        try:
            print(f"[ABSDEBUG] About to actually CALL delete_submission_real for row_id={row['id']}", flush=True)
            delete_submission_real(row["id"], user_id, user_email)
            print(f"[ABSDEBUG] Finished call to delete_submission_real for row_id={row['id']}", flush=True)
        except Exception as e:
            import traceback
            print(f"[ABSDEBUG] Exception when calling delete_submission_real: {e}", flush=True)
            traceback.print_exc()
        deleted = True
    # Get submissions for chart
    if show_mine and (user_id or user_email):
        # Only show current user's submissions in chart
        subs = get_user_submissions(user_id, user_email)
        if filter_category and filter_category != "All":
            subs = [s for s in subs if s.category == filter_category]
    else:
        if filter_category and filter_category != "All":
            subs = [s for s in get_submissions() if s.category == filter_category]
        else:
            subs = get_submissions()
    chart_subs, chart_counts = get_main_chart_subs_from_list(subs)
    fig = go.Figure()
    # Draw grid regions (flip axes: Value on x, Quality on y)
    for i in range(3):
        for j in range(3):
            fig.add_shape(type="rect",
                x0=i*100/3, x1=(i+1)*100/3,
                y0=j*100/3, y1=(j+1)*100/3,
                fillcolor=region_colors[j][i],
                opacity=0.3,
                line={"width": 1, "color": "#222"},
                layer="below"
            )
    # Draw bold grid lines (vertical for Value, horizontal for Quality)
    for k in range(1, 3):
        fig.add_shape(type="line", x0=k*100/3, x1=k*100/3, y0=0, y1=100, line={"color": "#222", "width": 2})
        fig.add_shape(type="line", y0=k*100/3, y1=k*100/3, x0=0, x1=100, line={"color": "#222", "width": 2})
    # Add points (flip axes)
    if chart_subs:
        fig.add_trace(go.Scatter(
            x=[s.value for s in chart_subs],
            y=[s.quality for s in chart_subs],
            text=[f"{s.name}<br>{s.category}<br>Value: {s.value:.1f}<br>Quality: {s.quality:.1f}<br>Submissions: {count}" for s, count in zip(chart_subs, chart_counts)],
            hoverinfo="text",
            mode="markers",
            marker={"size": 14, "color": prussian_blue, "line": {"width": 2, "color": "#fff"}, "opacity": 1.0},
        ))
    fig.update_layout(
        autosize=True,
        width=None, height=None,
        margin={"l": 110, "r": 20, "t": 90, "b": 40},
        xaxis={
            "range": [0, 100],
            "title": None,
            "showgrid": False,
            "zeroline": False,
            "scaleanchor": "y",
            "scaleratio": 1,
            "showticklabels": False,
        },
        yaxis={
            "range": [100, 0],
            "title": None,
            "showgrid": False,
            "zeroline": False,
            "scaleanchor": "x",
            "scaleratio": 1,
            "showticklabels": False,
        },
        plot_bgcolor="#fff",
        paper_bgcolor="#fff",
        annotations=[
            dict(x=1/6, y=1.08, text="Cheap", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            dict(x=0.5, y=1.08, text="Mod Value", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            dict(x=5/6, y=1.08, text="Expensive", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            dict(x=-0.13, y=1/6, text="High Q", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
            dict(x=-0.13, y=0.5, text="Mod Q", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
            dict(x=-0.13, y=5/6, text="Low Q", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
        ]
    )
    # Table logic
    table = None
    if show_mine:
        # Show user's own submissions only
        if user_id or user_email:
            table = get_user_table(user_id, show_mine=True, filter_category=filter_category, user_email=user_email)
        else:
            table = html.Div()
    else:
        # Show all submissions only for admin
        if is_admin:
            table = get_user_table(user_id, show_mine=False, filter_category=filter_category, user_email=user_email)
        else:
            table = html.Div()
    if table is None:
        table = html.Div()
    # If a delete just happened, force update by returning new objects
    if deleted:
        return fig, table
    return fig, table

# --- Modal and upvote logic: weighted value/quality display above table, upvote system, no callback errors ---
@app.callback(
    [Output("profile-modal", "is_open"),
     Output("profile-title", "children"),
     Output("profile-body", "children"),
     Output("selected-restaurant", "data")],
    [Input("scatter-plot", "clickData"),
     Input("close-profile-modal", "n_clicks")],
    [State("profile-modal", "is_open"),
     State("selected-restaurant", "data")],
    prevent_initial_call=True
)
def display_profile_modal(clickData, close_clicks, is_open, selected_data):
    ctx = callback_context
    triggered = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else None
    print(f"[MODALDEBUG] Modal triggered by: {triggered}", flush=True)
    if triggered == "close-profile-modal" and is_open:
        # Reset selected-restaurant to None so clicking the same point will always open modal
        return False, dash.no_update, dash.no_update, None
    if triggered == "scatter-plot" and clickData:
        point = clickData["points"][0]
        text = point.get("text", "")
        lines = text.split("<br>")
        name = lines[0] if len(lines) > 0 else ""
        category = lines[1] if len(lines) > 1 else ""
        # Always open modal, even if same restaurant as before
        with SessionLocal() as db:
            subs = db.query(Submission).filter(Submission.name == name, Submission.category == category).all()
        print(f"[MODALDEBUG] Submissions for {name}/{category}: {[s.id for s in subs]}", flush=True)
        if not subs:
            body = html.Div("No submissions found.")
        else:
            subs = sorted(subs, key=lambda s: s.date_submitted or datetime.min, reverse=True)
            user_id = get_current_user_id()
            user_rows = []
            all_values = [s.value for s in subs]
            m = sum(all_values) / len(all_values) if all_values else 50
            now = datetime.utcnow()
            norm_weights, upvotes_list = get_restaurant_weights(subs)
            print(f"[MODALDEBUG] Upvotes list: {upvotes_list}", flush=True)
            print(f"[MODALDEBUG] Upvote cache: {upvote_cache}", flush=True)
            total_weight = sum(norm_weights)
            if total_weight == 0:
                weighted_value = sum(s.value for s in subs) / len(subs)
                weighted_quality = sum(s.quality for s in subs) / len(subs)
            else:
                weighted_value = sum(s.value * w for s, w in zip(subs, norm_weights)) / sum(norm_weights)
                weighted_quality = sum(s.quality * w for s, w in zip(subs, norm_weights)) / sum(norm_weights)
            min_w, max_w = min(norm_weights), max(norm_weights)
            def norm_opacity(w):
                if max_w == min_w:
                    return 1.0
                return 0.2 + 0.8 * (w - min_w) / (max_w - min_w)
            mini_fig = go.Figure()
            for i in range(3):
                for j in range(3):
                    mini_fig.add_shape(type="rect",
                        x0=i*100/3, x1=(i+1)*100/3,
                        y0=j*100/3, y1=(j+1)*100/3,
                        fillcolor=region_colors[j][i],
                        opacity=0.3,
                        line={"width": 1, "color": "#222"},
                        layer="below"
                    )
            for k in range(1, 3):
                mini_fig.add_shape(type="line", x0=k*100/3, x1=k*100/3, y0=0, y1=100, line={"color": "#222", "width": 2})
                mini_fig.add_shape(type="line", y0=k*100/3, y1=k*100/3, x0=0, x1=100, line={"color": "#222", "width": 2})
            mini_fig.add_trace(go.Scatter(
                x=[s.value for s in subs],
                y=[s.quality for s in subs],
                mode="markers",
                marker={
                    "size": 18,
                    "color": prussian_blue,
                    "opacity": [norm_opacity(w) for w in norm_weights],
                    "line": {"width": 2, "color": "#fff"}
                },
                text=[f"{get_user_initials(s.user_id)}<br>Value: {s.value:.0f}<br>Quality: {s.quality:.0f}<br>Final Weight: {w:.2f}%" for s, w in zip(subs, norm_weights)],
                hoverinfo="text",
            ))
            mini_fig.update_layout(
                width=320, height=320,
                margin={"l": 60, "r": 10, "t": 40, "b": 60},
                xaxis={
                    "range": [0, 100],
                    "showticklabels": False,  # Hide axis values
                    "showgrid": False,
                    "zeroline": False,
                    "title": "Value (%)",
                    "title_standoff": 10,
                },
                yaxis={
                    "range": [100, 0],
                    "showticklabels": False,  # Hide axis values
                    "showgrid": False,
                    "zeroline": False,
                    "title": "Quality (%)",
                    "title_standoff": 10,
                },
                plot_bgcolor="#fff",
                paper_bgcolor="#fff",
                title={"text": "Mini Chart (This Restaurant)", "x": 0, "xanchor": "left", "font": {"size": 20, "color": prussian_blue}},
                annotations=[]
            )
            for i, s in enumerate(subs):
                upvotes = upvotes_list[i]
                final_weight = norm_weights[i]
                user_has_upvoted = has_user_upvoted(s.id, user_id) if user_id else False
                print(f"[MODALDEBUG] Submission {s.id}: upvotes={upvotes}, user_has_upvoted={user_has_upvoted}", flush=True)
                upvote_btn = dbc.Button(
                    [
                        html.Span("▲", style={"color": prussian_blue if user_has_upvoted else "#aaa", "fontWeight": "bold", "fontSize": 18}),
                        html.Span(f" {upvotes}", style={"marginLeft": 4, "color": prussian_blue if user_has_upvoted else "#aaa"})
                    ],
                    id={"type": "upvote-btn", "index": s.id},
                    color="link",
                    style={"padding": "0 8px", "minWidth": 0},
                    n_clicks=0,
                    disabled=False
                )
                user_rows.append(html.Tr([
                    html.Td(get_user_initials(s.user_id)),
                    html.Td(f"{s.value:.0f}"),
                    html.Td(f"{s.quality:.0f}"),
                    html.Td(s.date_submitted.strftime("%Y-%m-%d") if s.date_submitted else "-"),
                    html.Td(f"{final_weight:.1f}%", style={"color": prussian_blue, "fontWeight": 600}),
                    html.Td(upvote_btn),
                ]))
            body = html.Div([
                html.H5(f"Category: {category}"),
                html.Div([
                    html.Div([
                        html.Strong("Weighted Value: "),
                        html.Span(f"{weighted_value:.1f}")
                    ], style={"display": "inline-block", "marginRight": 24, "fontSize": 18, "color": prussian_blue}),
                    html.Div([
                        html.Strong("Weighted Quality: "),
                        html.Span(f"{weighted_quality:.1f}")
                    ], style={"display": "inline-block", "fontSize": 18, "color": prussian_blue}),
                ], style={"marginBottom": 12, "marginTop": 8}),
                html.Div(
                    dcc.Graph(figure=mini_fig, config={"displayModeBar": False}, style={"margin": "0 auto", "maxWidth": 340, "marginBottom": 32, "marginTop": 8}),
                    style={"display": "flex", "justifyContent": "center", "alignItems": "center", "width": "100%"}
                ),
                html.H6("User Submissions (most recent first):", style={"marginTop": 24, "marginBottom": 12}),
                dbc.Table([
                    html.Thead(html.Tr([
                        html.Th("User"), html.Th("Value"), html.Th("Quality"), html.Th("Date"), html.Th("Final Weight"), html.Th("Upvote")  # Upvote last
                    ])),
                    html.Tbody(user_rows)
                ], bordered=True, hover=True, size="sm", style={"marginBottom": 0, "marginTop": 0}),
            ], style={"padding": "0 8px 8px 8px", "width": "100%"})
        # Always update selected-restaurant so clicking the same point works
        return True, name, body, {"name": name, "category": category}
    return is_open, dash.no_update, dash.no_update, selected_data

@app.callback(
    Output("profile-body", "children", allow_duplicate=True),
    Input({"type": "upvote-btn", "index": ALL}, "n_clicks"),
    State("selected-restaurant", "data"),
    State("profile-body", "children"),
    prevent_initial_call=True
)
def fast_upvote_refresh(n_clicks_list, selected_data, profile_body):
    ctx = callback_context
    if not ctx.triggered or not selected_data:
        return dash.no_update
    triggered = ctx.triggered[0]["prop_id"].split(".")[0]
    import json
    try:
        btn_id = json.loads(triggered)
        if btn_id.get("type") != "upvote-btn":
            return dash.no_update
        submission_id = btn_id["index"]
    except Exception:
        return dash.no_update
    user_id = get_current_user_id()
    if not user_id:
        return dash.no_update
    # Re-query all submissions for this restaurant (sorted as in modal)
    with SessionLocal() as db:
        subs = db.query(Submission).filter(
            Submission.name == selected_data.get("name"),
            Submission.category == selected_data.get("category")
        ).order_by(sa.desc(Submission.date_submitted)).all()
        # Find the index of the submission in the sorted list
        idx = next((i for i, s in enumerate(subs) if s.id == submission_id), None)
        if idx is None or not isinstance(n_clicks_list, list) or idx >= len(n_clicks_list):
            return dash.no_update
        n_clicks = n_clicks_list[idx]
        # Only toggle upvote if n_clicks is odd and > 0 (i.e., just clicked)
        if n_clicks is None or n_clicks % 2 == 0 or n_clicks <= 0:
            return dash.no_update
        sub = subs[idx]
        toggle_upvote(submission_id, user_id, sub.category, sub.type)
    # Rebuild modal body only
    subs = sorted(subs, key=lambda s: s.date_submitted or datetime.min, reverse=True)
    user_rows = []
    all_values = [s.value for s in subs]
    m = sum(all_values) / len(all_values) if all_values else 50
    now = datetime.utcnow()
    norm_weights, upvotes_list = get_restaurant_weights(subs)
    total_weight = sum(norm_weights)
    if total_weight == 0:
        weighted_value = sum(s.value for s in subs) / len(subs)
        weighted_quality = sum(s.quality for s in subs) / len(subs)
    else:
        weighted_value = sum(s.value * w for s, w in zip(subs, norm_weights)) / sum(norm_weights)
        weighted_quality = sum(s.quality * w for s, w in zip(subs, norm_weights)) / sum(norm_weights)
    min_w, max_w = min(norm_weights), max(norm_weights)
    def norm_opacity(w):
        if max_w == min_w:
            return 1.0
        return 0.2 + 0.8 * (w - min_w) / (max_w - min_w)
    mini_fig = go.Figure()
    for i in range(3):
        for j in range(3):
            mini_fig.add_shape(type="rect",
                x0=i*100/3, x1=(i+1)*100/3,
                y0=j*100/3, y1=(j+1)*100/3,
                fillcolor=region_colors[j][i],
                opacity=0.3,
                line={"width": 1, "color": "#222"},
                layer="below"
            )
    for k in range(1, 3):
        mini_fig.add_shape(type="line", x0=k*100/3, x1=k*100/3, y0=0, y1=100, line={"color": "#222", "width": 2})
        mini_fig.add_shape(type="line", y0=k*100/3, y1=k*100/3, x0=0, x1=100, line={"color": "#222", "width": 2})
    mini_fig.add_trace(go.Scatter(
        x=[s.value for s in subs],
        y=[s.quality for s in subs],
        mode="markers",
        marker={
            "size": 18,
            "color": prussian_blue,
            "opacity": [norm_opacity(w) for w in norm_weights],
            "line": {"width": 2, "color": "#fff"}
        },
        text=[f"{get_user_initials(s.user_id)}<br>Value: {s.value:.0f}<br>Quality: {s.quality:.0f}<br>Final Weight: {w:.2f}%" for s, w in zip(subs, norm_weights)],
        hoverinfo="text",
    ))
    mini_fig.update_layout(
        width=320, height=320,
        margin={"l": 60, "r": 10, "t": 40, "b": 60},
        xaxis={
            "range": [0, 100],
            "showticklabels": False,
            "showgrid": False,
            "zeroline": False,
            "title": "Value (%)",
            "title_standoff": 10,
        },
        yaxis={
            "range": [100, 0],
            "showticklabels": False,
            "showgrid": False,
            "zeroline": False,
            "title": "Quality (%)",
            "title_standoff": 10,
        },
        plot_bgcolor="#fff",
        paper_bgcolor="#fff",
        title={"text": "Mini Chart (This Restaurant)", "x": 0, "xanchor": "left", "font": {"size": 20, "color": prussian_blue}},
        annotations=[]
    )
    for i, s in enumerate(subs):
        upvotes = upvotes_list[i]
        final_weight = norm_weights[i]
        user_has_upvoted = has_user_upvoted(s.id, user_id) if user_id else False
        upvote_btn = dbc.Button(
            [
                html.Span("▲", style={"color": prussian_blue if user_has_upvoted else "#aaa", "fontWeight": "bold", "fontSize": 18}),
                html.Span(f" {upvotes}", style={"marginLeft": 4, "color": prussian_blue if user_has_upvoted else "#aaa"})
            ],
            id={"type": "upvote-btn", "index": s.id},
            color="link",
            style={"padding": "0 8px", "minWidth": 0},
            n_clicks=0,
            disabled=False
        )
        user_rows.append(html.Tr([
            html.Td(get_user_initials(s.user_id)),
            html.Td(f"{s.value:.0f}"),
            html.Td(f"{s.quality:.0f}"),
            html.Td(s.date_submitted.strftime("%Y-%m-%d") if s.date_submitted else "-"),
            html.Td(f"{final_weight:.1f}%", style={"color": prussian_blue, "fontWeight": 600}),
            html.Td(upvote_btn),
        ]))
    body = html.Div([
        html.H5(f"Category: {selected_data.get('category', '')}"),
        html.Div([
            html.Div([
                html.Strong("Weighted Value: "),
                html.Span(f"{weighted_value:.1f}")
            ], style={"display": "inline-block", "marginRight": 24, "fontSize": 18, "color": prussian_blue}),
            html.Div([
                html.Strong("Weighted Quality: "),
                html.Span(f"{weighted_quality:.1f}")
            ], style={"display": "inline-block", "fontSize": 18, "color": prussian_blue}),
        ], style={"marginBottom": 12, "marginTop": 8}),
        html.Div(
            dcc.Graph(figure=mini_fig, config={"displayModeBar": False}, style={"margin": "0 auto", "maxWidth": 340, "marginBottom": 32, "marginTop": 8}),
            style={"display": "flex", "justifyContent": "center", "alignItems": "center", "width": "100%"}
        ),
        html.H6("User Submissions (most recent first):", style={"marginTop": 24, "marginBottom": 12}),
        dbc.Table([
            html.Thead(html.Tr([
                html.Th("User"), html.Th("Value"), html.Th("Quality"), html.Th("Date"), html.Th("Final Weight"), html.Th("Upvote")
            ])),
            html.Tbody(user_rows)
        ], bordered=True, hover=True, size="sm", style={"marginBottom": 0, "marginTop": 0}),
    ], style={"padding": "0 8px 8px 8px", "width": "100%"})
    return body

# --- DB startup test ---
def db_startup_test():
    import os
    import sys
    import traceback
    print(f"[DBTEST] Process PID: {os.getpid()}", flush=True)
    try:
        # Try to open DB file for writing
        db_path = DATABASE_URL.replace('sqlite:///', '')
        with open(db_path, 'a') as f:
            f.write('')
        print(f"[DBTEST] DB file {db_path} is writable.", flush=True)
    except Exception as e:
        print(f"[DBTEST] Cannot write to DB file: {e}", flush=True)
    try:
        with SessionLocal() as db:
            print("[DBTEST] Opened DB session.", flush=True)
            # Try a simple query
            count = db.query(Submission).count()
            print(f"[DBTEST] Submission count: {count}", flush=True)
    except Exception as e:
        print(f"[DBTEST] Exception opening DB session: {e}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
db_startup_test()

# --- Add callback to update login/logout section ---
@app.callback(
    Output("login-section", "children"),
    [Input("login-state", "data"), Input("url", "pathname")],
    prevent_initial_call=False
)
def update_login_section(_, __):
    return get_login_section()

# --- Add callback to update show-mine-toggle from radio button ---
@app.callback(
    Output("show-mine-toggle", "data"),
    Input("show-mine-radio", "value"),
    prevent_initial_call=False
)
def update_show_mine_toggle(radio_value):
    return radio_value

# --- Enable/disable submit button based on form validity and login ---
@app.callback(
    Output("submit-btn", "disabled"),
    [Input("value", "value"),
     Input("quality", "value"),
     Input("type", "value"),
     Input("category", "value"),
     Input("name", "value"),
     Input("location", "value"),
     Input("login-section", "children")],
    prevent_initial_call=False
)
def enable_submit(value, quality, type_, category, name, location, login_children):
    # Check if user is logged in
    logged_in = False
    if login_children:
        # Check for 'Log out' in the children (string or html)
        if isinstance(login_children, list):
            for child in login_children:
                if hasattr(child, 'props') and 'Log out' in str(child):
                    logged_in = True
        elif hasattr(login_children, 'props') and 'Log out' in str(login_children):
            logged_in = True
        elif 'Log out' in str(login_children):
            logged_in = True
    # All fields must be filled and user logged in
    if value is not None and quality is not None and type_ and category and name and location and logged_in:
        return False
    return True

# --- Handle submission ---
@app.callback(
    Output("form-alert", "children"),
    Input("submit-btn", "n_clicks"),
    [State("value", "value"),
     State("quality", "value"),
     State("type", "value"),
     State("category", "value"),
     State("name", "value"),
     State("location", "value")],
    prevent_initial_call=True
)
def handle_submit(n_clicks, value, quality, type_, category, name, location):
    if not n_clicks:
        return ""
    # Validate again
    if value is None or quality is None or not type_ or not category or not name or not location:
        return dbc.Alert("Please fill in all fields.", color="danger")
    # Check login
    user = get_current_user()
    if not user:
        return dbc.Alert("You must be logged in to submit.", color="danger")
    # Add submission
    try:
        add_submission({
            "value": value,
            "quality": quality,
            "type": type_,
            "category": category,
            "name": name,
            "location": location
        })
        return dbc.Alert("Submission successful!", color="success")
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger")

@app.server.route("/logout")
def logout():
    flask_session.clear()
    return flask_redirect("/")