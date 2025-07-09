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

## Deploying to Production (Render.com Example)

Render.com is a simple, reliable, and affordable way to deploy Python web apps like this one. The free tier is great for demos and light use.

### 1. Push your code to GitHub

Make sure your latest code is committed and pushed to a GitHub repository.

### 2. Create a new Web Service on Render

- Go to https://dashboard.render.com/
- Click **New +** > **Web Service**
- Connect your GitHub account and select your repo
- For **Environment**, choose `Python 3`
- For **Build Command**, enter:
  ```sh
  pip install -r requirements.txt
  ```
- For **Start Command**, enter:
  ```sh
  gunicorn app:app
  ```
- For **Instance Type**, the free tier is fine for most use cases

### 3. Add Environment Variables

- In the Render dashboard, go to your service's **Environment** tab
- Add all variables from your `.env` (except secrets—never commit `.env` to git)
- Example:
  - `GOOGLE_OAUTH_CLIENT_ID=...`
  - `GOOGLE_OAUTH_CLIENT_SECRET=...`
  - `FLASK_SECRET_KEY=...`

### 4. Persistent SQLite Storage (Optional)

By default, SQLite data will be lost on redeploy. For persistent storage:
- Go to the **Disks** tab in your Render service
- Add a disk (e.g., `/data`, 1GB is enough)
- In your code, change the database URL to:
  ```python
  DATABASE_URL = "sqlite:////data/submissions.db"
  ```
- Commit and push this change
- Your data will now persist across deploys

### 5. Deploy!

- Click **Manual Deploy** or push to your repo to trigger a deploy
- Your app will be live at the provided URL

---

## Security

- `.env` and `submissions.db` are excluded from git by `.gitignore`.
- Never commit secrets or the database to your repo.

## License

MIT
