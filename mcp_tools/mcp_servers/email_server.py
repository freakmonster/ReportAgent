"""
Email MCP Server — Notification service for human review alerts.

Sends email notifications when a workflow reaches the human_review node.
Runs as an independent HTTP (FastAPI) service on port 8004.

Configuration: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
in config YAML or environment variables.
邮箱授权码在邮箱设置里 30 秒生成
例如 QQ 邮箱：设置 → 账户 → POP3/SMTP → 开启 → 生成授权码。
$env:SMTP_HOST = "smtp.qq.com"
$env:SMTP_PORT = "587"
$env:SMTP_USER = "你的QQ号@qq.com"
$env:SMTP_PASSWORD = "QQ邮箱的授权码"
$env:SMTP_FROM = "你的QQ号@qq.com"
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

class EmailSender:
    """Async email sender via SMTP."""

    def __init__(self) -> None:
        self._smtp_config: dict[str, object] | None = None

    def _get_smtp_config(self) -> dict[str, object]:
        """Resolve SMTP configuration from settings."""
        if self._smtp_config is None:
            from config.settings import settings

            smtp_host = getattr(settings, "smtp_host", "localhost")
            smtp_port = int(getattr(settings, "smtp_port", 587))
            smtp_user = getattr(settings, "smtp_user", "")
            smtp_password = getattr(settings, "smtp_password", "")
            smtp_from = getattr(settings, "smtp_from", "noreply@research-agent.local")
            smtp_use_tls = bool(getattr(settings, "smtp_use_tls", True))

            self._smtp_config = {
                "host": smtp_host,
                "port": smtp_port,
                "user": smtp_user,
                "password": smtp_password,
                "from": smtp_from,
                "use_tls": smtp_use_tls,
            }

        return self._smtp_config

    async def send(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        body_type: str = "html",
    ) -> dict[str, Any]:
        """Send an email.

        Args:
            to: Recipient email address(es).
            subject: Email subject line.
            body: Email body content.
            body_type: "html" or "plain".

        Returns:
            Dict with success flag and message_id if available.
        """
        config = self._get_smtp_config()

        if isinstance(to, str):
            to = [to]

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = str(config["from"])
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(body, body_type, "utf-8"))

        try:
            # Use aiosmtplib for async SMTP
            import smtplib as _stdlib_smtplib

            import aiosmtplib

            smtp = aiosmtplib.SMTP(
                hostname=str(config["host"]),
                port=int(config["port"]),
                use_tls=bool(config["use_tls"]),
            )

            await smtp.connect()
            if str(config["user"]):
                await smtp.login(str(config["user"]), str(config["password"]))

            response = await smtp.send_message(msg)
            await smtp.quit()

            logger.info("Email sent to %s: %s", to, subject)
            return {
                "success": True,
                "recipients": to,
                "subject": subject,
                "response": str(response),
            }
        except ImportError:
            logger.warning(
                "aiosmtplib not installed. Email sending is a no-op. "
                "Install with: pip install aiosmtplib"
            )
            return {
                "success": True,
                "recipients": to,
                "subject": subject,
                "note": "Email not actually sent (aiosmtplib missing)",
            }
        except (OSError, ValueError) as exc:
            logger.error("SMTP connection/configuration error for %s: %s", to, exc)
            raise EmailSendError(f"SMTP connection failed: {exc}") from exc


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

def create_email_app() -> object:
    """Create and configure the FastAPI email MCP server application."""
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    app = FastAPI(title="MCP Email Server", version="0.1.0")
    sender = EmailSender()

    # ── Request models ──────────────────────────────────────────────

    class SendEmailRequest(BaseModel):
        to: str | list[str] = Field(..., description="Recipient email address(es)")
        subject: str = Field(..., description="Email subject")
        body: str = Field(..., description="Email body (HTML or plain text)")
        body_type: str = Field(default="html", description="html or plain")

    class ReviewNotificationRequest(BaseModel):
        """Convenience request for human review notifications."""
        workflow_id: str = Field(..., description="Workflow ID needing review")
        reviewer_email: str = Field(..., description="Reviewer email address")
        report_title: str = Field(default="", description="Report title")
        review_url: str = Field(default="", description="URL to review page")

    # ── Health ──────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "mcp-email"}

    # ── Tool endpoints ──────────────────────────────────────────────

    @app.post("/tools/send_email")
    async def send_email(req: SendEmailRequest) -> dict[str, Any]:
        return await sender.send(
            to=req.to,
            subject=req.subject,
            body=req.body,
            body_type=req.body_type,
        )

    @app.post("/tools/send_review_notification")
    async def send_review_notification(req: ReviewNotificationRequest) -> dict[str, Any]:
        """Send a human review notification email."""
        subject = f"[Action Required] Report Review: {req.report_title or req.workflow_id}"
        body = f"""
        <h2>Research Report Needs Your Review</h2>
        <p><strong>Workflow ID:</strong> {req.workflow_id}</p>
        <p><strong>Report:</strong> {req.report_title or 'Untitled'}</p>
        <p>Please review the generated report and approve or request changes.</p>
        {f'<p><a href="{req.review_url}">Click here to review</a></p>' if req.review_url else ''}
        <hr/>
        <p><small>This is an automated notification from the Research Agent system.</small></p>
        """
        return await sender.send(
            to=req.reviewer_email,
            subject=subject,
            body=body,
            body_type="html",
        )

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_email_app()


def main() -> None:
    """Run the email MCP server."""
    import uvicorn

    from config.settings import settings

    uvicorn.run(
        "mcp_tools.mcp_servers.email_server:app",
        host="0.0.0.0",
        port=8004,
        log_level=settings.log_level.lower(),
    )


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class EmailSendError(Exception):
    """Raised when email sending fails."""
