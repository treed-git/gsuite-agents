"""OAuth2 authentication for Google Drive API."""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def get_drive_service():
    """Authenticate and return a Google Drive API service object.

    On first run, opens a browser window for OAuth consent.
    Subsequent runs use the cached token.json automatically.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def is_authenticated():
    """Return True if valid credentials exist (setup has been done)."""
    if not os.path.exists(CREDENTIALS_FILE):
        return False
    if not os.path.exists(TOKEN_FILE):
        return False
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        return creds and (creds.valid or (creds.expired and creds.refresh_token))
    except Exception:
        return False
