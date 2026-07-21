import os
from datetime import datetime, timedelta
from typing import Optional  # Ajout de list pour typer RoleChecker
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

# Importations de tes modules locaux
from app.database import get_db
from app.models import User

# Configuration du hachage des mots de passe (On garde ta config PBKDF2)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Récupération de la clé secrète (On garde ta clé MVP 2026 !)
SECRET_KEY = os.getenv(
    "SECRET_KEY", 
    "SUPER_SECRET_KEY_POUR_NOTRE_MVP_PORTAIL_SCOLAIRE_2026"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Point d'entrée pour récupérer le token dans l'en-tête (Authorization: Bearer <token>)
security_scheme = HTTPBearer()


# --- TES FONCTIONS DE SÉCURITÉ PRÉSERVÉES ---

def hash_password(password: str) -> str:
    """Hache le mot de passe en texte brut."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si un mot de passe correspond au hash stocké."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except UnknownHashError:
        # Fallback pour les mots de passe stockés en clair ou migrés sans hash
        return plain_password == hashed_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Génère un token JWT sécurisé contenant le rôle et l'email."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- SYSTÈME RBAC AJOUTÉ ---

async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security_scheme), db: Session = Depends(get_db)) -> User:
    token = creds.credentials  # On extrait directement la chaîne du token JWT

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expirée ou invalide. Veuillez vous reconnecter.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # ... (le reste du code de ta fonction get_current_user ne bouge pas !)
    """
    Dépendance pour extraire et valider l'utilisateur connecté depuis le token JWT.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expirée ou invalide. Veuillez vous reconnecter.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Décoder le jeton JWT avec ta clé secrète MVP
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Rechercher l'utilisateur correspondant dans PostgreSQL
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


class RoleChecker:
    """
    Dépendance pour restreindre l'accès à certains rôles uniquement.
    Exemple d'utilisation : Depends(RoleChecker(["ADMIN"]))
    """
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)):
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas les droits nécessaires pour accéder à cette ressource."
            )
        return current_user