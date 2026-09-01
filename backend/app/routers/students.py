import uuid
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models import Student, StudentAccount, User, SchoolClass, UserRole
from app.schemas import StudentCreate, StudentResponse, StudentUpdate
from app.security import get_current_user, RoleChecker

# Schémas supplémentaires pour les opérations
class TuitionUpdate(BaseModel):
    """Schéma pour définir/modifier la scolarité d'un élève."""
    total_amount: float


def resolve_class_info(db: Session, class_id=None, class_name=None, classe=None, classroom=None):
    c_name_input = class_name or classe or classroom
    
    if class_id is not None:
        if isinstance(class_id, int) or (isinstance(class_id, str) and class_id.isdigit()):
            cid = int(class_id)
            school_cls = db.query(SchoolClass).filter(SchoolClass.id == cid).first()
            if school_cls:
                return school_cls.id, school_cls.name
        elif isinstance(class_id, str) and class_id.strip() and not c_name_input:
            c_name_input = class_id.strip()

    if c_name_input and str(c_name_input).strip():
        clean_name = str(c_name_input).strip()
        school_cls = db.query(SchoolClass).filter(func.lower(SchoolClass.name) == clean_name.lower()).first()
        if school_cls:
            return school_cls.id, school_cls.name
        return None, clean_name

    return None, None


router = APIRouter(
    prefix="/api/students",
    tags=["Gestion des Élèves (Sprint 3)"]
)


@router.post("/", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Inscrit un nouvel élève, l'associe à son parent et sa classe,
    puis initialise automatiquement son compte financier.
    Réservé aux administrateurs.
    """
    # 1. Vérification de l'existence du parent (Rôle PARENT requis)
    parent = db.query(User).filter(User.id == str(payload.parent_id), User.role == UserRole.PARENT).first()
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Parent introuvable ou l'utilisateur spécifié n'a pas le rôle PARENT"
        )

    # 2. Résolution résiliente de la classe
    target_class_id, target_class_name = resolve_class_info(
        db,
        class_id=payload.class_id,
        class_name=payload.class_name,
        classe=payload.classe,
        classroom=payload.classroom
    )

    # 3. Génération automatique du matricule unique
    matricule = f"MAT-2026-{uuid.uuid4().hex[:4].upper()}"

    # 4. Création de l'élève
    student = Student(
        first_name=payload.first_name,
        last_name=payload.last_name,
        matricule=matricule,
        user_id=str(payload.parent_id),
        class_id=target_class_id,
        class_name=target_class_name,
        is_active=True
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    # 5. Création automatique du compte financier associé
    account = StudentAccount(
        student_id=student.id,
        total_amount=300000.0,
        paid_amount=0.0,
        remaining_amount=300000.0,
        status="NON_SOLDE"
    )
    db.add(account)
    db.commit()

    return student


@router.get("/my-children", response_model=List[StudentResponse])
def get_my_children(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permet à un parent connecté de récupérer la liste de tous ses enfants rattachés avec le nom de leur classe.
    """
    if current_user.role != UserRole.PARENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux utilisateurs ayant le rôle PARENT."
        )

    # Jointure avec la table des classes
    results = (
        db.query(Student, SchoolClass.name.label("class_name_joined"))
        .outerjoin(SchoolClass, Student.class_id == SchoolClass.id)
        .filter(Student.user_id == str(current_user.id))
        .all()
    )

    children = []
    for student, class_name in results:
        # S'assure que le champ class_name est bien rempli pour Pydantic
        student.class_name = class_name or student.class_name
        children.append(student)

    return children


@router.get("/", response_model=List[StudentResponse])
def list_students(
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Liste tous les élèves enregistrés.
    Réservé aux administrateurs.
    """
    results = (
        db.query(Student, SchoolClass.name.label("class_name_joined"))
        .outerjoin(SchoolClass, Student.class_id == SchoolClass.id)
        .all()
    )

    students = []
    for student, class_name in results:
        student.class_name = class_name or student.class_name
        students.append(student)

    return students


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN, UserRole.PARENT]))
):
    """
    Récupère les détails d'un élève spécifique.
    Les parents ne peuvent voir que leurs propres enfants.
    """
    student = (
        db.query(Student, SchoolClass.name.label("class_name_joined"))
        .outerjoin(SchoolClass, Student.class_id == SchoolClass.id)
        .filter(Student.id == student_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    student_obj, class_name = student
    
    # Vérification d'accès pour les parents
    if _current_user.role == UserRole.PARENT and str(student_obj.user_id) != str(_current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas accès aux informations de cet élève."
        )

    student_obj.class_name = class_name or student_obj.class_name
    return student_obj


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Modifie les informations d'un élève.
    Réservé aux administrateurs.
    """
    student = db.query(Student).filter(Student.id == student_id).first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    # Resolution resiliente de la classe si fournie
    if payload.class_id is not None or payload.class_name or payload.classe or payload.classroom:
        target_class_id, target_class_name = resolve_class_info(
            db,
            class_id=payload.class_id,
            class_name=payload.class_name,
            classe=payload.classe,
            classroom=payload.classroom
        )
        if target_class_id is not None or target_class_name is not None:
            student.class_id = target_class_id
            student.class_name = target_class_name

    # Mise à jour des champs
    if payload.first_name:
        student.first_name = payload.first_name
    if payload.last_name:
        student.last_name = payload.last_name

    db.commit()
    db.refresh(student)

    return student


@router.patch("/{student_id}/status", response_model=StudentResponse)
def toggle_student_status(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Désactive/Réactive un élève en basculant le statut is_active.
    Réservé aux administrateurs.
    """
    student = db.query(Student).filter(Student.id == student_id).first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    # Basculement du statut
    student.is_active = not student.is_active
    db.commit()
    db.refresh(student)

    return student


# ==========================================
# GESTION DE LA SCOLARITÉ (TUITION)
# ==========================================

@router.get("/{student_id}/tuition")
def get_student_tuition(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user)
):
    """
    Récupère les informations financières (scolarité, montant payé, solde) d'un élève.
    Les parents ne voient que leurs enfants.
    """
    student = db.query(Student).filter(Student.id == student_id).first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    # Vérification d'accès pour les parents
    if _current_user.role == UserRole.PARENT and student.user_id != _current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas accès à ces informations."
        )

    account = db.query(StudentAccount).filter(StudentAccount.student_id == student_id).first()

    if not account:
        return {
            "student_id": student_id,
            "total_amount": None,
            "paid_amount": None,
            "remaining_amount": None,
            "status": "NO_TUITION"
        }

    return {
        "student_id": student_id,
        "total_amount": account.total_amount,
        "paid_amount": account.paid_amount,
        "remaining_amount": account.remaining_amount,
        "status": account.status
    }


@router.post("/{student_id}/tuition")
def set_student_tuition(
    student_id: int,
    payload: TuitionUpdate,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Définit la scolarité (montant total) d'un élève.
    Réservé aux administrateurs.
    """
    student = db.query(Student).filter(Student.id == student_id).first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    account = db.query(StudentAccount).filter(StudentAccount.student_id == student_id).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte financier de l'élève introuvable."
        )

    if payload.total_amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le montant de la scolarité ne peut pas être négatif."
        )

    # Mise à jour du montant total
    account.total_amount = payload.total_amount
    # Recalcul du solde
    account.remaining_amount = account.total_amount - account.paid_amount
    if account.remaining_amount < 0:
        account.remaining_amount = 0.0

    # Mise à jour du statut
    if account.total_amount == 0:
        account.status = "NON_SOLDE"
    elif account.paid_amount >= account.total_amount:
        account.status = "SOLDE"
    elif account.paid_amount > 0:
        account.status = "PARTIEL"
    else:
        account.status = "NON_SOLDE"

    db.commit()
    db.refresh(account)

    return {
        "student_id": student_id,
        "total_amount": account.total_amount,
        "paid_amount": account.paid_amount,
        "remaining_amount": account.remaining_amount,
        "status": account.status
    }


@router.put("/{student_id}/tuition")
def update_student_tuition(
    student_id: int,
    payload: TuitionUpdate,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Modifie la scolarité (montant total) d'un élève.
    Réservé aux administrateurs.
    """
    student = db.query(Student).filter(Student.id == student_id).first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    account = db.query(StudentAccount).filter(StudentAccount.student_id == student_id).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte financier de l'élève introuvable."
        )

    if payload.total_amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le montant de la scolarité ne peut pas être négatif."
        )

    # Mise à jour du montant total
    old_total = account.total_amount
    account.total_amount = payload.total_amount
    # Recalcul du solde
    account.remaining_amount = account.total_amount - account.paid_amount
    if account.remaining_amount < 0:
        account.remaining_amount = 0.0

    # Mise à jour du statut
    if account.total_amount == 0:
        account.status = "NON_SOLDE"
    elif account.paid_amount >= account.total_amount:
        account.status = "SOLDE"
    elif account.paid_amount > 0:
        account.status = "PARTIEL"
    else:
        account.status = "NON_SOLDE"

    db.commit()
    db.refresh(account)

    return {
        "student_id": student_id,
        "total_amount": account.total_amount,
        "paid_amount": account.paid_amount,
        "remaining_amount": account.remaining_amount,
        "status": account.status
    }