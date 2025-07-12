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
from flask import session, redirect as flask_redirect, url_for
from flask_dance.contrib.google import make_google_blueprint, google
from dotenv import load_dotenv
from dash import dash_table  # Updated import for dash_table
from datetime import datetime
from dash.dependencies import ALL

# Load environment variables from .env
load_dotenv()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")

# --- Database setup (SQLite, persistent for Render) ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./submissions.db")
engine = sa.create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    isolation_level="AUTOCOMMIT" if DATABASE_URL.startswith("sqlite") else None
)
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
def get_user_submissions(user_id_or_email):
    # Return submissions where user_id matches name or email (case-insensitive)
    if not user_id_or_email:
        return []
    with SessionLocal() as db:
        user_id_or_email = user_id_or_email.strip().lower()
        return db.query(Submission).filter(
            sa.or_(
                sa.func.lower(Submission.user_id) == user_id_or_email,
                sa.func.lower(Submission.user_id) == (user_id_or_email if '@' in user_id_or_email else None)
            )
        ).all()

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
        # Automatically upvote own submission
        db.add(SubmissionUpvote(submission_id=sub.id, voter_id=user_id, category=data["category"], type=data["type"]))
        db.commit()

# --- Helper: delete all submissions ---
def delete_all_submissions():
    with SessionLocal() as db:
        db.query(Submission).delete()
        db.commit()

# delete_all_submissions()  # Clear all submissions on app start (uncomment to use)

# --- Helper: delete a submission by id and user_id ---
def delete_submission(sub_id, user_id):
    # Allow admin to delete any record
    if user_id == ADMIN_EMAIL:
        with SessionLocal() as db:
            db.query(Submission).filter(Submission.id == sub_id).delete()
            db.commit()
    else:
        with SessionLocal() as db:
            db.query(Submission).filter(Submission.id == sub_id, Submission.user_id == user_id).delete()
            db.commit()

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
def get_user_table(user_id=None, show_mine=True, filter_category="All"):
    if show_mine and user_id:
        subs = get_user_submissions(user_id)
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

# Global upvote cache and lock
upvote_cache = {}
upvote_user_cache = {}
pending_upvote_changes = []  # List of (submission_id, voter_id, category, type_, action)
upvote_lock = threading.Lock()
CACHE_FLUSH_INTERVAL = 30  # seconds

def get_upvote_count(submission_id):
    with upvote_lock:
        return upvote_cache.get(submission_id, 0)

def has_user_upvoted(submission_id, voter_id):
    with upvote_lock:
        return voter_id in upvote_user_cache.get(submission_id, set())

def toggle_upvote(submission_id, voter_id, category, type_):
    with upvote_lock:
        user_set = upvote_user_cache.setdefault(submission_id, set())
        if voter_id in user_set:
            user_set.remove(voter_id)
            upvote_cache[submission_id] = upvote_cache.get(submission_id, 1) - 1
            pending_upvote_changes.append((submission_id, voter_id, category, type_, "remove"))
        else:
            user_set.add(voter_id)
            upvote_cache[submission_id] = upvote_cache.get(submission_id, 0) + 1
            pending_upvote_changes.append((submission_id, voter_id, category, type_, "add"))

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
    More recent = higher weight. Exponential decay, 30 days half-life.
    """
    if not hasattr(sub, "date_submitted") or not sub.date_submitted:
        return 1.0
    if now is None:
        now = datetime.utcnow()
    days_ago = (now - sub.date_submitted).days
    # Half-life of 30 days: weight = 0.5 ** (days_ago / 30)
    return 0.5 ** (days_ago / 30)

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

# --- Update main chart callback ---
@app.callback(
    Output("scatter-plot", "figure"),
    Output("user-table-container", "children"),
    Input("category-filter", "value"),
    Input("show-mine-toggle", "data"),
    Input("user-table", "active_cell"),
    Input("submit-btn", "n_clicks"),
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
def combined_scatter_and_remove(filter_category, show_mine, active_cell, n_clicks, data, login_state, value, quality, type_, category, name, location, filter_category2, show_mine2):
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
    # Remove action
    if ctx.triggered and ctx.triggered[0]["prop_id"].startswith("user-table.active_cell") and active_cell and active_cell.get("column_id") == "remove":
        row = data[active_cell["row"]]
        if not user_id or not login_state or not login_state.get("logged_in"):
            return dash.no_update, dash.no_update
        delete_submission(row["id"], user_id)
    # Get submissions for chart
    if filter_category and filter_category != "All":
        subs = [s for s in get_submissions() if s.category == filter_category]
    else:
        subs = get_submissions()
    chart_subs, chart_counts = get_main_chart_subs(filter_category)
    fig = go.Figure()
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
    for k in range(1, 3):
        fig.add_shape(type="line", x0=k*100/3, x1=k*100/3, y0=0, y1=100, line={"color": "#222", "width": 2})
        fig.add_shape(type="line", y0=k*100/3, y1=k*100/3, x0=0, x1=100, line={"color": "#222", "width": 2})
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
        if user_id:
            table = get_user_table(user_id, show_mine=True, filter_category=filter_category)
        else:
            table = html.Div()
    else:
        # Show all submissions only for admin
        if is_admin:
            table = get_user_table(user_id, show_mine=False, filter_category=filter_category)
        else:
            table = html.Div()
    if table is None:
        table = html.Div()
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
    if triggered == "close-profile-modal" and is_open:
        return False, dash.no_update, dash.no_update, None
    if triggered == "scatter-plot" and clickData:
        point = clickData["points"][0]
        text = point.get("text", "")
        lines = text.split("<br>")
        name = lines[0] if len(lines) > 0 else ""
        category = lines[1] if len(lines) > 1 else ""
        # Query DB for all submissions for this restaurant
        with SessionLocal() as db:
            subs = db.query(Submission).filter(Submission.name == name, Submission.category == category).all()
        if not subs:
            body = html.Div("No submissions found.")
        else:
            subs = sorted(subs, key=lambda s: s.date_submitted or datetime.min, reverse=True)
            user_id = get_current_user_id()
            user_rows = []
            all_values = [s.value for s in subs]
            m = sum(all_values) / len(all_values) if all_values else 50
            now = datetime.utcnow()
            # Compute raw final weights
            norm_weights, upvotes_list = get_restaurant_weights(subs)
            # Weighted average for this restaurant (live)
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
        submission_id = btn_id["index"]
    except Exception:
        return dash.no_update
    user_id = get_current_user_id()
    if not user_id:
        return dash.no_update
    with SessionLocal() as db:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if not sub:
            return dash.no_update
        toggle_upvote(submission_id, user_id, sub.category, sub.type)
        # Re-query upvote count and user status for all submissions in this restaurant
        subs = db.query(Submission).filter(Submission.name == selected_data.get("name"), Submission.category == selected_data.get("category")).all()
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