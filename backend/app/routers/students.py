import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Student, StudentAccount, User, SchoolClass
from app.schemas import StudentCreate, StudentResponse
from app.security import get_current_user, RoleChecker

router = APIRouter(
    prefix="/api/students",
    tags=["Gestion des Élèves (Sprint 3)"]
)

@router.post("/", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker(["ADMIN", "COMPTABLE"]))
):
    """
    Inscrit un nouvel élève, l'associe à son parent et sa classe,
    puis initialise automatiquement son compte financier.
    """
    # 1. Vérification de l'existence du parent (Rôle PARENT requis)
    parent = db.query(User).filter(User.id == payload.parent_id, User.role == "PARENT").first()
    if not parent:
        raise HTTPException(
            status_code=404, 
            detail="Parent introuvable ou l'utilisateur spécifié n'a pas le rôle PARENT"
        )

    # 2. Vérification de la classe
    classroom = db.query(SchoolClass).filter(SchoolClass.id == payload.class_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classe introuvable")

    # 3. Génération automatique du matricule unique
    matricule = f"MAT-2026-{uuid.uuid4().hex[:4].upper()}"

    # 4. Création de l'élève
    student = Student(
        first_name=payload.first_name,
        last_name=payload.last_name,
        matricule=matricule,
        user_id=payload.parent_id,
        class_id=payload.class_id
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    # 5. Création automatique du compte financier associé
    account = StudentAccount(
        student_id=student.id,
        total_amount=0.0,
        paid_amount=0.0,
        remaining_amount=0.0,
        status="NON_SOLDE"
    )
    db.add(account)
    db.commit()

    return student


@router.get("/", response_model=List[StudentResponse])
def list_students(
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user)
):
    """Liste tous les élèves enregistrés."""
    return db.query(Student).all()