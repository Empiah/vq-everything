# Value and Quality Everything

A modern Dash web app for collecting and visualizing user submissions on a 3x3 value/quality scatter plot grid. Features Google login, SQLite storage, and a beautiful Plotly chart.

## Features

- Google OAuth 2.0 login (secure, no passwords stored)
- Submission form: value (0-100), quality (0-100), type, category, name, location
- All data stored in SQLite (local file, not in git)
- Interactive 3x3 scatter plot grid (Plotly)
- Filter by category and user ("All Submissions" or "My Submissions")
- Responsive, mobile-friendly UI (Dash + Bootstrap)
- All secrets loaded from `.env` (never in git)

## Setup

1. **Clone the repo:**

   ```sh
   git clone https://github.com/yourusername/your-repo-name.git
   cd your-repo-name
   ```

2. **Create a virtual environment (recommended):**

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**

   ```sh
   pip install -r requirements.txt
   ```

4. **Create a `.env` file:**
   - Copy `.env.example` to `.env` and fill in your Google OAuth credentials and a strong Flask secret key.

5. **Run the app locally:**

   ```sh
   python app.py
   ```

   The app will be available at [http://127.0.0.1:8050](http://127.0.0.1:8050)

## Deploying to Production (Heroku/Render/etc.)

- Use the provided `Procfile` and `requirements.txt`.
- Set all environment variables (`.env` values) in your host's dashboard.
- Run with `gunicorn app:app.server` (see Procfile).

## Security

- `.env` and `submissions.db` are excluded from git by `.gitignore`.
- Never commit secrets or the database to your repo.

## License

MIT
