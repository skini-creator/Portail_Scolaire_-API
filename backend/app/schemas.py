from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ==========================================
# 0. ÉNUMÉRATIONS POUR SCHÉMAS
# ==========================================

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    COMPTABLE = "COMPTABLE"
    PARENT = "PARENT"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


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
    role: UserRole
    full_name: str


class UserProfile(BaseModel):
    """Schéma simple pour l'utilisateur connecté."""
    id: Union[int, str]
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Schéma pour la création d'un utilisateur par l'Admin (Parents, Comptables, etc.)."""
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    role: UserRole = UserRole.PARENT
    phone: Optional[str] = None

    @field_validator('role', mode='before')
    @classmethod
    def normalize_role(cls, v):
        if isinstance(v, str):
            val_upper = v.upper()
            if val_upper == 'ACCOUNTANT':
                return UserRole.COMPTABLE
            return val_upper
        return v


class UserResponse(BaseModel):
    """Schéma de retour d'un utilisateur créé."""
    id: Union[int, str]
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole
    phone: Optional[str] = None
    is_active: Optional[bool] = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- SCHÉMAS SPÉCIFIQUES PARENT ---
class ParentCreate(BaseModel):
    """Schéma de création d'un Parent par l'Admin."""
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    role: Optional[str] = "PARENT"


class ParentUpdate(BaseModel):
    """Schéma de modification d'un Parent par l'Admin."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None


class ParentResponse(BaseModel):
    """Schéma de retour d'un Parent."""
    id: Union[int, str]
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: UserRole = UserRole.PARENT
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- SCHÉMAS SPÉCIFIQUES COMPTABLE ---
class AccountantCreate(BaseModel):
    """Schéma de création d'un Comptable par l'Admin."""
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    role: Optional[str] = "COMPTABLE"


class AccountantUpdate(BaseModel):
    """Schéma de modification d'un Comptable par l'Admin."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None


class AccountantResponse(BaseModel):
    """Schéma de retour d'un Comptable."""
    id: Union[int, str]
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: UserRole = UserRole.COMPTABLE
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==========================================
# 2. SCHÉMAS DU SPRINT 3 (Gestion Scolaire & Élèves)
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


# --- 2.4. ÉLÈVE ---
class StudentCreate(BaseModel):
    """Schéma pour l'inscription d'un élève par l'Admin."""
    first_name: str
    last_name: str
    parent_id: Union[int, str]
    class_id: Optional[int] = None
    school_year_id: Optional[int] = None


class StudentUpdate(BaseModel):
    """Schéma de modification d'un élève."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    class_id: Optional[int] = None


class StudentResponse(BaseModel):
    """Schéma de retour d'un élève inscrit."""
    id: int
    first_name: str
    last_name: str
    matricule: str
    user_id: Union[int, str]
    parent_id: Optional[Union[int, str]] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    is_active: Optional[bool] = True

    class Config:
        from_attributes = True


# ==========================================
# 3. PAIEMENTS & FINANCES (Mise à jour Workflow)
# ==========================================

class PaymentCreate(BaseModel):
    """Schéma pour déclarer un paiement (créé avec le statut PENDING par défaut)."""
    student_id: int
    amount: float
    reference: Optional[str] = None  # Référence Mobile Money (ex: R123456)
    operator: Optional[str] = "AIRTEL_MONEY"


class PaymentRejectRequest(BaseModel):
    """Schéma envoyé par le comptable pour justifier un rejet de paiement."""
    reason: Optional[str] = "Référence introuvable"


class PaymentResponse(BaseModel):
    """Schéma de retour complet pour les paiements (aligné sur Payment dans models.py)."""
    id: int
    student_account_id: int
    amount: float
    reference: str
    operator: str
    status: PaymentStatus
    payment_date: datetime
    created_at: datetime

    # Champs de validation par le Comptable
    validated_at: Optional[datetime] = None
    validated_by_id: Optional[int] = None
    rejection_reason: Optional[str] = None

    # Métadonnées jointes pour le Dashboard Admin / Comptable / Parent
    student_name: Optional[str] = None
    class_name: Optional[str] = None

    class Config:
        from_attributes = True


class StudentAccountResponse(BaseModel):
    """Schéma pour afficher l'état financier du compte d'un élève."""
    id: int
    student_id: int
    total_amount: float
    paid_amount: float
    remaining_amount: float
    status: str  # 'NON_SOLDE', 'PARTIEL', 'SOLDE'

    class Config:
        from_attributes = True