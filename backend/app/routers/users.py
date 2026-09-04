import logging
from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole, Student, StudentAccount, Payment
from app.schemas import UserCreate, UserResponse
from app.security import get_current_user, RoleChecker, hash_password
from app.supabase_client import create_supabase_auth_user, delete_supabase_auth_user, SupabaseAdminError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/users",
    tags=["Gestion des Utilisateurs (Admin)"]
)


# ==========================================
# 1. GESTION DES COMPTABLES
# ==========================================

@router.post("/accountants", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_accountant(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Crée un nouveau comptable (Supabase Auth + DB).
    Réservé aux administrateurs.
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
        logger.error(f"[UsersRouter] Échec insertion comptable, rollback Supabase Auth: {e}")
        delete_supabase_auth_user(supabase_user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la sauvegarde du comptable."
        )


@router.get("/accountants", response_model=List[UserResponse])
def list_accountants(
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Récupère la liste de tous les comptables.
    """
    accountants = db.query(User).filter(User.role == UserRole.COMPTABLE).all()
    return accountants


@router.get("/accountants/{accountant_id}", response_model=UserResponse)
def get_accountant(
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


@router.put("/accountants/{accountant_id}", response_model=UserResponse)
def update_accountant(
    accountant_id: str,
    payload: UserCreate,
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

    if payload.email != accountant.email:
        existing_user = db.query(User).filter(User.email == payload.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un utilisateur avec cet email existe déjà."
            )

    accountant.first_name = payload.first_name
    accountant.last_name = payload.last_name
    accountant.email = payload.email
    accountant.phone = payload.phone
    if payload.password:
        accountant.password = hash_password(payload.password)

    db.commit()
    db.refresh(accountant)
    return accountant


@router.patch("/accountants/{accountant_id}/status", response_model=UserResponse)
def toggle_accountant_status(
    accountant_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Désactive/Réactive un comptable.
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
def delete_accountant(
    accountant_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Supprime définitivement un comptable de la base de données et de Supabase Auth.
    Réservé aux administrateurs.
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
        except Exception as se:
            logger.warning(f"Impossible de supprimer le comptable de Supabase Auth: {se}")

        return {"message": "Comptable supprimé avec succès."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression du comptable : {str(e)}"
        )


# ==========================================
# 2. GESTION DES PARENTS
# ==========================================

@router.post("/parents", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_parent(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Crée un nouveau parent (Supabase Auth + DB).
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
        logger.error(f"[UsersRouter] Échec insertion parent, rollback Supabase Auth: {e}")
        delete_supabase_auth_user(supabase_user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la sauvegarde du parent."
        )


@router.get("/parents", response_model=List[UserResponse])
def list_parents(
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Récupère la liste de tous les parents.
    """
    parents = db.query(User).filter(User.role == UserRole.PARENT).all()
    return parents


@router.get("/parents/{parent_id}", response_model=UserResponse)
def get_parent(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
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


@router.put("/parents/{parent_id}", response_model=UserResponse)
def update_parent(
    parent_id: str,
    payload: UserCreate,
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

    if payload.email != parent.email:
        existing_user = db.query(User).filter(User.email == payload.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un utilisateur avec cet email existe déjà."
            )

    parent.first_name = payload.first_name
    parent.last_name = payload.last_name
    parent.email = payload.email
    parent.phone = payload.phone
    if payload.password:
        parent.password = hash_password(payload.password)

    db.commit()
    db.refresh(parent)
    return parent


@router.patch("/parents/{parent_id}/status", response_model=UserResponse)
def toggle_parent_status(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Désactive/Réactive un parent.
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
def delete_parent(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Supprime définitivement un parent, ses enfants associés et leurs comptes/paiements.
    Réservé aux administrateurs.
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
        except Exception as se:
            logger.warning(f"Impossible de supprimer le parent de Supabase Auth: {se}")

        return {"message": "Parent et ses enfants associés supprimés avec succès."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression du parent : {str(e)}"
        )


# ==========================================
# 3. INFO SUPPLÉMENTAIRE (Nombre d'enfants pour parents)
# ==========================================

@router.get("/parents/{parent_id}/children-count")
def get_parent_children_count(
    parent_id: str,
    db: Session = Depends(get_db),
    _current_user=Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Récupère le nombre d'enfants associés à un parent.
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

    children_count = db.query(Student).filter(
        Student.user_id == str(parent_id)
    ).count()

    return {"parent_id": parent_id, "children_count": children_count}
