import os
from datetime import datetime, timedelta
from typing import Optional, List, Union, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

# Importations corrigées des modules locaux
from app.database import get_db
from app.models import User, UserRole

# Configuration du hachage des mots de passe
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Clé secrète JWT et paramètres
SECRET_KEY = os.getenv(
    "SECRET_KEY", 
    "SUPER_SECRET_KEY_POUR_NOTRE_MVP_PORTAIL_SCOLAIRE_2026"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 heures pour une session fluide

# Point d'entrée pour le Bearer Token dans Swagger / Clients HTTP
security_scheme = HTTPBearer()


# ==========================================
# 1. HACHAGE & JETONS JWT
# ==========================================

def hash_password(password: str) -> str:
    """Hache le mot de passe en texte brut."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie si un mot de passe correspond au hash stocké."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except UnknownHashError:
        # Fallback pour les mots de passe stockés en clair lors du développement
        return plain_password == hashed_password


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Génère un token JWT contenant l'email (sub) et le rôle."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ==========================================
# 2. DÉPENDANCES D'AUTHENTIFICATION & RBAC
# ==========================================

async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Dépendance FastAPI : extrait et valide l'utilisateur connecté via le Token JWT.
    """
    token = creds.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expirée ou invalide. Veuillez vous reconnecter.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Décoder le jeton JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Rechercher l'utilisateur dans la base de données
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
        
    return user


class RoleChecker:
    """
    Dépendance pour restreindre l'accès à certains rôles uniquement (RBAC).
    
    Exemples d'utilisation :
    - `Depends(RoleChecker([UserRole.ADMIN]))`
    - `Depends(RoleChecker(["ADMIN", "COMPTABLE"]))`
    """
    def __init__(self, allowed_roles: List[Union[UserRole, str, Any]]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        # Vérification souple (gère à la fois les chaînes "ADMIN" et les objets Enum UserRole)
        user_role_str = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
        allowed_roles_str = [r.value if hasattr(r, 'value') else str(r) for r in self.allowed_roles]

        if user_role_str not in allowed_roles_str:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas les droits nécessaires pour effectuer cette action."
            )
            
        return current_user