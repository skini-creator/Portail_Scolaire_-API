import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Build the DB URL from environment variables to avoid hard-coded secrets.
# Priority: DATABASE_URL env var (for flexibility), otherwise construct from components.
DB_USER = os.getenv("DB_USER", "admin_scolaire")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "portail_scolaire_dev")

# If a full DATABASE_URL is supplied, use it. Otherwise require DB_PASSWORD to be set
# (to avoid embedding secrets in source code). This forces callers to provide password
# via environment or secret management.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if not DB_PASSWORD:
        raise RuntimeError(
            "DB_PASSWORD environment variable is required when DATABASE_URL is not provided."
        )
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dépendance pour injecter la session de BDD dans nos routes FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()