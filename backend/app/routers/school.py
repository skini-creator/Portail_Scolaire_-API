from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import School, SchoolYear, SchoolClass
from app.schemas import (
    SchoolCreate, SchoolResponse,
    SchoolYearCreate, SchoolYearResponse,
    SchoolClassCreate, SchoolClassResponse
)
from app.security import get_current_user, RoleChecker

# Création du routeur avec un préfixe et des tags pour Swagger
router = APIRouter(
    prefix="/api/school",
    tags=["Gestion Scolaire (Sprint 3)"]
)

# ==========================================
# 1. ENDPOINTS : ÉCOLES (SCHOOLS)
# ==========================================

@router.post("/", response_model=SchoolResponse, status_code=status.HTTP_201_CREATED)
def create_school(
    payload: SchoolCreate, 
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker(["ADMIN"])) # Seul l'ADMIN crée l'école
):
    """Enregistre un nouvel établissement scolaire (ADMIN uniquement)."""
    school = School(name=payload.name, address=payload.address, phone=payload.phone)
    db.add(school)
    db.commit()
    db.refresh(school)
    return school


@router.get("/", response_model=List[SchoolResponse])
def list_schools(
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user) # Tout utilisateur connecté peut lire
):
    """Liste tous les établissements scolaires enregistrés."""
    return db.query(School).all()


# ==========================================
# 2. ENDPOINTS : ANNÉES SCOLAIRES (SCHOOL YEARS)
# ==========================================

@router.post("/years", response_model=SchoolYearResponse, status_code=status.HTTP_201_CREATED)
def create_school_year(
    payload: SchoolYearCreate, 
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker(["ADMIN"]))
):
    """Crée une nouvelle année scolaire (ex: 2025-2026) (ADMIN uniquement)."""
    # Si la nouvelle année est définie comme active, on désactive d'abord les autres
    if payload.is_active:
        db.query(SchoolYear).update({"is_active": False}, synchronize_session=False)
        
    school_year = SchoolYear(label=payload.label, is_active=payload.is_active)
    db.add(school_year)
    db.commit()
    db.refresh(school_year)
    return school_year


@router.get("/years", response_model=List[SchoolYearResponse])
def list_school_years(
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user)
):
    """Liste toutes les années scolaires enregistrées."""
    return db.query(SchoolYear).all()


# ==========================================
# 3. ENDPOINTS : CLASSES
# ==========================================

@router.post("/classes", response_model=SchoolClassResponse, status_code=status.HTTP_201_CREATED)
def create_class(
    payload: SchoolClassCreate, 
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker(["ADMIN"]))
):
    """Crée une classe associée à une école et une année scolaire spécifiques (ADMIN uniquement)."""
    # Vérifications des clés étrangères existantes
    school = db.query(School).filter(School.id == payload.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="Établissement scolaire introuvable")
        
    year = db.query(SchoolYear).filter(SchoolYear.id == payload.school_year_id).first()
    if not year:
        raise HTTPException(status_code=404, detail="Année scolaire introuvable")

    school_class = SchoolClass(
        name=payload.name,
        school_id=payload.school_id,
        school_year_id=payload.school_year_id
    )
    db.add(school_class)
    db.commit()
    db.refresh(school_class)
    return school_class


@router.get("/classes", response_model=List[SchoolClassResponse])
def list_classes(
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user)
):
    """Liste toutes les classes enregistrées."""
    return db.query(SchoolClass).all()