"""
Email utility — sends HTML emails via Gmail SMTP.
Credentials stored as GitHub Secrets: GMAIL_ADDRESS, GMAIL_APP_PASSWORD
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

RECIPIENT = "muneebnaseem786@gmail.com"


def send_email(subject: str, html_body: str) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, RECIPIENT, msg.as_string())

    print(f"Email sent: {subject}")
