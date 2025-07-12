# Standalone script to update all submissions for a given email to use the Google name instead
# Usage: python update_user_ids.py <old_email> <new_name>

import sys
import os
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./submissions.db")
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
    user_id = sa.Column(sa.String, nullable=True)

def update_user_ids(old_email, new_name):
    with SessionLocal() as db:
        subs = db.query(Submission).filter(Submission.user_id == old_email).all()
        print(f"Found {len(subs)} submissions for {old_email}.")
        for s in subs:
            s.user_id = new_name
        db.commit()
        print(f"Updated all submissions to user_id = {new_name}.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python update_user_ids.py <old_email> <new_name>")
        sys.exit(1)
    old_email = sys.argv[1]
    new_name = sys.argv[2]
    update_user_ids(old_email, new_name)
