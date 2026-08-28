import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

# Build the DB URL from environment variables to avoid hard-coded secrets.
import tempfile

DB_USER = os.getenv("DB_USER", "admin_scolaire")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "portail_scolaire_dev")
# Par défaut pour les BDD cloud (Supabase/Neon/Render), sslmode='require' est nécessaire
DB_SSLMODE = os.getenv("DB_SSLMODE", "require")

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Compatibilité SQLAlchemy 2.0 (convertit postgres:// en postgresql://)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
elif DB_PASSWORD and DB_HOST and DB_HOST != "db":
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # Fallback SQLite dans le dossier temporaire /tmp (seul dossier inscriptible sur Vercel serverless)
    tmp_db = os.path.join(tempfile.gettempdir(), "app_dev.db")
    DATABASE_URL = f"sqlite:///{tmp_db}"

connect_args = {}
if DATABASE_URL.startswith("postgresql"):
    if "sslmode" not in DATABASE_URL and DB_SSLMODE:
        connect_args["sslmode"] = DB_SSLMODE
elif DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine_kwargs = {"connect_args": connect_args}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs["poolclass"] = NullPool

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dépendance pour injecter la session de BDD dans nos routes FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()