import uuid
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Student, StudentAccount, Payment, SchoolClass, PaymentStatus, UserRole, User
from app.schemas import PaymentCreate, PaymentResponse, StudentAccountResponse, PaymentRejectRequest
from app.security import get_current_user, RoleChecker

router = APIRouter(
    prefix="/api/payments",
    tags=["Gestion Financière & Paiements (Sprint 3)"]
)


@router.get("/stats")
def get_payment_stats(
    db: Session = Depends(get_db),
    _current_user: User = Depends(RoleChecker([UserRole.COMPTABLE, UserRole.ADMIN]))
):
    """
    Renseigne les métriques clés pour le dashboard Comptable / Admin :
    - Total encaissé (somme de tous les paiements APPROVED / VALIDÉ)
    - Nombre de paiements en attente de validation (PENDING / EN_ATTENTE)
    """
    approved_statuses = ["APPROVED", "VALIDE", "VALIDÉ"]
    pending_statuses = ["PENDING", "EN_ATTENTE", "EN ATTENTE"]

    # Total encaissé sur tous les paiements approuvés / validés
    total_collected = db.query(func.sum(Payment.amount)).filter(
        func.upper(Payment.status).in_(approved_statuses)
    ).scalar() or 0.0

    # Nombre de dossiers en attente de validation
    pending_count = db.query(Payment).filter(
        func.upper(Payment.status).in_(pending_statuses)
    ).count()

    return {
        "total_collected": round(float(total_collected), 2),
        "pending_count": pending_count
    }


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN, UserRole.COMPTABLE, UserRole.PARENT]))
):
    """
    Enregistre une déclaration de paiement (statut initial : PENDING).
    Le compte de l'élève sera mis à jour uniquement après validation par le Comptable.
    """
    if payload.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le montant du versement doit être strictement supérieur à 0."
        )

    student = db.query(Student).filter(Student.id == payload.student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Élève introuvable."
        )

    account = db.query(StudentAccount).filter(StudentAccount.student_id == payload.student_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte financier introuvable pour cet élève."
        )

    try:
        ref_code = payload.reference if payload.reference else f"PAY-{uuid.uuid4().hex[:8].upper()}"
        payment_op = getattr(payload, 'operator', 'AIRTEL_MONEY')

        payment = Payment(
            student_account_id=account.id,
            amount=float(payload.amount),
            reference=ref_code,
            operator=payment_op,
            status=PaymentStatus.PENDING.value if hasattr(PaymentStatus.PENDING, 'value') else "PENDING",
            payment_date=datetime.utcnow()
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        res_data = PaymentResponse.model_validate(payment)
        res_data.student_name = f"{student.first_name} {student.last_name}".strip()
        return res_data

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'enregistrement du paiement : {str(e)}"
        )


@router.patch("/{payment_id}/validate", response_model=PaymentResponse)
def validate_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker([UserRole.COMPTABLE, UserRole.ADMIN]))
):
    """
    Validation d'un paiement par le Comptable/Admin.
    Passe le statut à APPROVED et met à jour le compte financier de l'élève.
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paiement non trouvé.")

    approved_val = PaymentStatus.APPROVED.value if hasattr(PaymentStatus.APPROVED, 'value') else "APPROVED"

    if str(payment.status).upper() in ["APPROVED", "VALIDE", "VALIDÉ"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ce paiement a déjà été validé.")

    account = db.query(StudentAccount).filter(StudentAccount.id == payment.student_account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte élève associé introuvable.")

    try:
        payment.status = approved_val
        payment.validated_at = datetime.utcnow()
        payment.validated_by_id = current_user.id

        current_paid = float(account.paid_amount or 0.0)
        account.paid_amount = round(current_paid + float(payment.amount), 2)
        account.remaining_amount = round(float(account.total_amount) - account.paid_amount, 2)

        if account.remaining_amount <= 0:
            account.remaining_amount = 0.0
            account.status = "SOLDE"
        elif account.paid_amount > 0:
            account.status = "PARTIEL"
        else:
            account.status = "NON_SOLDE"

        db.commit()
        db.refresh(payment)

        res_data = PaymentResponse.model_validate(payment)
        student = account.student
        if student:
            res_data.student_name = f"{student.first_name} {student.last_name}".strip()
        return res_data

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la validation du paiement : {str(e)}"
        )


@router.patch("/{payment_id}/reject", response_model=Dict[str, str])
def reject_payment(
    payment_id: int,
    payload: PaymentRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker([UserRole.COMPTABLE, UserRole.ADMIN]))
):
    """
    Rejet d'un paiement par le Comptable/Admin avec enregistrement du motif 
    et envoi automatique d'une notification au parent.
    Renvoie le message de confirmation : {"message": "Paiement rejeté"}
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Paiement non trouvé."
        )

    # Conversion propre du statut pour éviter les conflits d'Enum/String
    raw_status = payment.status.value if hasattr(payment.status, 'value') else str(payment.status)
    current_status = raw_status.upper()

    # Seuls les paiements déjà validés ne peuvent plus être rejetés
    if current_status in ["APPROVED", "VALIDE", "VALIDÉ"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Impossible de rejeter un paiement qui a déjà été validé."
        )

    # Application du motif par défaut si champ non renseigné
    reason_text = payload.reason.strip() if (payload.reason and payload.reason.strip()) else "Référence introuvable"

    try:
        rejected_val = PaymentStatus.REJECTED.value if hasattr(PaymentStatus.REJECTED, 'value') else "REJECTED"

        payment.status = rejected_val
        payment.rejection_reason = reason_text
        payment.validated_at = datetime.utcnow()
        payment.validated_by_id = current_user.id

        db.commit()

        # Logique de notification Parent
        account = db.query(StudentAccount).filter(StudentAccount.id == payment.student_account_id).first()
        if account and account.student:
            student = account.student
            notification_text = (
                f"NOTIFICATION PARENT : Le paiement de {payment.amount} FCFA (Réf: {payment.reference}) "
                f"pour l'élève {student.first_name} {student.last_name} a été rejeté. "
                f"Motif : {reason_text}."
            )
            print(f"📩 [MESSAGE ENVOYÉ AU PARENT] -> {notification_text}")

        return {"message": "Paiement rejeté"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du rejet du paiement : {str(e)}"
        )


@router.get("/account/{student_id}", response_model=StudentAccountResponse)
def get_student_account(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user)
):
    """Consulter le solde et le statut du compte financier d'un élève."""
    account = db.query(StudentAccount).filter(StudentAccount.student_id == student_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte financier introuvable."
        )
    return account


@router.get("/history/{student_id}", response_model=List[PaymentResponse])
def get_payment_history(
    student_id: int,
    db: Session = Depends(get_db),
    _current_user = Depends(get_current_user)
):
    """Consulter l'historique complet des versements effectués pour un élève."""
    account = db.query(StudentAccount).filter(StudentAccount.student_id == student_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte financier introuvable."
        )
    
    payments = db.query(Payment).filter(Payment.student_account_id == account.id).order_by(Payment.payment_date.desc()).all()
    return payments


@router.get("/", response_model=List[PaymentResponse])
def list_all_payments(
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker([UserRole.ADMIN, UserRole.COMPTABLE]))
):
    """
    Permet aux administrateurs et comptables de lister l'ensemble
    des paiements enregistrés dans l'établissement avec le nom de l'élève et la classe.
    """
    rows = (
        db.query(Payment, Student.first_name, Student.last_name, SchoolClass.name.label("class_name"))
        .join(StudentAccount, Payment.student_account_id == StudentAccount.id)
        .join(Student, StudentAccount.student_id == Student.id)
        .outerjoin(SchoolClass, Student.class_id == SchoolClass.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )

    results = []
    for payment, first_name, last_name, class_name in rows:
        p_data = PaymentResponse.model_validate(payment)
        p_data.student_name = f"{first_name or ''} {last_name or ''}".strip()
        p_data.class_name = class_name or "N/A"
        results.append(p_data)

    return results