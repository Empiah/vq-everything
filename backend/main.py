"""
FastAPI backend for Value and Quality Everything
- Stores user submissions for a scatter plot
- Each submission: value (float, 0-100), quality (float, 0-100), type (str), category (str), name (str, max 100 chars), location (str), user_id (int, for future Google login)
- Uses SQLite as the database
- Endpoints: create submission, list all submissions
- CORS enabled for frontend integration
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, constr, conint, confloat

DATABASE_URL = "sqlite:///./submissions.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# SQLAlchemy model for a submission
class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True, index=True)
    value = Column(Float, nullable=False)
    quality = Column(Float, nullable=False)
    type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    name = Column(String(100), nullable=False)
    location = Column(String, nullable=False)
    user_id = Column(Integer, nullable=True)  # For future Google login

# Pydantic schema for input validation
class SubmissionCreate(BaseModel):
    value: confloat(ge=0, le=100)
    quality: confloat(ge=0, le=100)
    type: str
    category: str
    name: constr(max_length=100)
    location: str
    user_id: int = None

class SubmissionOut(SubmissionCreate):
    id: int
    class Config:
        orm_mode = True

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Enable CORS for all origins (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/submissions", response_model=SubmissionOut)
def create_submission(sub: SubmissionCreate, db: Session = Depends(get_db)):
    """Create a new submission"""
    db_sub = Submission(**sub.dict())
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    return db_sub

@app.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(db: Session = Depends(get_db)):
    """List all submissions"""
    return db.query(Submission).all()
