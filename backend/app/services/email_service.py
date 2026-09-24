"""Email delivery behind a provider interface.

Providers: `mock` (logs only), `smtp` (any SMTP relay), `sendgrid` (SendGrid
v3 Mail Send). Choose with EMAIL_PROVIDER; EMAIL_MOCK_MODE=true always wins."""
import asyncio
import html
import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    success: bool
    provider: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = True


@dataclass
class InvitationContent:
    lead_name: str
    sales_person: str
    date_text: str
    time_text: str
    duration_text: str
    join_url: Optional[str]
    lead_email: str
    label: str


class EmailProvider:
    name = "base"

    async def send(self, to: str, subject: str, html_body: str, text_body: str) -> DeliveryResult:
        raise NotImplementedError


class MockEmailProvider(EmailProvider):
    name = "mock"

    async def send(self, to, subject, html_body, text_body):
        message_id = f"mock-email-{uuid.uuid4().hex[:16]}"
        logger.info("email.mock_sent", extra={"provider_message_id": message_id, "subject": subject})
        return DeliveryResult(True, self.name, message_id)


class SmtpEmailProvider(EmailProvider):
    name = "smtp"

    def _send_sync(self, to, subject, html_body, text_body) -> str:
        msg = EmailMessage()
        msg["From"] = settings.email_from
        msg["To"] = to
        msg["Subject"] = subject
        domain = parseaddr(settings.email_from)[1].split("@")[-1] or "classify.demo"
        msg["Message-ID"] = make_msgid(domain=domain)
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        return msg["Message-ID"]

    async def send(self, to, subject, html_body, text_body):
        if not settings.smtp_host:
            return DeliveryResult(False, self.name, error="SMTP_HOST is not configured", retryable=False)
        try:
            message_id = await asyncio.to_thread(self._send_sync, to, subject, html_body, text_body)
            return DeliveryResult(True, self.name, message_id)
        except smtplib.SMTPRecipientsRefused:
            return DeliveryResult(False, self.name, error="Recipient address was rejected", retryable=False)
        except smtplib.SMTPAuthenticationError:
            return DeliveryResult(False, self.name, error="SMTP authentication failed", retryable=False)
        except (smtplib.SMTPException, OSError) as exc:
            return DeliveryResult(False, self.name, error=f"SMTP error: {type(exc).__name__}")


class SendGridEmailProvider(EmailProvider):
    name = "sendgrid"
    url = "https://api.sendgrid.com/v3/mail/send"

    async def send(self, to, subject, html_body, text_body):
        if not settings.email_api_key:
            return DeliveryResult(False, self.name, error="EMAIL_API_KEY is not configured", retryable=False)
        from_name, from_email = parseaddr(settings.email_from)
        body = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": from_email, **({"name": from_name} if from_name else {})},
            "subject": subject,
            "content": [{"type": "text/plain", "value": text_body}, {"type": "text/html", "value": html_body}],
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(self.url, json=body, headers={"Authorization": f"Bearer {settings.email_api_key}"})
        except httpx.HTTPError as exc:
            return DeliveryResult(False, self.name, error=f"Network error: {type(exc).__name__}")
        if resp.status_code in (200, 202):
            return DeliveryResult(True, self.name, resp.headers.get("X-Message-Id"))
        retryable = resp.status_code >= 500 or resp.status_code == 429
        return DeliveryResult(False, self.name, error=f"SendGrid responded {resp.status_code}", retryable=retryable)


def get_email_provider() -> EmailProvider:
    if settings.email_mock_mode or settings.email_provider == "mock":
        return MockEmailProvider()
    if settings.email_provider == "sendgrid":
        return SendGridEmailProvider()
    return SmtpEmailProvider()


def render_invitation(content: InvitationContent) -> tuple:
    """Return (subject, html, text). All user values are HTML-escaped."""
    e = {k: html.escape(str(v or "")) for k, v in content.__dict__.items()}
    subject = f"You're invited: {content.label}"
    if content.join_url:
        cta = (
            f'<a href="{e["join_url"]}" style="display:inline-block;background:#F97316;color:#ffffff;'
            f'text-decoration:none;font-weight:600;padding:12px 28px;border-radius:8px;">Join Meeting</a>'
        )
        link_text = f"Join the meeting: {content.join_url}"
    else:
        cta = (
            '<p style="margin:0;color:#475569;font-size:14px;">Your personal joining link has been sent '
            f'to <strong>{e["lead_email"]}</strong> in a separate email from Classify.</p>'
        )
        link_text = f"Your joining link has been sent to {content.lead_email} in a separate email from Classify."

    row = (
        '<tr><td style="padding:6px 0;color:#64748B;font-size:13px;width:90px;">{k}</td>'
        '<td style="padding:6px 0;color:#0F172A;font-size:14px;font-weight:600;">{v}</td></tr>'
    )
    html_body = f"""<!doctype html>
<html><body style="margin:0;background:#F8FAFC;font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:14px;border:1px solid #E2E8F0;overflow:hidden;">
<tr><td style="background:#0F172A;padding:20px 28px;"><span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.2px;">Dora</span><span style="color:#F97316;font-size:18px;font-weight:700;"> X </span><span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.2px;">Classify</span></td></tr>
<tr><td style="padding:28px;">
<h1 style="margin:0 0 12px;font-size:22px;color:#0F172A;">You're Invited to a Sales Discussion</h1>
<p style="margin:0 0 6px;color:#334155;font-size:15px;">Hi {e["lead_name"]},</p>
<p style="margin:0 0 20px;color:#334155;font-size:15px;">Your meeting with <strong>{e["sales_person"]}</strong> has been scheduled.</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:#FFF7ED;border:1px solid #FED7AA;border-radius:10px;padding:14px 18px;margin-bottom:24px;">
{row.format(k="Date", v=e["date_text"])}
{row.format(k="Time", v=e["time_text"])}
{row.format(k="Duration", v=e["duration_text"])}
</table>
<div style="text-align:center;margin-bottom:24px;">{cta}</div>
<p style="margin:0;color:#334155;font-size:15px;">We look forward to speaking with you.</p>
</td></tr>
<tr><td style="padding:16px 28px;border-top:1px solid #E2E8F0;color:#94A3B8;font-size:12px;">Dora X Classify · Sales meetings powered by Classify</td></tr>
</table></td></tr></table></body></html>"""

    text_body = (
        f"You're Invited to a Sales Discussion\n\nHi {content.lead_name},\n\n"
        f"Your meeting with {content.sales_person} has been scheduled.\n\n"
        f"Date: {content.date_text}\nTime: {content.time_text}\nDuration: {content.duration_text}\n\n"
        f"{link_text}\n\nWe look forward to speaking with you.\n\nDora X Classify"
    )
    return subject, html_body, text_body


async def send_meeting_invitation(content: InvitationContent) -> DeliveryResult:
    provider = get_email_provider()
    subject, html_body, text_body = render_invitation(content)
    result = await provider.send(content.lead_email, subject, html_body, text_body)
    if not result.success:
        logger.warning("email.send_failed", extra={"provider": provider.name, "error": result.error})
    return result
