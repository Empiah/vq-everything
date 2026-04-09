# Value and Quality Everything

A web app for collecting and visualizing user ratings on a 3x3 value/quality scatter plot. Users log in with Google, submit ratings for restaurants across categories, and see how their scores compare to the community.

## Features

- Google OAuth 2.0 login
- Submission form with value (0-100%), quality (0-100%), category, name, and location
- Interactive 3x3 scatter plot grid with category and user filtering
- Restaurant profile modals with weighted scoring and upvote system
- Google Places integration — search for restaurants to auto-fill name, location, and display Google rating/review data
- SQLite database with persistent storage support
- Responsive UI (Dash + Bootstrap)

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | Yes | Secret key for Flask session management |
| `ADMIN_EMAIL` | Yes | Admin user's email address |
| `GOOGLE_OAUTH_CLIENT_ID` | Yes | Google OAuth 2.0 client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Yes | Google OAuth 2.0 client secret |
| `GOOGLE_MAPS_API_KEY` | No | Google Places API key (enables restaurant search) |
| `DATABASE_URL` | No | Database URL (defaults to `sqlite:///./submissions.db`) |

## Local Setup

```sh
git clone https://github.com/Empiah/vq-everything.git
cd vq-everything
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your credentials
python app.py
```

The app will be available at http://127.0.0.1:8050

## Deployment

Hosted on [Render](https://render.com). Set the environment variables above in the Render dashboard, use `gunicorn app:app` as the start command, and attach a persistent disk for SQLite storage.

## License

MIT
