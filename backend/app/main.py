import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# Importations des routeurs (Sprint 3)
from app.routers import school

# Importations absolues
from app.database import engine, get_db, Base
from app.models import User, Student, StudentAccount
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


def wait_for_db(engine, max_retries: int = 10, delay_seconds: int = 3):
    """Attends que PostgreSQL soit prêt avant de démarrer l'application."""
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("Connexion à PostgreSQL réussie.")
            return
        except OperationalError as exc:
            last_exception = exc
            print(
                f"PostgreSQL indisponible (tentative {attempt}/{max_retries}). "
                f"Réessayer dans {delay_seconds}s..."
            )
            time.sleep(delay_seconds)
    raise RuntimeError(
        f"Impossible de se connecter à PostgreSQL après {max_retries} tentatives."
    ) from last_exception


# --- GESTIONNAIRE DE LIFESPAN (INITIALISATION DE LA BDD AU DÉMARRAGE) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """S'exécute automatiquement au lancement de l'API pour injecter les données de démo."""

    print("Attente de la disponibilité de PostgreSQL... ⏳")
    wait_for_db(engine)

    print("Vérification et création des tables de la base de données... 🛠️")
    Base.metadata.create_all(bind=engine)

    db = next(get_db())
    try:
        # 1. Injection de l'ADMIN de démo
        test_admin = db.query(User).filter(User.email == "admin@demo.com").first()
        if not test_admin:
            print("Injection de l'administrateur de démo... 👑")
            admin = User(
                role="ADMIN",
                first_name="Algrin",
                last_name="Mondjo",
                email="admin@demo.com",
                password=hash_password("AdminPassword2026"),
                phone="+241 66 00 00 00"
            )
            db.add(admin)
            db.commit()
            print("Administrateur de démo créé ! 🎉")

        # 2. Injection du PARENT de démo
        test_parent = db.query(User).filter(User.email == "parent@demo.com").first()
        if not test_parent:
            print("Injection du parent de démo... 👨‍👩‍👦")
            parent = User(
                role="PARENT",
                first_name="Jean",
                last_name="Mondjo",
                email="parent@demo.com",
                password=hash_password("DemoPassword2026"),
                phone="+241 74 83 74 43"
            )
            db.add(parent)
            db.commit()
            db.refresh(parent)

            # Création de l'élève rattaché au parent
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

            # Compte financier de scolarité associé
            account = StudentAccount(
                student_id=student.id,
                total_amount=300000.0,
                paid_amount=0.0,
                remaining_amount=300000.0,
                status="NON_SOLDE"
            )
            db.add(account)
            db.commit()
            print("Données de démo parent/élève injectées avec succès ! 🎉")
        else:
            if pwd_context.identify(test_parent.password) is None:
                print("Mot de passe de démo stocké en clair; migration vers un hash sécurisé... 🔒")
                test_parent.password = hash_password("DemoPassword2026")
                db.add(test_parent)
                db.commit()
                print("Mot de passe de démo migré avec succès.")
            else:
                print("Données de démo déjà présentes. Initialisation ignorée. ✅")
                
    except Exception as e:
        print(f"Erreur lors de l'injection : {e}")
        raise
    finally:
        db.close()

    yield


# --- INSTANCIATION DE L'APPLICATION ---
app = FastAPI(
    title="Portail Scolaire API",
    version="1.0.0",
    lifespan=lifespan
)


# --- CONFIGURATION DU CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INCLUSION DES ROUTEURS ---
app.include_router(school.router)


# --- ROUTES ---

@app.get("/")
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

    access_token = create_access_token(
        data={"sub": user.email, "role": user.role}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "full_name": f"{user.first_name} {user.last_name}"
    }


# --- ROUTES SPRINT 2 : GESTION DES UTILISATEURS ---

@app.post(
    "/api/users/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RoleChecker(["ADMIN"]))]
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
    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "role": current_user.role,
        "phone": current_user.phone
    }


@app.get("/api/admin/dashboard", dependencies=[Depends(RoleChecker(["ADMIN"]))])
def read_admin_dashboard():
    """Panneau d'administration d'exemple pour valider le fonctionnement du RBAC."""
    return {"message": "Bienvenue sur le panneau d'administration secret ! 🔑"}