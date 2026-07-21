from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

# ==========================================
# 1. NOUVELLES TABLES : GESTION SCOLAIRE (Sprint 3)
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
# 2. TABLES EXISTANTES MISES À JOUR
# ==========================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False) # "ADMIN", "PARENT", "COMPTABLE"
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False) 
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    students = relationship("Student", back_populates="parent")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    matricule = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    
    # Évolution Sprint 3 : Clés étrangères vers les entités structurées (rendues optionnelles temporairement pour le seed initial)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=True)
    school_year_id = Column(Integer, ForeignKey("school_years.id"), nullable=True)
    
    # On garde ces deux champs textes pour que ton script d'injection initial (lifespan) ne plante pas !
    class_name = Column(String, nullable=True) 
    school_year = Column(String, nullable=True) 
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    parent = relationship("User", back_populates="students")
    account = relationship("StudentAccount", back_populates="student", uselist=False)
    
    class_rel = relationship("SchoolClass", back_populates="students")
    school_year_rel = relationship("SchoolYear", back_populates="students")


class StudentAccount(Base):
    __tablename__ = "student_accounts"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    total_amount = Column(Float, default=0.0)      
    paid_amount = Column(Float, default=0.0)       
    remaining_amount = Column(Float, default=0.0)  
    status = Column(String, default="NON_SOLDE")   

    # Relations
    student = relationship("Student", back_populates="account")
    payments = relationship("Payment", back_populates="account")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    student_account_id = Column(Integer, ForeignKey("student_accounts.id"), nullable=False)
    amount = Column(Float, nullable=False)
    reference = Column(String, unique=True, index=True, nullable=False) 
    operator = Column(String, nullable=False) 
    payment_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="VALIDE") 
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    account = relationship("StudentAccount", back_populates="payments")