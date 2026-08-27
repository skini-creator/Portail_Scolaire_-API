import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Float,
    DateTime,
    Boolean,
    Enum,
    Text,
)
from sqlalchemy.orm import relationship
from app.database import Base


# ==========================================
# 0. ÉNUMÉRATIONS (Rôles & Statuts)
# ==========================================

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    COMPTABLE = "COMPTABLE"
    PARENT = "PARENT"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"      # En attente de validation par le comptable
    APPROVED = "APPROVED"    # Validé (impacte le montant payé)
    REJECTED = "REJECTED"    # Rejeté avec motif


# ==========================================
# 1. GESTION SCOLAIRE & STRUCTURE
# ==========================================

class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)        # Ex: "Lycée National Léon Mba"
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    classes = relationship("SchoolClass", back_populates="school")


class SchoolYear(Base):
    __tablename__ = "school_years"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, unique=True, nullable=False) # Ex: "2025-2026"
    is_active = Column(Boolean, default=False)          # Pour savoir si c'est l'année en cours
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    classes = relationship("SchoolClass", back_populates="school_year")
    students = relationship("Student", back_populates="school_year_rel")


class SchoolClass(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False) # Ex: "6ème A"
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    school_year_id = Column(Integer, ForeignKey("school_years.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    school = relationship("School", back_populates="classes")
    school_year = relationship("SchoolYear", back_populates="classes")
    students = relationship("Student", back_populates="class_rel")


# ==========================================
# 2. UTILISATEURS & ÉLÈVES
# ==========================================

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    role = Column(Enum(UserRole), default=UserRole.PARENT, nullable=False) # "ADMIN", "PARENT", "COMPTABLE"
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False) 
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)  # Permet de désactiver un utilisateur
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    students = relationship("Student", back_populates="parent")
    validated_payments = relationship("Payment", back_populates="validated_by")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    matricule = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)  # Permet de désactiver un élève
    
    # Clés étrangères vers la structure
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    school_year_id = Column(Integer, ForeignKey("school_years.id"), nullable=True)
    
    # Champs de rétrocompatibilité (Injection initiale / Seeding)
    class_name = Column(String, nullable=True) 
    school_year = Column(String, nullable=True) 
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    parent = relationship("User", back_populates="students")
    account = relationship("StudentAccount", back_populates="student", uselist=False)
    
    class_rel = relationship("SchoolClass", back_populates="students")
    school_year_rel = relationship("SchoolYear", back_populates="students")

    @property
    def parent_id(self):
        return self.user_id


# ==========================================
# 3. COMPTABILITÉ & PAIEMENTS
# ==========================================

class StudentAccount(Base):
    __tablename__ = "student_accounts"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    total_amount = Column(Float, default=0.0)      
    paid_amount = Column(Float, default=0.0)       
    remaining_amount = Column(Float, default=0.0)  
    status = Column(String, default="NON_SOLDE")   # Ex: "SOLDE", "NON_SOLDE"

    # Relations
    student = relationship("Student", back_populates="account")
    payments = relationship("Payment", back_populates="account")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    student_account_id = Column(Integer, ForeignKey("student_accounts.id"), nullable=False)
    amount = Column(Float, nullable=False)
    reference = Column(String, unique=True, index=True, nullable=False) 
    operator = Column(String, nullable=False) # Ex: "AIRTEL_MONEY", "MOOV_MONEY"
    payment_date = Column(DateTime, default=datetime.utcnow)
    
    # Workflow de validation par le Comptable
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    validated_at = Column(DateTime, nullable=True)
    validated_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    account = relationship("StudentAccount", back_populates="payments")
    validated_by = relationship("User", back_populates="validated_payments")