import os
import uuid
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_KEY", "")


class SupabaseAdminError(Exception):
    """Exception levée en cas d'erreur de communication avec Supabase Auth Admin."""
    pass


def create_supabase_auth_user(
    email: str,
    password: str,
    user_metadata: Dict[str, Any]
) -> str:
    """
    Crée un utilisateur dans Supabase Auth en utilisant l'API Admin (SERVICE_ROLE_KEY).
    Retourne l'ID unique (UUID) généré par Supabase.
    Si SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY n'est pas configuré, génère un UUID local (mode dev).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning(
            "[SupabaseAdmin] SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY non configuré. "
            "Génération d'un UUID local de secours pour dev."
        )
        return str(uuid.uuid4())

    endpoint = f"{SUPABASE_URL}/auth/v1/admin/users"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": user_metadata,
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            user_id = data.get("id")
            if not user_id:
                raise SupabaseAdminError("Supabase N'a pas retourné d'ID d'utilisateur.")
            logger.info(f"[SupabaseAdmin] Utilisateur Supabase Auth créé avec succès (ID: {user_id}).")
            return str(user_id)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error(f"[SupabaseAdmin] Erreur HTTP Supabase {e.code}: {error_body}")
        try:
            parsed = json.loads(error_body)
            msg = parsed.get("msg") or parsed.get("message") or error_body
        except Exception:
            msg = error_body
        raise SupabaseAdminError(f"Erreur Supabase Auth ({e.code}): {msg}")
    except Exception as e:
        logger.error(f"[SupabaseAdmin] Erreur inattendue: {e}")
        raise SupabaseAdminError(f"Erreur de connexion Supabase Auth: {str(e)}")


def delete_supabase_auth_user(user_id: str) -> bool:
    """
    Supprime un utilisateur dans Supabase Auth (rollback en cas d'erreur de transaction DB).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("[SupabaseAdmin] Supabase non configuré, omission du rollback Supabase.")
        return True

    endpoint = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }

    try:
        req = urllib.request.Request(
            endpoint,
            headers=headers,
            method="DELETE"
        )
        with urllib.request.urlopen(req) as resp:
            logger.info(f"[SupabaseAdmin] Rollback réussi : Utilisateur Supabase Auth {user_id} supprimé.")
            return True
    except Exception as e:
        logger.error(f"[SupabaseAdmin] Échec du rollback Supabase Auth pour {user_id}: {e}")
        return False
