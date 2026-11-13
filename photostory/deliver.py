"""Delivery channels. Each channel takes the rendered episode and sends it somewhere.

Email is built in. New channels (e.g. WhatsApp) implement `Channel.send`.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from .config import Config, Secrets
from .models import Episode
from .render import Rendered, cid_for
from .sources.base import Photo


class Channel(Protocol):
    name: str

    def send(self, ep: Episode, rendered: Rendered, photos: list[Photo]) -> None: ...


def build_email(ep: Episode, rendered: Rendered, photos: list[Photo], cfg: Config, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"{cfg.email.subject_prefix}: {ep.title}"
    msg["From"] = sender
    msg["To"] = ", ".join(cfg.email.to)
    msg["Message-ID"] = make_msgid(domain="photostory.local")
    msg.set_content(
        f"{ep.title}\n{ep.tagline}\n\nYour mail app doesn't show HTML — open the attached photostory.html instead.\n\n"
        + rendered.markdown
    )
    msg.add_alternative(rendered.email_html, subtype="html")
    html_part = msg.get_payload()[1]
    for i, p in enumerate(photos, 1):
        html_part.add_related(p.jpeg, maintype="image", subtype="jpeg", cid=f"<{cid_for(i)}>", filename=f"photo{i}.jpg")
    if cfg.email.attach_interactive_page:
        msg.add_attachment(rendered.page_html.encode(), maintype="text", subtype="html", filename="photostory.html")
    return msg


class EmailChannel:
    name = "email"

    def __init__(self, cfg: Config, secrets: Secrets, smtp_factory=smtplib.SMTP):
        if not cfg.email.to:
            raise ValueError("No email recipients: set email.to in config or the EMAIL_TO secret.")
        if not (secrets.smtp_username and secrets.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be set to send email.")
        self.cfg, self.secrets, self.smtp_factory = cfg, secrets, smtp_factory

    def send(self, ep: Episode, rendered: Rendered, photos: list[Photo]) -> None:
        sender = self.cfg.email.from_addr or self.secrets.smtp_username
        msg = build_email(ep, rendered, photos, self.cfg, sender)
        with self.smtp_factory(self.cfg.email.smtp_host, self.cfg.email.smtp_port, timeout=60) as smtp:
            smtp.starttls()
            smtp.login(self.secrets.smtp_username, self.secrets.smtp_password)
            smtp.send_message(msg)


def make_channels(cfg: Config, secrets: Secrets) -> list[Channel]:
    channels: list[Channel] = []
    if cfg.email.enabled:
        channels.append(EmailChannel(cfg, secrets))
    return channels
