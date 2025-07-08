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
from flask import session, redirect, url_for
from flask_dance.contrib.google import make_google_blueprint, google
from dotenv import load_dotenv
from dash import dash_table  # Updated import for dash_table

# Load environment variables from .env
load_dotenv()

# --- Database setup ---
DATABASE_URL = "sqlite:///./submissions.db"
engine = sa.create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[WARNING] Could not create tables: {e}")

# --- Helper: get all submissions ---
def get_submissions():
    with SessionLocal() as db:
        return db.query(Submission).all()

# --- Helper: get submissions for a user ---
def get_user_submissions(user_id):
    with SessionLocal() as db:
        return db.query(Submission).filter(Submission.user_id == user_id).all()

# --- Helper: add a submission ---
def add_submission(data):
    user_id = get_current_user_id()
    data["user_id"] = user_id
    with SessionLocal() as db:
        sub = Submission(**data)
        db.add(sub)
        db.commit()

# --- Helper: delete all submissions ---
def delete_all_submissions():
    with SessionLocal() as db:
        db.query(Submission).delete()
        db.commit()

# delete_all_submissions()  # Clear all submissions on app start (uncomment to use)

# --- Helper: delete a submission by id and user_id ---
def delete_submission(sub_id, user_id):
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
    data = [
        {"id": s.id, "value": s.value, "quality": s.quality, "type": s.type, "category": s.category, "name": s.name, "location": s.location, "user_id": s.user_id, "remove": "Delete"}
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
        {"name": "User ID", "id": "user_id"},
        {"name": "Remove", "id": "remove"},  # Removed 'presentation': 'button'
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

def get_current_user():
    try:
        print("[DEBUG] flask_session keys:", list(flask_session.keys()))
        if "google_oauth_token" not in flask_session:
            print("[DEBUG] No google_oauth_token in session")
            return None
        resp = google.get("/oauth2/v2/userinfo")
        print("[DEBUG] google.get response:", resp)
        if resp.ok:
            print("[DEBUG] User info:", resp.json())
            return resp.json()
    except Exception as e:
        print("[DEBUG] Exception in get_current_user:", e)
        return None
    return None

def get_current_user_id():
    user = get_current_user()
    if user:
        return user.get("email")
    return None

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
            text=[f"{s.name}<br>{s.category}" for s in subs],
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
    dcc.Store(id="show-mine-toggle", data=True),
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
                        "All", "Steak", "Sushi", "Pizza", "Burgers", "Pasta", "Indian", "Chinese", "Thai", "Mexican", "Korean", "BBQ", "Seafood", "Vegan", "Middle Eastern", "French", "Spanish", "Vietnamese", "Greek", "Turkish", "Lebanese", "Caribbean", "African", "Tapas", "Deli", "Bakery", "Cafe", "Other"
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
                            "Steak", "Sushi", "Pizza", "Burgers", "Pasta", "Indian", "Chinese", "Thai", "Mexican", "Korean", "BBQ", "Seafood", "Vegan", "Middle Eastern", "French", "Spanish", "Vietnamese", "Greek", "Turkish", "Lebanese", "Caribbean", "African", "Tapas", "Deli", "Bakery", "Cafe", "Other"
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
            {"name": "User ID", "id": "user_id"},
            {"name": "Remove", "id": "remove"},
        ],
        style_table={"display": "none"},  # Use style_table instead of style
    ),
    html.Div(id="user-table-container", style={"marginTop": 40, "paddingLeft": 20, "paddingRight": 20, "paddingBottom": 30}),
], fluid=True)

# --- Callback to update login section and login state ---
@app.callback(
    Output("login-section", "children"),
    Output("login-state", "data"),
    Input("url", "pathname"),
)
def update_login_and_state(_):
    user = get_current_user()
    login_section = get_login_section()
    return login_section, {"logged_in": bool(user)}

# --- Combined callback for scatter-plot and table remove ---
@app.callback(
    Output("scatter-plot", "figure"),
    Output("user-table", "data"),
    Input("category-filter", "value"),
    Input("show-mine-toggle", "data"),
    Input("user-table", "active_cell"),
    Input("submit-btn", "n_clicks"),  # Add submit as input
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
    prevent_initial_call=True
)
def combined_scatter_and_remove(filter_category, show_mine, active_cell, n_clicks, data, login_state, value, quality, type_, category, name, location, filter_category2, show_mine2):
    ctx = callback_context
    user_id = get_current_user_id()
    # Determine if this is a remove action
    if ctx.triggered and ctx.triggered[0]["prop_id"].startswith("user-table.active_cell") and active_cell and active_cell.get("column_id") == "remove":
        row = data[active_cell["row"]]
        if not user_id or not login_state or not login_state.get("logged_in"):
            return dash.no_update, data
        delete_submission(row["id"], user_id)
        # After deletion, refresh data
        if show_mine and user_id:
            subs = get_user_submissions(user_id)
        else:
            subs = get_submissions()
        if filter_category and filter_category != "All":
            subs = [s for s in subs if s.category == filter_category]
        avg_subs = get_averaged_subs(subs)
        new_data = [d for d in data if d["id"] != row["id"]]
    else:
        # Not a remove action, or after submit, just update chart and table
        if show_mine and user_id:
            subs = get_user_submissions(user_id)
        else:
            subs = get_submissions()
        if filter_category and filter_category != "All":
            subs = [s for s in subs if s.category == filter_category]
        avg_subs = get_averaged_subs(subs)
        # Always recalculate table data
        new_data = [
            {"id": s.id, "value": s.value, "quality": s.quality, "type": s.type, "category": s.category, "name": s.name, "location": s.location, "user_id": s.user_id, "remove": "Delete"}
            for s in subs
        ]
    fig = go.Figure()
    # Draw grid regions (flip axes)
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
    if avg_subs:
        fig.add_trace(go.Scatter(
            x=[s.value for s in avg_subs],
            y=[s.quality for s in avg_subs],
            text=[f"{s.name}<br>{s.category}" for s in avg_subs],
            hoverinfo="text",
            mode="markers",
            marker={"size": 14, "color": prussian_blue, "line": {"width": 2, "color": "#fff"}},
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
            # Value (x) subtitles at the top (use yref='paper')
            dict(x=1/6, y=1.02, text="Cheap", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            dict(x=0.5, y=1.02, text="Mkt. Like", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            dict(x=5/6, y=1.02, text="Expensive", showarrow=False, xref="paper", yref="paper", xanchor="center", yanchor="bottom", font=dict(size=18, color=prussian_blue)),
            # Quality (y) subtitles at the left, vertical (use xref='paper')
            dict(x=-0.02, y=1/6, text="Low Quality", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
            dict(x=-0.02, y=0.5, text="Mod Quality", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
            dict(x=-0.02, y=5/6, text="High Quality", showarrow=False, xref="paper", yref="paper", xanchor="right", yanchor="middle", font=dict(size=18, color=prussian_blue), textangle=-90),
        ]
    )
    return fig, new_data

# --- Callback to enable/disable form and submit button based on login state ---
@app.callback(
    Output("value", "disabled"),
    Output("quality", "disabled"),
    Output("type", "disabled"),
    Output("category", "disabled"),
    Output("name", "disabled"),
    Output("location", "disabled"),
    Output("submit-btn", "disabled"),
    Input("login-state", "data"),
    Input("value", "value"),
    Input("quality", "value"),
    Input("type", "value"),
    Input("category", "value"),
    Input("name", "value"),
    Input("location", "value"),
)
def toggle_form(login_state, value, quality, type_, category, name, location):
    logged_in = login_state and login_state.get("logged_in", False)
    form_disabled = not logged_in
    submit_disabled = not (logged_in and value is not None and quality is not None and type_ and category and name and location)
    return [form_disabled]*6 + [submit_disabled]

# --- Callback to update show-mine-toggle store ---
@app.callback(
    Output("show-mine-toggle", "data"),
    Input("show-mine-radio", "value"),
)
def update_show_mine_toggle(value):
    return value

# --- Callback to handle form submission ---
@app.callback(
    Output("form-alert", "children"),
    Input("submit-btn", "n_clicks"),
    State("value", "value"),
    State("quality", "value"),
    State("type", "value"),
    State("category", "value"),
    State("name", "value"),
    State("location", "value"),
    prevent_initial_call=True
)
def handle_form_submission(n_clicks, value, quality, type_, category, name, location):
    if n_clicks:
        if value is None or quality is None or not name:
            return dbc.Alert("Please fill all required fields.", color="danger")
        else:
            add_submission({
                "value": value,
                "quality": quality,
                "type": type_,
                "category": category,
                "name": name,
                "location": location,
            })
            return dbc.Alert("Submission added!", color="success")
    return dash.no_update

# --- Logout route for Flask server ---
from flask import session as flask_session
@app.server.route("/logout")
def logout():
    flask_session.clear()
    return redirect("/")

# --- Callback to show/hide user-table based on show-mine-toggle ---
@app.callback(
    Output("user-table-container", "children"),
    Input("show-mine-toggle", "data"),
    Input("login-state", "data"),
    Input("category-filter", "value"),
)
def render_user_table(show_mine, login_state, filter_category):
    user_id = get_current_user_id()
    if show_mine and login_state and login_state.get("logged_in") and user_id:
        return get_user_table(user_id=user_id, show_mine=True, filter_category=filter_category)
    return None

if __name__ == "__main__":
    app.run(debug=False)
