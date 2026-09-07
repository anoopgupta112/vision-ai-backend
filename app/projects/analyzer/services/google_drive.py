import os
import io
import json
import logging
from typing import Optional, Dict, Any, Union, List
from datetime import datetime
from bson import ObjectId

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

from app.core.database import get_database

logger = logging.getLogger(__name__)

# Scopes for Google Drive Vault operations and user authentication
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

VAULT_ROOT_NAME = "LeadsPro Cloud Vault"


def _get_client_config() -> Dict[str, Any]:
    """Builds the Google OAuth client config dictionary from environment variables."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("GOOGLE_DRIVE_REDIRECT_URI", "http://localhost:8000/api/drive/callback").strip()

    if not client_id or not client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured in environment variables.")

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def get_authorization_url(user_id: str) -> str:
    """Generates the Google OAuth 2.0 authorization URL for a user."""
    client_config = _get_client_config()
    redirect_uri = os.getenv("GOOGLE_DRIVE_REDIRECT_URI", "http://localhost:8000/api/drive/callback").strip()

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=user_id,
    )

    # Persist PKCE code_verifier so the callback can successfully fetch the token
    if flow.code_verifier:
        db = get_database()
        try:
            db.system_settings.update_one(
                {"key": f"oauth_verifier_{user_id}"},
                {"$set": {"verifier": flow.code_verifier, "created_at": datetime.utcnow()}},
                upsert=True,
            )
        except Exception as exc:
            logger.warning("Could not persist oauth code_verifier: %s", exc)

    return auth_url


def exchange_code_for_tokens(user_id: str, code: str) -> Dict[str, Any]:
    """Exchanges authorization code for tokens and saves them in system settings and user doc."""
    client_config = _get_client_config()
    redirect_uri = os.getenv("GOOGLE_DRIVE_REDIRECT_URI", "http://localhost:8000/api/drive/callback").strip()

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    db = get_database()
    code_verifier = None
    try:
        verifier_doc = db.system_settings.find_one({"key": f"oauth_verifier_{user_id}"})
        if verifier_doc and verifier_doc.get("verifier"):
            code_verifier = verifier_doc["verifier"]
            db.system_settings.delete_one({"key": f"oauth_verifier_{user_id}"})
    except Exception as exc:
        logger.warning("Could not retrieve oauth code_verifier: %s", exc)

    if code_verifier:
        flow.fetch_token(code=code, code_verifier=code_verifier)
    else:
        try:
            flow.fetch_token(code=code)
        except Exception:
            flow.fetch_token(code=code, code_verifier=flow.code_verifier)

    credentials = flow.credentials

    # Fetch user profile from token
    user_email = ""
    try:
        oauth2_service = build("oauth2", "v2", credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        user_email = user_info.get("email", "")
    except Exception as exc:
        logger.warning("Could not fetch user profile during OAuth token exchange: %s", exc)

    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "email": user_email,
        "connected_at": datetime.utcnow().isoformat(),
    }

    db = get_database()
    # 1. Save system-wide in system_settings so ALL users and forms use this vault
    try:
        db.system_settings.update_one(
            {"key": "master_google_drive"},
            {"$set": token_data},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("Could not save to system_settings: %s", exc)

    # 2. Also save to user doc
    try:
        oid = ObjectId(user_id)
        db.users.update_one({"_id": oid}, {"$set": {"google_drive": token_data}})
    except Exception:
        db.users.update_one({"id": user_id}, {"$set": {"google_drive": token_data}})

    logger.info("Successfully configured Master Google Drive Vault for account: %s", user_email)
    return token_data


def get_drive_status(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns the system-wide Master Google Drive Vault status.
    If connected, all users see the vault as active.
    """
    db = get_database()
    
    # 1. Check system_settings
    try:
        setting = db.system_settings.find_one({"key": "master_google_drive"})
        if setting and setting.get("refresh_token"):
            return {
                "connected": True,
                "email": setting.get("email"),
                "connected_at": setting.get("connected_at"),
                "is_system_vault": True,
            }
    except Exception as exc:
        logger.debug("Error querying system_settings for drive status: %s", exc)

    # 2. Check users collection
    try:
        user_doc = db.users.find_one({"google_drive.refresh_token": {"$exists": True}})
        if user_doc and user_doc.get("google_drive"):
            gd_data = user_doc["google_drive"]
            return {
                "connected": True,
                "email": gd_data.get("email"),
                "connected_at": gd_data.get("connected_at"),
                "is_system_vault": True,
            }
    except Exception as exc:
        logger.debug("Error querying users for drive status: %s", exc)

    return {"connected": False}


def disconnect_drive(user_id: Optional[str] = None) -> bool:
    """Removes stored Master Google Drive credentials from system settings and user doc."""
    db = get_database()
    try:
        db.system_settings.delete_one({"key": "master_google_drive"})
        db.users.update_many({"google_drive": {"$exists": True}}, {"$unset": {"google_drive": ""}})
        return True
    except Exception as exc:
        logger.error("Error disconnecting drive: %s", exc)
        return False


def get_master_credentials() -> Optional[Credentials]:
    """
    Retrieves and refreshes Google credentials for the Master Vault.
    1. Checks system_settings collection
    2. Checks DB users collection
    3. Falls back to service account key file
    """
    master_email = os.getenv("GOOGLE_MASTER_DRIVE_EMAIL", "").strip().lower()
    db = get_database()

    # 1. Check system_settings collection (Primary System Master Vault)
    try:
        setting = db.system_settings.find_one({"key": "master_google_drive"})
        if setting and setting.get("refresh_token"):
            creds = Credentials(
                token=setting.get("token"),
                refresh_token=setting.get("refresh_token"),
                token_uri=setting.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=setting.get("client_id", os.getenv("GOOGLE_CLIENT_ID")),
                client_secret=setting.get("client_secret", os.getenv("GOOGLE_CLIENT_SECRET")),
                scopes=SCOPES,
            )
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    db.system_settings.update_one(
                        {"key": "master_google_drive"},
                        {"$set": {"token": creds.token}},
                    )
                except RefreshError as r_err:
                    logger.warning("Revoked Master OAuth token ('invalid_grant'). Purging: %s", r_err)
                    db.system_settings.delete_one({"key": "master_google_drive"})
                    creds = None
                except Exception as exc:
                    logger.warning("Failed refreshing Master Vault OAuth token: %s", exc)
                    creds = None

            if creds and not creds.expired:
                return creds
    except Exception as exc:
        logger.debug("Could not read system_settings for master creds: %s", exc)

    # 2. Check users collection
    try:
        user_doc = None
        if master_email:
            query = {
                "$and": [
                    {"google_drive.refresh_token": {"$exists": True}},
                    {"$or": [
                        {"email": master_email},
                        {"google_drive.email": master_email},
                    ]}
                ]
            }
            user_doc = db.users.find_one(query)

        if not user_doc:
            user_doc = db.users.find_one({"google_drive.refresh_token": {"$exists": True}})

        if user_doc and user_doc.get("google_drive"):
            data = user_doc["google_drive"]
            creds = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data.get("client_id", os.getenv("GOOGLE_CLIENT_ID")),
                client_secret=data.get("client_secret", os.getenv("GOOGLE_CLIENT_SECRET")),
                scopes=SCOPES,
            )
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    db.users.update_one(
                        {"_id": user_doc["_id"]},
                        {"$set": {"google_drive.token": creds.token}},
                    )
                except RefreshError as r_err:
                    logger.warning("Revoked user OAuth token. Clearing: %s", r_err)
                    db.users.update_one(
                        {"_id": user_doc["_id"]},
                        {"$unset": {"google_drive": ""}},
                    )
                    creds = None
                except Exception as exc:
                    logger.warning("Failed refreshing user OAuth token: %s", exc)
                    creds = None

            if creds and not creds.expired:
                return creds
    except Exception as exc:
        logger.debug("Could not read user OAuth token from DB: %s", exc)

    # 2. Check service account credentials
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if os.path.exists(sa_file):
        try:
            return service_account.Credentials.from_service_account_file(sa_file, scopes=SCOPES)
        except Exception as exc:
            logger.warning("Failed loading service account file: %s", exc)

    return None


def get_master_drive_service():
    """Returns an authorized Google Drive v3 resource."""
    creds = get_master_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)


def ensure_folder(service, parent_id: Optional[str], folder_name: str) -> str:
    """Finds or creates a folder in Google Drive by name under parent_id."""
    query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{folder_name}' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    response = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    files = response.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    created = service.files().create(
        body=metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


def ensure_vault_form_structure(
    form_id: str,
    form_title: Optional[str] = None,
    client_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ensures the hierarchical folder structure exists in the Google Drive Master Vault:
    VisionAI Master Vault / [Client / Organization] / [Form Title] /
        ├── Resumes/       (Candidate PDF resumes)
        └── Excel_Reports/ (Candidate intelligence & evaluation spreadsheets)
    """
    service = get_master_drive_service()
    if not service:
        raise RuntimeError("Master Google Drive Vault is not connected. Please authorize the Master Vault account first.")

    # 1. Master Root Vault
    root_id = ensure_folder(service, None, VAULT_ROOT_NAME)

    # 2. Client / Organization Workspace Folder
    clean_client = (client_name or "General Workspace").strip()
    client_folder_id = ensure_folder(service, root_id, clean_client)

    # 3. Specific Form / Job Role Folder
    title = (form_title.strip() if form_title else f"Form {form_id}")
    form_folder_id = ensure_folder(service, client_folder_id, title)

    # 4. Separated Sub-Folders: Resumes and Excel Reports
    resumes_folder_id = ensure_folder(service, form_folder_id, "Resumes")
    excel_folder_id = ensure_folder(service, form_folder_id, "Excel_Reports")

    folder_url = f"https://drive.google.com/drive/folders/{form_folder_id}"
    client_folder_url = f"https://drive.google.com/drive/folders/{client_folder_id}"

    return {
        "root_id": root_id,
        "client_folder_id": client_folder_id,
        "client_folder_url": client_folder_url,
        "form_folder_id": form_folder_id,
        "resumes_folder_id": resumes_folder_id,
        "excel_folder_id": excel_folder_id,
        "folder_url": folder_url,
    }


def upload_resume_stream(
    resumes_folder_id: str,
    file_bytes: bytes,
    original_filename: str,
    candidate_name: str,
) -> Dict[str, Any]:
    """
    Uploads a candidate resume PDF directly from in-memory bytes to Google Drive.
    Uses zero VPS disk space.
    """
    service = get_master_drive_service()
    if not service:
        raise RuntimeError("Master Google Drive Vault is not connected.")

    display_name = f"{candidate_name.strip() or 'Candidate'} - {original_filename}"
    file_metadata = {
        "name": display_name,
        "parents": [resumes_folder_id],
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype="application/pdf",
        resumable=True,
    )

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink, webContentLink",
        supportsAllDrives=True,
    ).execute()

    return {
        "file_id": uploaded.get("id"),
        "file_name": uploaded.get("name"),
        "web_view_link": uploaded.get("webViewLink"),
        "web_content_link": uploaded.get("webContentLink"),
    }


def download_file_bytes(file_id: str) -> bytes:
    """
    Streams a file's content directly into memory from Google Drive.
    Uses zero VPS disk space.
    """
    service = get_master_drive_service()
    if not service:
        raise RuntimeError("Master Google Drive Vault is not connected.")

    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    return fh.getvalue()


def sync_excel_stream(
    target_folder_id: str,
    excel_bytes: bytes,
    form_title: Optional[str] = None,
) -> Optional[str]:
    """
    Uploads or updates the live submissions spreadsheet in the Excel_Reports folder from in-memory bytes.
    """
    service = get_master_drive_service()
    if not service:
        return None

    spreadsheet_name = f"{(form_title or 'Submissions').strip()}_Submissions.xlsx"
    query = f"'{target_folder_id}' in parents and name = '{spreadsheet_name}' and trashed = false"

    response = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    media = MediaIoBaseUpload(
        io.BytesIO(excel_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=True,
    )

    files = response.get("files", [])
    if files:
        file_id = files[0]["id"]
        updated = service.files().update(
            fileId=file_id,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return updated.get("webViewLink")
    else:
        file_metadata = {
            "name": spreadsheet_name,
            "parents": [target_folder_id],
        }
        created = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        ).execute()
        return created.get("webViewLink")


def share_folder_with_email(
    form_folder_id: str,
    email_address: str,
    role: str = "writer",
    send_notification: bool = True,
) -> Dict[str, Any]:
    """
    Programmatically shares the form's Google Drive folder with the recruiter's email
    using Google Drive's permissions API. Zero OAuth login required for recruiter.
    """
    service = get_master_drive_service()
    if not service:
        raise RuntimeError("Master Google Drive Vault is not connected. Please authorize the Master Vault account first.")

    email = email_address.strip().lower()
    permission_body = {
        "type": "user",
        "role": role,  # "writer" (editor) or "reader" (view only)
        "emailAddress": email,
    }

    try:
        created_perm = service.permissions().create(
            fileId=form_folder_id,
            body=permission_body,
            fields="id",
            sendNotificationEmail=send_notification,
            supportsAllDrives=True,
        ).execute()

        folder_info = service.files().get(
            fileId=form_folder_id,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()

        return {
            "success": True,
            "email": email,
            "permission_id": created_perm.get("id"),
            "folder_id": form_folder_id,
            "folder_name": folder_info.get("name"),
            "folder_link": folder_info.get("webViewLink"),
        }
    except Exception as exc:
        logger.error("Failed sharing Google Drive folder %s with %s: %s", form_folder_id, email, exc)
        raise exc
