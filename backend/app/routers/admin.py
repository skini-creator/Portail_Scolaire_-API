import uuid
import logging
from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole, Student, StudentAccount, SchoolClass, Payment
from app.schemas import (
    UserCreate,
    UserResponse,
    ParentCreate,
    ParentUpdate,
    ParentResponse,
    AccountantCreate,
    AccountantUpdate,
    AccountantResponse,
    StudentCreate,
    StudentUpdate,
    StudentResponse,
)
from app.security import RoleChecker, hash_password
from app.supabase_client import create_supabase_auth_user, delete_supabase_auth_user, SupabaseAdminError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["Administration & Supabase Auth Sync"]
)


# ==========================================
# 1. GESTION DES PARENTS (Admin)
# ==========================================

@router.post("/parents", response_model=ParentResponse, status_code=status.HTTP_201_CREATED)
def create_parent_admin(
    payload: ParentCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Crée un nouveau parent :
    1. Orchestration dans Supabase Auth (Admin SDK avec SERVICE_ROLE_KEY).
    2. Persistance dans PostgreSQL en une transaction logique (avec rollback Supabase Auth si échec DB).
    """
    # 1. Vérification que l'email n'existe pas déjà en DB
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà."
        )

    # 2. Création dans Supabase Auth
    user_metadata = {
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "phone": payload.phone,
        "role": "PARENT",
    }

    try:
        supabase_user_id = create_supabase_auth_user(
            email=payload.email,
            password=payload.password,
            user_metadata=user_metadata,
        )
    except SupabaseAdminError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err)
        )

    # 3. Insertion dans PostgreSQL
    try:
        new_user = User(
            id=supabase_user_id,
            role=UserRole.PARENT,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            password=hash_password(payload.password),
            phone=payload.phone,
            is_active=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as e:
        db.rollback()
        logger.error(f"[AdminRouter] Échec de l'insertion DB parent, déclenchement du rollback Supabase Auth: {e}")
        delete_supabase_auth_user(supabase_user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la sauvegarde du parent en base de données."
        )


@router.get("/parents", response_model=List[ParentResponse])
def list_parents_admin(
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN, UserRole.COMPTABLE]))
):
    """
    Récupère la liste de tous les parents.
    """
    parents = db.query(User).filter(User.role == UserRole.PARENT).all()
    return parents


@router.get("/parents/{parent_id}", response_model=ParentResponse)
def get_parent_admin(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN, UserRole.COMPTABLE]))
):
    """
    Récupère les détails d'un parent spécifique.
    """
    parent = db.query(User).filter(
        User.id == str(parent_id),
        User.role == UserRole.PARENT
    ).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent introuvable."
        )

    return parent


@router.put("/parents/{parent_id}", response_model=ParentResponse)
def update_parent_admin(
    parent_id: str,
    payload: ParentUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Modifie les informations d'un parent.
    """
    parent = db.query(User).filter(
        User.id == str(parent_id),
        User.role == UserRole.PARENT
    ).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent introuvable."
        )

    if payload.email and payload.email != parent.email:
        existing_user = db.query(User).filter(User.email == payload.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un utilisateur avec cet email existe déjà."
            )
        parent.email = payload.email

    if payload.first_name is not None:
        parent.first_name = payload.first_name
    if payload.last_name is not None:
        parent.last_name = payload.last_name
    if payload.phone is not None:
        parent.phone = payload.phone
    if payload.password:
        parent.password = hash_password(payload.password)

    db.commit()
    db.refresh(parent)
    return parent


@router.patch("/parents/{parent_id}/status", response_model=ParentResponse)
def toggle_parent_status_admin(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Active / Désactive le compte d'un parent.
    """
    parent = db.query(User).filter(
        User.id == str(parent_id),
        User.role == UserRole.PARENT
    ).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent introuvable."
        )

    parent.is_active = not parent.is_active
    db.commit()
    db.refresh(parent)
    return parent


@router.delete("/parents/{parent_id}")
def delete_parent_admin(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Supprime un parent et tous ses enfants associés.
    """
    parent = db.query(User).filter(
        User.id == str(parent_id),
        User.role == UserRole.PARENT
    ).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent introuvable."
        )

    try:
        children = db.query(Student).filter(Student.user_id == str(parent_id)).all()
        for child in children:
            account = db.query(StudentAccount).filter(StudentAccount.student_id == child.id).first()
            if account:
                db.query(Payment).filter(Payment.student_account_id == account.id).delete()
                db.delete(account)
            db.delete(child)

        db.delete(parent)
        db.commit()
        try:
            delete_supabase_auth_user(str(parent_id))
        except Exception:
            pass
        return {"message": "Parent et ses enfants supprimés avec succès."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression du parent : {str(e)}"
        )


@router.get("/parents/{parent_id}/children-count")
def get_parent_children_count_admin(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN, UserRole.COMPTABLE]))
):
    """
    Récupère le nombre d'enfants rattachés à un parent.
    """
    parent = db.query(User).filter(
        User.id == str(parent_id),
        User.role == UserRole.PARENT
    ).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent introuvable."
        )

    children_count = db.query(Student).filter(Student.user_id == str(parent_id)).count()
    return {"parent_id": parent_id, "children_count": children_count}


# ==========================================
# 2. GESTION DES COMPTABLES (Admin)
# ==========================================

@router.post("/accountants", response_model=AccountantResponse, status_code=status.HTTP_201_CREATED)
def create_accountant_admin(
    payload: AccountantCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Crée un nouveau comptable :
    1. Supabase Auth avec SERVICE_ROLE_KEY.
    2. Enregistrement PostgreSQL avec gestion d'erreur/rollback.
    """
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà."
        )

    user_metadata = {
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "phone": payload.phone,
        "role": "COMPTABLE",
    }

    try:
        supabase_user_id = create_supabase_auth_user(
            email=payload.email,
            password=payload.password,
            user_metadata=user_metadata,
        )
    except SupabaseAdminError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err)
        )

    try:
        new_user = User(
            id=supabase_user_id,
            role=UserRole.COMPTABLE,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            password=hash_password(payload.password),
            phone=payload.phone,
            is_active=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as e:
        db.rollback()
        logger.error(f"[AdminRouter] Échec de l'insertion DB comptable, rollback Supabase Auth: {e}")
        delete_supabase_auth_user(supabase_user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la sauvegarde du comptable en base de données."
        )


@router.get("/accountants", response_model=List[AccountantResponse])
def list_accountants_admin(
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Récupère la liste de tous les comptables.
    """
    accountants = db.query(User).filter(User.role == UserRole.COMPTABLE).all()
    return accountants


@router.get("/accountants/{accountant_id}", response_model=AccountantResponse)
def get_accountant_admin(
    accountant_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Récupère les détails d'un comptable spécifique.
    """
    accountant = db.query(User).filter(
        User.id == str(accountant_id),
        User.role == UserRole.COMPTABLE
    ).first()

    if not accountant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comptable introuvable."
        )

    return accountant


@router.put("/accountants/{accountant_id}", response_model=AccountantResponse)
def update_accountant_admin(
    accountant_id: str,
    payload: AccountantUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Modifie les informations d'un comptable.
    """
    accountant = db.query(User).filter(
        User.id == str(accountant_id),
        User.role == UserRole.COMPTABLE
    ).first()

    if not accountant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comptable introuvable."
        )

    if payload.email and payload.email != accountant.email:
        existing_user = db.query(User).filter(User.email == payload.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un utilisateur avec cet email existe déjà."
            )
        accountant.email = payload.email

    if payload.first_name is not None:
        accountant.first_name = payload.first_name
    if payload.last_name is not None:
        accountant.last_name = payload.last_name
    if payload.phone is not None:
        accountant.phone = payload.phone
    if payload.password:
        accountant.password = hash_password(payload.password)

    db.commit()
    db.refresh(accountant)
    return accountant


@router.patch("/accountants/{accountant_id}/status", response_model=AccountantResponse)
def toggle_accountant_status_admin(
    accountant_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Active / Désactive le compte d'un comptable.
    """
    accountant = db.query(User).filter(
        User.id == str(accountant_id),
        User.role == UserRole.COMPTABLE
    ).first()

    if not accountant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comptable introuvable."
        )

    accountant.is_active = not accountant.is_active
    db.commit()
    db.refresh(accountant)
    return accountant


@router.delete("/accountants/{accountant_id}")
def delete_accountant_admin(
    accountant_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Supprime un comptable.
    """
    accountant = db.query(User).filter(
        User.id == str(accountant_id),
        User.role == UserRole.COMPTABLE
    ).first()

    if not accountant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comptable introuvable."
        )

    try:
        db.delete(accountant)
        db.commit()
        try:
            delete_supabase_auth_user(str(accountant_id))
        except Exception:
            pass
        return {"message": "Comptable supprimé avec succès."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression du comptable : {str(e)}"
        )


# ==========================================
# 3. GESTION DES ÉLÈVES (Admin)
# ==========================================

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
        from sqlalchemy import func
        school_cls = db.query(SchoolClass).filter(func.lower(SchoolClass.name) == clean_name.lower()).first()
        if school_cls:
            return school_cls.id, school_cls.name
        return None, clean_name

    return None, None


@router.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student_admin(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Inscrit un nouvel élève, le rattache au parent et initialise son compte scolarité.
    """
    # 1. Vérification du parent
    parent = db.query(User).filter(
        User.id == str(payload.parent_id),
        User.role == UserRole.PARENT
    ).first()

    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent introuvable ou n'a pas le rôle PARENT."
        )

    # 2. Résolution résiliente de la classe
    target_class_id, target_class_name = resolve_class_info(
        db,
        class_id=payload.class_id,
        class_name=payload.class_name,
        classe=payload.classe,
        classroom=payload.classroom
    )

    # 3. Génération du matricule
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

    # 5. Création automatique du compte scolarité associé
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


@router.get("/students", response_model=List[StudentResponse])
def list_students_admin(
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN, UserRole.COMPTABLE]))
):
    """
    Récupère la liste de tous les élèves enregistrés.
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


@router.get("/students/{student_id}", response_model=StudentResponse)
def get_student_admin(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN, UserRole.COMPTABLE]))
):
    """
    Récupère les détails d'un élève.
    """
    result = (
        db.query(Student, SchoolClass.name.label("class_name_joined"))
        .outerjoin(SchoolClass, Student.class_id == SchoolClass.id)
        .filter(Student.id == student_id)
        .first()
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    student, class_name = result
    student.class_name = class_name or student.class_name
    return student


@router.put("/students/{student_id}", response_model=StudentResponse)
def update_student_admin(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Modifie les informations d'un élève.
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

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

    if payload.first_name:
        student.first_name = payload.first_name
    if payload.last_name:
        student.last_name = payload.last_name

    db.commit()
    db.refresh(student)
    return student


@router.patch("/students/{student_id}/status", response_model=StudentResponse)
def toggle_student_status_admin(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Bascule le statut d'un élève (Actif / Inactif).
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    student.is_active = not student.is_active
    db.commit()
    db.refresh(student)
    return student


@router.delete("/students/{student_id}")
def delete_student_admin(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Supprime un élève.
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    try:
        account = db.query(StudentAccount).filter(StudentAccount.student_id == student.id).first()
        if account:
            db.query(Payment).filter(Payment.student_account_id == account.id).delete()
            db.delete(account)

        db.delete(student)
        db.commit()
        return {"message": "Élève supprimé avec succès."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression de l'élève : {str(e)}"
        )
