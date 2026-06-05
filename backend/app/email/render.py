"""Localized transactional-email rendering.

One module owns the copy for every transactional email in all 7
locales. A template = an entry in `_TEMPLATES` (subject / heading /
paragraphs / button) + the shared chrome in `_COMMON` (fallback-link
note, ignore note, signature). Adding a locale string is a dict edit,
never a migration.

Security: ctx values (org name, role, URLs) are user/tenant-derived,
so the HTML body is rendered through a Jinja env with
`autoescape=True` — an org named `<script>` lands as text, not markup.
The plaintext body uses a separate non-escaping env (entities like
`&amp;` would be noise in a text/plain part).

Catalog strings use Jinja placeholders (`{{ org_name }}`) so the same
string renders into both the escaped HTML part and the raw text part.
"""

from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Environment, select_autoescape

# ──────────────────────────── Supported locales ──────────────────────────
# Mirror the frontend's 7-locale set. Unknown locales fall back to en.
SUPPORTED_LOCALES = ("en", "pt", "de", "fr", "it", "rm", "es")
_DEFAULT_LOCALE = "en"

# Template identifiers — the public `send()` API takes one of these.
TEMPLATE_INVITE = "invite"
TEMPLATE_PASSWORD_RESET = "password_reset"
TEMPLATE_VERIFY_EMAIL = "verify_email"

# Two envs: HTML escapes ctx (XSS defense in the inbox), text does not.
_html_env = Environment(autoescape=select_autoescape(["html", "xml"]))
_text_env = Environment(autoescape=False)


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


# Chrome shared across every template, per locale. Kept separate from
# per-template copy so a wording tweak to "the link doesn't work" note
# touches one place, not N templates.
_COMMON: dict[str, dict[str, str]] = {
    "en": {
        "fallback": "If the button above doesn't work, copy and paste this link into your browser:",
        "ignore": "If you weren't expecting this email, you can safely ignore it.",
        "signature": "— The {{ app_name }} team",
    },
    "pt": {
        "fallback": "Se o botão acima não funcionar, copie e cole este link no seu navegador:",
        "ignore": "Se você não esperava este e-mail, pode ignorá-lo com segurança.",
        "signature": "— A equipe {{ app_name }}",
    },
    "de": {
        "fallback": "Falls der Button oben nicht funktioniert, kopieren Sie diesen Link in Ihren Browser:",
        "ignore": "Wenn Sie diese E-Mail nicht erwartet haben, können Sie sie ignorieren.",
        "signature": "— Ihr {{ app_name }}-Team",
    },
    "fr": {
        "fallback": "Si le bouton ci-dessus ne fonctionne pas, copiez ce lien dans votre navigateur :",
        "ignore": "Si vous n'attendiez pas cet e-mail, vous pouvez l'ignorer.",
        "signature": "— L'équipe {{ app_name }}",
    },
    "it": {
        "fallback": "Se il pulsante qui sopra non funziona, copia questo link nel tuo browser:",
        "ignore": "Se non ti aspettavi questa e-mail, puoi ignorarla.",
        "signature": "— Il team {{ app_name }}",
    },
    "rm": {
        "fallback": "Sche il buttun survart na funcziuna betg, copiai quai link en voss navigatur:",
        "ignore": "Sche Vus n'avais betg spetgà questa e-mail, pudais La ignorar.",
        "signature": "— Voss team {{ app_name }}",
    },
    "es": {
        "fallback": "Si el botón de arriba no funciona, copia y pega este enlace en tu navegador:",
        "ignore": "Si no esperabas este correo, puedes ignorarlo de forma segura.",
        "signature": "— El equipo de {{ app_name }}",
    },
}


# Per-template copy. `paragraphs` is a list so the body can grow without
# a structural change. Placeholders are Jinja vars resolved from ctx.
_TEMPLATES: dict[str, dict[str, dict]] = {
    TEMPLATE_INVITE: {
        "en": {
            "subject": "You've been invited to join {{ org_name }}",
            "preheader": "Accept your invitation to {{ org_name }} on {{ app_name }}.",
            "heading": "Join {{ org_name }}",
            "paragraphs": [
                "You've been invited to join {{ org_name }} on {{ app_name }} as {{ role }}.",
                "Click the button below to create your account and get started.",
            ],
            "button": "Accept invitation",
            "expiry": "This invitation expires on {{ expires_at }}.",
        },
        "pt": {
            "subject": "Você foi convidado para entrar em {{ org_name }}",
            "preheader": "Aceite seu convite para {{ org_name }} no {{ app_name }}.",
            "heading": "Entrar em {{ org_name }}",
            "paragraphs": [
                "Você foi convidado para entrar em {{ org_name }} no {{ app_name }} como {{ role }}.",
                "Clique no botão abaixo para criar sua conta e começar.",
            ],
            "button": "Aceitar convite",
            "expiry": "Este convite expira em {{ expires_at }}.",
        },
        "de": {
            "subject": "Sie wurden eingeladen, {{ org_name }} beizutreten",
            "preheader": "Nehmen Sie Ihre Einladung zu {{ org_name }} auf {{ app_name }} an.",
            "heading": "{{ org_name }} beitreten",
            "paragraphs": [
                "Sie wurden eingeladen, {{ org_name }} auf {{ app_name }} als {{ role }} beizutreten.",
                "Klicken Sie auf die Schaltfläche unten, um Ihr Konto zu erstellen.",
            ],
            "button": "Einladung annehmen",
            "expiry": "Diese Einladung läuft am {{ expires_at }} ab.",
        },
        "fr": {
            "subject": "Vous avez été invité à rejoindre {{ org_name }}",
            "preheader": "Acceptez votre invitation à {{ org_name }} sur {{ app_name }}.",
            "heading": "Rejoindre {{ org_name }}",
            "paragraphs": [
                "Vous avez été invité à rejoindre {{ org_name }} sur {{ app_name }} en tant que {{ role }}.",
                "Cliquez sur le bouton ci-dessous pour créer votre compte.",
            ],
            "button": "Accepter l'invitation",
            "expiry": "Cette invitation expire le {{ expires_at }}.",
        },
        "it": {
            "subject": "Sei stato invitato a unirti a {{ org_name }}",
            "preheader": "Accetta il tuo invito a {{ org_name }} su {{ app_name }}.",
            "heading": "Unisciti a {{ org_name }}",
            "paragraphs": [
                "Sei stato invitato a unirti a {{ org_name }} su {{ app_name }} come {{ role }}.",
                "Clicca sul pulsante qui sotto per creare il tuo account.",
            ],
            "button": "Accetta l'invito",
            "expiry": "Questo invito scade il {{ expires_at }}.",
        },
        "rm": {
            "subject": "Vus essas vegnì envidà da Vus participar a {{ org_name }}",
            "preheader": "Acceptai Voss invit a {{ org_name }} sin {{ app_name }}.",
            "heading": "Participar a {{ org_name }}",
            "paragraphs": [
                "Vus essas vegnì envidà da participar a {{ org_name }} sin {{ app_name }} sco {{ role }}.",
                "Cliccai sin il buttun sutvart per crear Voss conto.",
            ],
            "button": "Acceptar l'invit",
            "expiry": "Quest invit scada ils {{ expires_at }}.",
        },
        "es": {
            "subject": "Has sido invitado a unirte a {{ org_name }}",
            "preheader": "Acepta tu invitación a {{ org_name }} en {{ app_name }}.",
            "heading": "Unirse a {{ org_name }}",
            "paragraphs": [
                "Has sido invitado a unirte a {{ org_name }} en {{ app_name }} como {{ role }}.",
                "Haz clic en el botón de abajo para crear tu cuenta y empezar.",
            ],
            "button": "Aceptar invitación",
            "expiry": "Esta invitación caduca el {{ expires_at }}.",
        },
    },
    TEMPLATE_PASSWORD_RESET: {
        "en": {
            "subject": "Reset your {{ app_name }} password",
            "preheader": "Use this link to choose a new password.",
            "heading": "Reset your password",
            "paragraphs": [
                "We received a request to reset the password for your {{ app_name }} account.",
                "Click the button below to choose a new password.",
            ],
            "button": "Reset password",
            "expiry": "This link expires in {{ expires_hours }} hour(s). If it expires, request a new one.",
        },
        "pt": {
            "subject": "Redefina sua senha do {{ app_name }}",
            "preheader": "Use este link para escolher uma nova senha.",
            "heading": "Redefina sua senha",
            "paragraphs": [
                "Recebemos uma solicitação para redefinir a senha da sua conta no {{ app_name }}.",
                "Clique no botão abaixo para escolher uma nova senha.",
            ],
            "button": "Redefinir senha",
            "expiry": "Este link expira em {{ expires_hours }} hora(s). Se expirar, solicite um novo.",
        },
        "de": {
            "subject": "Setzen Sie Ihr {{ app_name }}-Passwort zurück",
            "preheader": "Verwenden Sie diesen Link, um ein neues Passwort zu wählen.",
            "heading": "Passwort zurücksetzen",
            "paragraphs": [
                "Wir haben eine Anfrage zum Zurücksetzen des Passworts für Ihr {{ app_name }}-Konto erhalten.",
                "Klicken Sie auf die Schaltfläche unten, um ein neues Passwort zu wählen.",
            ],
            "button": "Passwort zurücksetzen",
            "expiry": "Dieser Link läuft in {{ expires_hours }} Stunde(n) ab. Fordern Sie danach einen neuen an.",
        },
        "fr": {
            "subject": "Réinitialisez votre mot de passe {{ app_name }}",
            "preheader": "Utilisez ce lien pour choisir un nouveau mot de passe.",
            "heading": "Réinitialiser votre mot de passe",
            "paragraphs": [
                "Nous avons reçu une demande de réinitialisation du mot de passe de votre compte {{ app_name }}.",
                "Cliquez sur le bouton ci-dessous pour choisir un nouveau mot de passe.",
            ],
            "button": "Réinitialiser le mot de passe",
            "expiry": "Ce lien expire dans {{ expires_hours }} heure(s). S'il expire, demandez-en un nouveau.",
        },
        "it": {
            "subject": "Reimposta la tua password di {{ app_name }}",
            "preheader": "Usa questo link per scegliere una nuova password.",
            "heading": "Reimposta la password",
            "paragraphs": [
                "Abbiamo ricevuto una richiesta di reimpostazione della password del tuo account {{ app_name }}.",
                "Clicca sul pulsante qui sotto per scegliere una nuova password.",
            ],
            "button": "Reimposta password",
            "expiry": "Questo link scade tra {{ expires_hours }} ora/e. Se scade, richiedine uno nuovo.",
        },
        "rm": {
            "subject": "Reinizialisai Voss pled-clav da {{ app_name }}",
            "preheader": "Dovrai quai link per tscherner in nov pled-clav.",
            "heading": "Reinizialisar il pled-clav",
            "paragraphs": [
                "Nus avain retschavì ina dumonda da reinizialisar il pled-clav da Voss conto {{ app_name }}.",
                "Cliccai sin il buttun sutvart per tscherner in nov pled-clav.",
            ],
            "button": "Reinizialisar il pled-clav",
            "expiry": "Quai link scada en {{ expires_hours }} ura(s). Sch'el scada, dumandai in nov.",
        },
        "es": {
            "subject": "Restablece tu contraseña de {{ app_name }}",
            "preheader": "Usa este enlace para elegir una nueva contraseña.",
            "heading": "Restablece tu contraseña",
            "paragraphs": [
                "Recibimos una solicitud para restablecer la contraseña de tu cuenta de {{ app_name }}.",
                "Haz clic en el botón de abajo para elegir una nueva contraseña.",
            ],
            "button": "Restablecer contraseña",
            "expiry": "Este enlace caduca en {{ expires_hours }} hora(s). Si caduca, solicita uno nuevo.",
        },
    },
    TEMPLATE_VERIFY_EMAIL: {
        "en": {
            "subject": "Confirm your email for {{ app_name }}",
            "preheader": "Confirm your email address to activate your account.",
            "heading": "Confirm your email",
            "paragraphs": [
                "Thanks for signing up for {{ app_name }}.",
                "Click the button below to confirm your email address and activate your account.",
            ],
            "button": "Confirm email",
            "expiry": "This link expires in {{ expires_hours }} hour(s). If it expires, request a new one from the sign-in page.",
        },
        "pt": {
            "subject": "Confirme seu e-mail para {{ app_name }}",
            "preheader": "Confirme seu endereço de e-mail para ativar sua conta.",
            "heading": "Confirme seu e-mail",
            "paragraphs": [
                "Obrigado por se cadastrar no {{ app_name }}.",
                "Clique no botão abaixo para confirmar seu endereço de e-mail e ativar sua conta.",
            ],
            "button": "Confirmar e-mail",
            "expiry": "Este link expira em {{ expires_hours }} hora(s). Se expirar, solicite um novo na página de login.",
        },
        "de": {
            "subject": "Bestätigen Sie Ihre E-Mail für {{ app_name }}",
            "preheader": "Bestätigen Sie Ihre E-Mail-Adresse, um Ihr Konto zu aktivieren.",
            "heading": "E-Mail bestätigen",
            "paragraphs": [
                "Danke, dass Sie sich bei {{ app_name }} registriert haben.",
                "Klicken Sie auf die Schaltfläche unten, um Ihre E-Mail-Adresse zu bestätigen und Ihr Konto zu aktivieren.",
            ],
            "button": "E-Mail bestätigen",
            "expiry": "Dieser Link läuft in {{ expires_hours }} Stunde(n) ab. Fordern Sie danach auf der Anmeldeseite einen neuen an.",
        },
        "fr": {
            "subject": "Confirmez votre e-mail pour {{ app_name }}",
            "preheader": "Confirmez votre adresse e-mail pour activer votre compte.",
            "heading": "Confirmez votre e-mail",
            "paragraphs": [
                "Merci de vous être inscrit à {{ app_name }}.",
                "Cliquez sur le bouton ci-dessous pour confirmer votre adresse e-mail et activer votre compte.",
            ],
            "button": "Confirmer l'e-mail",
            "expiry": "Ce lien expire dans {{ expires_hours }} heure(s). S'il expire, demandez-en un nouveau depuis la page de connexion.",
        },
        "it": {
            "subject": "Conferma la tua e-mail per {{ app_name }}",
            "preheader": "Conferma il tuo indirizzo e-mail per attivare il tuo account.",
            "heading": "Conferma la tua e-mail",
            "paragraphs": [
                "Grazie per esserti registrato su {{ app_name }}.",
                "Clicca sul pulsante qui sotto per confermare il tuo indirizzo e-mail e attivare il tuo account.",
            ],
            "button": "Conferma e-mail",
            "expiry": "Questo link scade tra {{ expires_hours }} ora/e. Se scade, richiedine uno nuovo dalla pagina di accesso.",
        },
        "rm": {
            "subject": "Confermai Voss e-mail per {{ app_name }}",
            "preheader": "Confermai Voss adressa d'e-mail per activar Voss conto.",
            "heading": "Confermar Voss e-mail",
            "paragraphs": [
                "Grazia per Vus esser annunzià tar {{ app_name }}.",
                "Cliccai sin il buttun sutvart per confermar Voss adressa d'e-mail ed activar Voss conto.",
            ],
            "button": "Confermar l'e-mail",
            "expiry": "Quai link scada en {{ expires_hours }} ura(s). Sch'el scada, dumandai in nov sin la pagina d'annunzia.",
        },
        "es": {
            "subject": "Confirma tu correo para {{ app_name }}",
            "preheader": "Confirma tu dirección de correo para activar tu cuenta.",
            "heading": "Confirma tu correo",
            "paragraphs": [
                "Gracias por registrarte en {{ app_name }}.",
                "Haz clic en el botón de abajo para confirmar tu dirección de correo y activar tu cuenta.",
            ],
            "button": "Confirmar correo",
            "expiry": "Este enlace caduca en {{ expires_hours }} hora(s). Si caduca, solicita uno nuevo en la página de inicio de sesión.",
        },
    },
}


# Branded, table-based HTML shell. Inline styles + tables because email
# clients (Outlook especially) ignore <style> blocks and flexbox. Kept
# deliberately minimal — one accent color, system font stack.
_HTML_LAYOUT = """\
<!DOCTYPE html>
<html lang="{{ locale }}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ subject }}</title></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;">{{ preheader }}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e6e6ef;">
<tr><td style="background:#4f46e5;padding:20px 32px;color:#ffffff;font-size:18px;font-weight:700;">{{ app_name }}</td></tr>
<tr><td style="padding:32px;">
<h1 style="margin:0 0 16px;font-size:22px;color:#18181b;">{{ heading }}</h1>
{% for p in paragraphs %}<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#3f3f46;">{{ p }}</p>
{% endfor %}<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;"><tr><td style="border-radius:8px;background:#4f46e5;">
<a href="{{ url }}" style="display:inline-block;padding:12px 28px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">{{ button }}</a>
</td></tr></table>
<p style="margin:0 0 8px;font-size:13px;color:#71717a;">{{ expiry }}</p>
<p style="margin:0 0 4px;font-size:13px;color:#71717a;">{{ fallback }}</p>
<p style="margin:0 0 16px;font-size:13px;word-break:break-all;"><a href="{{ url }}" style="color:#4f46e5;">{{ url }}</a></p>
<p style="margin:0;font-size:13px;color:#a1a1aa;">{{ ignore }}</p>
</td></tr>
<tr><td style="padding:20px 32px;border-top:1px solid #e6e6ef;font-size:13px;color:#a1a1aa;">{{ signature }}</td></tr>
</table></td></tr></table></body></html>
"""


def _normalize_locale(locale: str | None) -> str:
    if not locale:
        return _DEFAULT_LOCALE
    short = locale.split("-")[0].lower()
    return short if short in SUPPORTED_LOCALES else _DEFAULT_LOCALE


def _r(env: Environment, template_str: str, ctx: dict) -> str:
    return env.from_string(template_str).render(**ctx)


def render(template: str, locale: str | None, ctx: dict) -> RenderedEmail:
    """Render `template` in `locale` with `ctx`.

    `ctx` must carry the placeholder vars the template references:
      - invite          → org_name, role, url, expires_at
      - password_reset  → url, expires_hours
      - verify_email    → url, expires_hours
    `app_name` is injected automatically. Missing vars render empty
    (Jinja default), so a typo in a call site degrades to a blank,
    not a crash.
    """
    if template not in _TEMPLATES:
        raise ValueError(f"Unknown email template: {template!r}")
    loc = _normalize_locale(locale)
    tpl = _TEMPLATES[template][loc]
    common = _COMMON[loc]
    full_ctx = {"app_name": "CRM Gallo", "locale": loc, **ctx}

    subject = _r(_text_env, tpl["subject"], full_ctx)

    # HTML part — autoescaped.
    html_ctx = {
        **full_ctx,
        "subject": subject,
        "preheader": _r(_html_env, tpl["preheader"], full_ctx),
        "heading": _r(_html_env, tpl["heading"], full_ctx),
        "paragraphs": [_r(_html_env, p, full_ctx) for p in tpl["paragraphs"]],
        "button": _r(_html_env, tpl["button"], full_ctx),
        "expiry": _r(_html_env, tpl["expiry"], full_ctx),
        "fallback": _r(_html_env, common["fallback"], full_ctx),
        "ignore": _r(_html_env, common["ignore"], full_ctx),
        "signature": _r(_html_env, common["signature"], full_ctx),
    }
    html = _r(_html_env, _HTML_LAYOUT, html_ctx)

    # Plaintext part — not escaped.
    text_lines = [
        _r(_text_env, tpl["heading"], full_ctx),
        "",
        *[_r(_text_env, p, full_ctx) for p in tpl["paragraphs"]],
        "",
        full_ctx.get("url", ""),
        "",
        _r(_text_env, tpl["expiry"], full_ctx),
        _r(_text_env, common["ignore"], full_ctx),
        "",
        _r(_text_env, common["signature"], full_ctx),
    ]
    text = "\n".join(text_lines)

    return RenderedEmail(subject=subject, html=html, text=text)
