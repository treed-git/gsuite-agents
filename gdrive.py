"""Google Drive API wrapper — read and organize files without modifying content."""

import io

GOOGLE_WORKSPACE_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

FOLDER_MIME = "application/vnd.google-apps.folder"


def list_files(service, folder_id=None):
    """List all non-folder files. If folder_id is given, only files directly in that folder.
    Otherwise lists all files in My Drive that are not in any folder (top-level files).

    Returns list of dicts: {id, name, mimeType, parents}
    """
    if folder_id:
        query = f"'{folder_id}' in parents and mimeType != '{FOLDER_MIME}' and trashed = false"
    else:
        query = f"mimeType != '{FOLDER_MIME}' and trashed = false"

    results = []
    page_token = None
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, parents)",
            pageToken=page_token,
            pageSize=100,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def list_folders(service, parent_id=None):
    """List all folders. If parent_id is given, only direct children of that folder.
    Otherwise lists all folders in My Drive.

    Returns list of dicts: {id, name, parents}
    """
    if parent_id:
        query = f"'{parent_id}' in parents and mimeType = '{FOLDER_MIME}' and trashed = false"
    else:
        query = f"mimeType = '{FOLDER_MIME}' and trashed = false"

    results = []
    page_token = None
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, parents)",
            pageToken=page_token,
            pageSize=100,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def get_file_snippet(service, file_id, mime_type, max_chars=200):
    """Return a short text preview of a file's content.

    Works for Google Docs, Sheets, and Slides. Returns '[no preview available]'
    for binary files (images, PDFs, etc.).
    """
    export_mime = GOOGLE_WORKSPACE_MIME_TYPES.get(mime_type)
    if not export_mime:
        return "[no preview available]"

    try:
        data = service.files().export_media(fileId=file_id, mimeType=export_mime).execute()
        text = data.decode("utf-8", errors="replace").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text or "[empty file]"
    except Exception as e:
        return f"[could not read preview: {e}]"


def rename_file(service, file_id, new_name):
    """Rename a file. Does not affect content."""
    service.files().update(fileId=file_id, body={"name": new_name}).execute()


def move_file(service, file_id, new_parent_id, current_parent_id):
    """Move a file to a different folder."""
    service.files().update(
        fileId=file_id,
        addParents=new_parent_id,
        removeParents=current_parent_id,
        fields="id, parents",
    ).execute()


def create_folder(service, name, parent_id=None):
    """Create a new folder. Returns the new folder's ID."""
    metadata = {
        "name": name,
        "mimeType": FOLDER_MIME,
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]
