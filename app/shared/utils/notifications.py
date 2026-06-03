import logging

from app.extensions import get_db

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "pending":   ("Tu solicitud fue recibida",        "Estamos esperando que la fundación la revise."),
    "reviewing": ("Tu solicitud está en revisión",     "La fundación está evaluando tu solicitud de adopción."),
    "approved":  ("¡Tu solicitud fue aprobada!",       "La fundación aprobó tu solicitud. Ya puedes agendar tu visita."),
    "rejected":  ("Tu solicitud no fue aprobada",      "La fundación no pudo aprobar tu solicitud en este momento."),
    "completed": ("¡Adopción completada!",             "La adopción fue marcada como completada. ¡Bienvenido a la familia!"),
}


def create_notification(
    user_id: str,
    ntype: str,
    title: str,
    body: str,
    metadata: dict | None = None,
) -> None:
    try:
        get_db().table("notifications").insert({
            "user_id": user_id,
            "type": ntype,
            "title": title,
            "body": body,
            "metadata": metadata or {},
        }).execute()
    except Exception:
        logger.exception("Failed to create notification for user %s", user_id)


def notify_all_citizens(ntype: str, title: str, body: str, metadata: dict | None = None) -> None:
    try:
        db = get_db()
        result = db.table("profiles").select("id").eq("role", "ciudadano").execute()
        rows = result.data or []
        logger.info("notify_all_citizens: found %d citizens, ntype=%s", len(rows), ntype)
        if not rows:
            logger.warning("notify_all_citizens: no citizens found in profiles table")
            return
        inserts = [
            {
                "user_id": r["id"],
                "type": ntype,
                "title": title,
                "body": body,
                "metadata": metadata or {},
            }
            for r in rows
        ]
        db.table("notifications").insert(inserts).execute()
        logger.info("notify_all_citizens: inserted %d notifications", len(inserts))
    except Exception:
        logger.exception("Failed to notify all citizens")


def notify_adoption_status(
    *,
    adopter_id: str,
    pet_name: str,
    new_status: str,
    adoption_id: int,
) -> None:
    title, body_template = _STATUS_LABELS.get(
        new_status,
        ("Actualización en tu solicitud", "El estado de tu solicitud ha cambiado."),
    )
    create_notification(
        user_id=adopter_id,
        ntype="adoption_status_changed",
        title=title,
        body=f"{body_template.replace('tu solicitud', f'tu solicitud para adoptar a **{pet_name}**')}",
        metadata={"adoption_id": adoption_id, "pet_name": pet_name, "status": new_status},
    )
