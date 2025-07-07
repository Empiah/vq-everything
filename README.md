# Value and Quality Everything – Backend

This is a Python FastAPI backend for the Value and Quality Everything website.

## Features
- Stores user submissions for a scatter plot
- Each submission: value (float, 0-100), quality (float, 0-100), type (str), category (str), name (str, max 100 chars), location (str), user_id (for future Google login)
- Uses SQLite as the database
- Endpoints:
  - `POST /submissions` – create a new submission
  - `GET /submissions` – list all submissions
- CORS enabled for frontend integration

## Setup
1. Install dependencies:
   ```sh
   pip install -r backend/requirements.txt
   ```
2. Run the server:
   ```sh
   uvicorn backend.main:app --reload
   ```
