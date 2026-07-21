import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Student, StudentAccount, Payment
from app.schemas import PaymentCreate, PaymentResponse, StudentAccountResponse
from app.security import get_current_user, RoleChecker

router = APIRouter(
    prefix="/api/payments",
    tags=["Gestion Financière & Paiements (Sprint 3)"]
)


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    _current_user = Depends(RoleChecker(["ADMIN", "COMPTABLE"]))
):
    """Enregistre un paiement pour un élève et met à jour automatiquement son compte financier."""
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
        ref_code = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        payment_op = getattr(payload, 'payment_method', getattr(payload, 'operator', 'AIRTEL_MONEY'))

        payment = Payment(
            student_account_id=account.id,
            amount=float(payload.amount),
            reference=ref_code,
            operator=payment_op,
            status="VALIDE",
            payment_date=datetime.utcnow()
        )
        db.add(payment)

        account.paid_amount = round(float(account.paid_amount) + float(payload.amount), 2)
        account.remaining_amount = round(float(account.total_amount) - float(account.paid_amount), 2)

        if account.remaining_amount <= 0:
            account.remaining_amount = 0.0
            account.status = "SOLDE"
        elif account.paid_amount > 0:
            account.status = "PARTIEL"
        else:
            account.status = "NON_SOLDE"

        db.commit()
        db.refresh(payment)
        return payment

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'enregistrement du paiement : {str(e)}"
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
    
    payments = db.query(Payment).filter(Payment.student_account_id == account.id).all()
    return payments