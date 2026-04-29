import logging

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
    digits_html = "".join(
        f'<td style="padding:0 6px;">'
        f'<span style="display:inline-block;width:52px;height:64px;line-height:64px;'
        f'text-align:center;font-size:32px;font-weight:800;color:#e85d26;'
        f'background:#ffffff;border:2px solid #f0c9b4;border-radius:12px;">'
        f'{d}</span></td>'
        for d in otp
    )
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#fff5f0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:48px 16px;">

        <table width="560" cellpadding="0" cellspacing="0"
               style="max-width:560px;background:#ffffff;border-radius:16px;
                      overflow:hidden;box-shadow:0 4px 24px rgba(232,93,38,0.10);">

          <!-- Header -->
          <tr>
            <td style="background:#e85d26;padding:32px 40px;">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-size:22px;font-weight:800;color:#ffffff;
                                 letter-spacing:-0.5px;">Huellitas</span>
                    <span style="font-size:22px;color:rgba(255,255,255,0.65);
                                 font-weight:400;margin-left:4px;">API</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:4px;">
                    <span style="font-size:11px;color:rgba(255,255,255,0.7);
                                 letter-spacing:0.12em;text-transform:uppercase;">
                      Plataforma de adopción · Tolima
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">

              <!-- Icon -->
              <div style="width:56px;height:56px;background:#fdf3ee;border-radius:14px;
                          display:flex;align-items:center;justify-content:center;
                          margin-bottom:24px;">
                <span style="font-size:28px;line-height:56px;display:block;
                             text-align:center;">🔐</span>
              </div>

              <h2 style="margin:0 0 8px;font-size:22px;font-weight:800;
                         color:#1c1009;letter-spacing:-0.3px;">
                Restablecer contraseña
              </h2>
              <p style="margin:0 0 28px;font-size:15px;color:#78716c;line-height:1.6;">
                Recibimos una solicitud para restablecer la contraseña de tu cuenta.
                Usa el siguiente código de verificación:
              </p>

              <!-- OTP box -->
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="background:#fff5f0;border:1.5px solid #f0c9b4;
                              border-radius:14px;padding:28px 24px;text-align:center;">
                    <p style="margin:0 0 16px;font-size:11px;font-weight:600;
                               color:#c94e1e;letter-spacing:0.15em;text-transform:uppercase;">
                      Código de verificación
                    </p>
                    <table cellpadding="0" cellspacing="0"
                           style="margin:0 auto;">
                      <tr>{digits_html}</tr>
                    </table>
                    <p style="margin:16px 0 0;font-size:12px;color:#a8a29e;">
                      Válido por <strong style="color:#1c1009;">10 minutos</strong>
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:28px 0 0;font-size:13px;color:#a8a29e;line-height:1.6;">
                Si no solicitaste este cambio, puedes ignorar este correo de forma segura.
                Tu contraseña no será modificada.
              </p>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#fdf3ee;padding:20px 40px;border-top:1px solid #f0c9b4;">
              <p style="margin:0;font-size:12px;color:#c4a090;text-align:center;">
                © Huellitas — Plataforma de adopción de mascotas · Tolima, Colombia
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    _send(to_email, "Código de verificación — Huellitas", html)
