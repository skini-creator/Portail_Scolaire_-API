import sys
import os

# Configuration de sys.path pour l'exécution Serverless Vercel
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))   # .../backend/app
BACKEND_DIR = os.path.dirname(CURRENT_DIR)                 # .../backend
ROOT_DIR = os.path.dirname(BACKEND_DIR)                   # ... (racine du projet)

for path in [BACKEND_DIR, ROOT_DIR, CURRENT_DIR]:
    if path and path not in sys.path:
        sys.path.insert(0, path)


import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

# Importations des routeurs (Sprint 3)
from app.routers import school, students, payments, users, admin

# Importations absolues
from app.database import engine, get_db, Base
from app.models import User, Student, StudentAccount, UserRole
from app.schemas import LoginRequest, Token, UserCreate, UserResponse

# Security & RBAC (Sprint 2)
from app.security import (
    verify_password, 
    create_access_token, 
    hash_password, 
    pwd_context,
    get_current_user,
    RoleChecker
)


def wait_for_db(engine, max_retries: int = 2, delay_seconds: int = 1):
    """Attends que la base de données soit prête avant de démarrer l'application."""
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("Connexion à la base de données réussie.")
            return
        except Exception as exc:
            last_exception = exc
            print(
                f"Base de données indisponible (tentative {attempt}/{max_retries}). "
                f"Réessayer dans {delay_seconds}s..."
            )
            time.sleep(delay_seconds)
    print(f"Avertissement DB : {last_exception}")


# --- GESTIONNAIRE DE LIFESPAN (INITIALISATION DE LA BDD AU DÉMARRAGE) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """S'exécute automatiquement au lancement de l'API pour injecter les données de démo."""
    try:
        print("Vérification rapide de la base de données... 🛠️")
        wait_for_db(engine)
        Base.metadata.create_all(bind=engine)

        db = next(get_db())
        try:
            # 1. Injection de l'ADMIN de démo
            test_admin = db.query(User).filter(User.email == "admin@demo.com").first()
            if not test_admin:
                print("Injection de l'administrateur de démo... 👑")
                admin = User(
                    id="1",
                    role=UserRole.ADMIN,
                    first_name="Algrin",
                    last_name="Mondjo",
                    email="admin@demo.com",
                    password=hash_password("AdminPassword2026"),
                    phone="+241 66 00 00 00"
                )
                db.add(admin)
                db.commit()

            # 2. Injection du PARENT de démo
            test_parent = db.query(User).filter(User.email == "parent@demo.com").first()
            if not test_parent:
                print("Injection du parent de démo... 👨‍👩‍👦")
                parent = User(
                    id="2",
                    role=UserRole.PARENT,
                    first_name="Jean",
                    last_name="Mondjo",
                    email="parent@demo.com",
                    password=hash_password("DemoPassword2026"),
                    phone="+241 74 83 74 43"
                )
                db.add(parent)
                db.commit()
                db.refresh(parent)

                student = Student(
                    user_id=parent.id,
                    matricule="MAT-98765",
                    first_name="Ariel",
                    last_name="Mondjo",
                    class_name="6ème A",
                    school_year="2025-2026"
                )
                db.add(student)
                db.commit()
                db.refresh(student)

                account = StudentAccount(
                    student_id=student.id,
                    total_amount=300000.0,
                    paid_amount=0.0,
                    remaining_amount=300000.0,
                    status="NON_SOLDE"
                )
                db.add(account)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"Erreur durant l'initialisation lifespan: {e}")

    yield


# --- INSTANCIATION DE L'APPLICATION ---
app = FastAPI(
    title="Portail Scolaire API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request, exc: SQLAlchemyError):
    print(f"[DatabaseError] Erreur BDD sur {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Service de base de données temporairement indisponible. Veuillez vérifier la connexion ou la variable DATABASE_URL.",
            "error": str(exc)
        }
    )


# --- CONFIGURATION DU CORS ---
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
if allowed_origins_env:
    allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
else:
    allowed_origins = ["*"]  # Permet la connexion depuis React Native / Mobile sans blocage CORS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INCLUSION DES ROUTEURS ---
app.include_router(admin.router)
app.include_router(school.router)
app.include_router(students.router)
app.include_router(payments.router)
app.include_router(users.router)


# --- ROUTES ---

@app.get("/")
@app.get("/api")
def read_root():
    return {"message": "Bienvenue sur l'API du Portail Scolaire !"}


@app.post("/api/auth/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authentifie l'utilisateur et retourne un Token JWT."""
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Conversion explicite du rôle Enum en chaîne pour le token JWT
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)

    access_token = create_access_token(
        data={"sub": user.email, "role": role_str}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role_str,
        "full_name": f"{user.first_name} {user.last_name}"
    }


# --- ROUTES SPRINT 2 : GESTION DES UTILISATEURS ---

@app.post(
    "/api/users/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RoleChecker([UserRole.ADMIN]))]
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """Permet à l'ADMIN de créer un nouvel utilisateur (Parent, Comptable, Admin)."""
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà."
        )

    new_user = User(
        role=payload.role,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        password=hash_password(payload.password),
        phone=payload.phone
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@app.get("/api/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    """Retourne les informations de l'utilisateur actuellement connecté."""
    role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "role": role_str,
        "phone": current_user.phone
    }


@app.get("/api/admin/dashboard", dependencies=[Depends(RoleChecker([UserRole.ADMIN]))])
def read_admin_dashboard():
    """Panneau d'administration d'exemple pour valider le fonctionnement du RBAC."""
    return {"message": "Bienvenue sur le panneau d'administration secret ! 🔑"}