import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import resend
from flask import current_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _send(to: str, subject: str, html: str) -> None:
    resend.api_key = current_app.config["EMAIL_API_KEY"]
    resend.Emails.send(
        {
            "from": current_app.config["EMAIL_FROM"],
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )


def _send_smtp(to: str, subject: str, html: str) -> None:
    cfg = current_app.config
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["SMTP_USER"]
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"]) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        server.sendmail(cfg["SMTP_USER"], to, msg.as_string())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_foundation_approved(to_email: str, org_name: str) -> None:
    frontend_url = current_app.config["FRONTEND_URL"]
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f7f6;font-family:sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:600px;">
        <tr>
          <td style="background:#1a7f5a;padding:32px 40px;">
            <h1 style="margin:0;color:#ffffff;font-size:24px;">Huellitas 🐾</h1>
          </td>
        </tr>
        <tr>
          <td style="padding:40px;">
            <h2 style="color:#1a7f5a;margin-top:0;">¡Bienvenida, {org_name}!</h2>
            <p style="color:#374151;line-height:1.6;">
              Nos alegra informarte que tu fundación ha sido
              <strong>aprobada</strong> en la plataforma Huellitas.
              Ya puedes iniciar sesión y comenzar a publicar mascotas en adopción.
            </p>
            <a href="{frontend_url}/login"
               style="display:inline-block;margin-top:24px;padding:14px 28px;
                      background:#1a7f5a;color:#ffffff;text-decoration:none;
                      border-radius:6px;font-weight:600;font-size:15px;">
              Ingresar a la plataforma
            </a>
            <p style="margin-top:40px;color:#6b7280;font-size:13px;">
              Si tienes alguna duda, responde este correo y con gusto te ayudamos.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f4f7f6;padding:20px 40px;text-align:center;">
            <p style="margin:0;color:#9ca3af;font-size:12px;">
              © Huellitas — Plataforma de adopción de mascotas
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""
    _send(to_email, "¡Tu fundación fue aprobada en Huellitas!", html)


def send_foundation_rejected(to_email: str, org_name: str, reason: str) -> None:
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f7f6;font-family:sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:600px;">
        <tr>
          <td style="background:#1a7f5a;padding:32px 40px;">
            <h1 style="margin:0;color:#ffffff;font-size:24px;">Huellitas 🐾</h1>
          </td>
        </tr>
        <tr>
          <td style="padding:40px;">
            <h2 style="color:#374151;margin-top:0;">Actualización sobre tu solicitud</h2>
            <p style="color:#374151;line-height:1.6;">
              Hola <strong>{org_name}</strong>,
              hemos revisado tu solicitud y lamentamos informarte que
              no fue aprobada en este momento.
            </p>
            <div style="background:#fef2f2;border-left:4px solid #ef4444;
                        padding:16px 20px;border-radius:4px;margin:24px 0;">
              <p style="margin:0;color:#374151;font-size:14px;">
                <strong>Motivo:</strong>
              </p>
              <p style="margin:8px 0 0;color:#374151;font-size:14px;line-height:1.5;">
                {reason}
              </p>
            </div>
            <p style="color:#374151;line-height:1.6;">
              Si crees que hay un error o deseas más información, contáctanos en
              <a href="mailto:soporte@huellitas.app" style="color:#1a7f5a;">
                soporte@huellitas.app
              </a>.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f4f7f6;padding:20px 40px;text-align:center;">
            <p style="margin:0;color:#9ca3af;font-size:12px;">
              © Huellitas — Plataforma de adopción de mascotas
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""
    _send(to_email, "Resultado de tu solicitud en Huellitas", html)


def send_password_reset_otp(to_email: str, otp: str) -> None:
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f7f6;font-family:sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:600px;">
        <tr>
          <td style="background:#1a7f5a;padding:32px 40px;">
            <h1 style="margin:0;color:#ffffff;font-size:24px;">Huellitas 🐾</h1>
          </td>
        </tr>
        <tr>
          <td style="padding:40px;">
            <h2 style="color:#1a7f5a;margin-top:0;">Restablecer contraseña</h2>
            <p style="color:#374151;line-height:1.6;">
              Recibimos una solicitud para restablecer la contraseña de tu cuenta.
              Usa el siguiente código de verificación:
            </p>
            <div style="text-align:center;margin:32px 0;">
              <span style="display:inline-block;letter-spacing:12px;font-size:40px;
                           font-weight:700;color:#1a7f5a;background:#f0fdf4;
                           padding:20px 32px;border-radius:12px;border:2px solid #bbf7d0;">
                {otp}
              </span>
            </div>
            <p style="color:#374151;line-height:1.6;">
              Este código es válido por <strong>10 minutos</strong>.
              Si no solicitaste este cambio, puedes ignorar este correo.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f4f7f6;padding:20px 40px;text-align:center;">
            <p style="margin:0;color:#9ca3af;font-size:12px;">
              © Huellitas — Plataforma de adopción de mascotas
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""
    _send_smtp(to_email, "Código de verificación — Huellitas", html)
