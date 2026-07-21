from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# ==========================================
# 1. SCHÉMAS DU SPRINT 2 (Authentification & Utilisateurs)
# ==========================================

class LoginRequest(BaseModel):
    """Schéma pour la requête de connexion."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schéma pour le retour du Token JWT."""
    access_token: str
    token_type: str
    role: str
    full_name: str


class UserProfile(BaseModel):
    """Schéma simple pour l'utilisateur connecté."""
    id: int
    email: str
    first_name: str
    last_name: str
    role: str

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Schéma pour la création d'un utilisateur par l'Admin."""
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    role: str  # ex: 'ADMIN', 'PARENT', 'COMPTABLE'
    phone: Optional[str] = None


class UserResponse(BaseModel):
    """Schéma de retour d'un utilisateur créé."""
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True


# ==========================================
# 2. SCHÉMAS DU SPRINT 3 (Gestion Scolaire)
# ==========================================

# --- 2.1. ÉCOLE ---
class SchoolBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None


class SchoolCreate(SchoolBase):
    """Schéma pour la création d'une école."""
    pass


class SchoolResponse(SchoolBase):
    """Schéma de retour d'une école avec ses métadonnées."""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- 2.2. ANNÉE SCOLAIRE ---
class SchoolYearBase(BaseModel):
    label: str
    is_active: Optional[bool] = False


class SchoolYearCreate(SchoolYearBase):
    """Schéma pour la création d'une année scolaire (ex: 2025-2026)."""
    pass


class SchoolYearResponse(SchoolYearBase):
    """Schéma de retour d'une année scolaire."""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- 2.3. CLASSE ---
class SchoolClassBase(BaseModel):
    name: str
    school_id: int
    school_year_id: int


class SchoolClassCreate(SchoolClassBase):
    """Schéma pour la création d'une classe."""
    pass


class SchoolClassResponse(SchoolClassBase):
    """Schéma de retour d'une classe."""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True