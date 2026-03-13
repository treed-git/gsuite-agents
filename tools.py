"""Tool definitions and proposal tracker for the Drive organizer agent."""

import uuid


# ── Proposal Tracker ──────────────────────────────────────────────────────────

class ProposalTracker:
    """Collects rename/move/folder-creation proposals from the agent.
    No changes are applied until the user confirms after reviewing the plan.
    """

    def __init__(self):
        self.renames: dict[str, str] = {}          # file_id → new_name
        self.moves: dict[str, str] = {}             # file_id → folder_id (real or placeholder)
        self.new_folders: list[dict] = []           # [{placeholder_id, name, parent_id}]
        self.done: bool = False

    # ── Tool handlers (called by agent.py when Claude invokes a tool) ─────────

    def propose_rename(self, file_id: str, new_name: str) -> str:
        self.renames[file_id] = new_name
        return f"Rename recorded: file {file_id} → '{new_name}'"

    def propose_move(self, file_id: str, folder_id: str) -> str:
        self.moves[file_id] = folder_id
        return f"Move recorded: file {file_id} → folder '{folder_id}'"

    def propose_create_folder(self, name: str, parent_id: str | None = None) -> str:
        placeholder_id = f"new:{name}"
        # Avoid duplicates
        for f in self.new_folders:
            if f["name"] == name and f["parent_id"] == parent_id:
                return f"Folder '{name}' already proposed (placeholder: {f['placeholder_id']})"
        self.new_folders.append({
            "placeholder_id": placeholder_id,
            "name": name,
            "parent_id": parent_id,
        })
        return f"New folder '{name}' proposed (placeholder ID: {placeholder_id})"

    def finish_planning(self) -> str:
        self.done = True
        return "Planning complete."

    def has_changes(self) -> bool:
        return bool(self.renames or self.moves or self.new_folders)

    # ── Dry-run display ───────────────────────────────────────────────────────

    def render_plan(self, files_by_id: dict, folders_by_id: dict) -> str:
        """Return a human-readable table of all proposed changes."""
        lines = []
        sep = "─" * 65

        lines.append(sep)

        # New folders
        for f in self.new_folders:
            lines.append(f"  CREATE  \U0001f4c1 {f['name']}")

        # Renames
        for file_id, new_name in self.renames.items():
            old_name = files_by_id.get(file_id, {}).get("name", file_id)
            lines.append(f"  RENAME  \"{old_name}\"  →  \"{new_name}\"")

        # Moves
        for file_id, folder_id in self.moves.items():
            file_name = files_by_id.get(file_id, {}).get("name", file_id)
            # Use proposed new name if also being renamed
            if file_id in self.renames:
                file_name = self.renames[file_id]
            # Resolve folder name
            folder_name = self._resolve_folder_name(folder_id, folders_by_id)
            lines.append(f"  MOVE    \"{file_name}\"  →  \U0001f4c1 {folder_name}")

        lines.append(sep)

        # Count unchanged files
        total_files = len(files_by_id)
        changed_files = len(set(list(self.renames.keys()) + list(self.moves.keys())))
        unchanged = total_files - changed_files
        if unchanged > 0:
            lines.append(f"  ({unchanged} file{'s' if unchanged != 1 else ''} already well-organized — no changes needed)")

        return "\n".join(lines)

    def _resolve_folder_name(self, folder_id: str, folders_by_id: dict) -> str:
        if folder_id.startswith("new:"):
            return folder_id[4:]  # strip "new:" prefix
        folder = folders_by_id.get(folder_id, {})
        return folder.get("name", folder_id)

    def count_changes(self) -> int:
        return len(self.renames) + len(self.moves) + len(self.new_folders)


# ── Claude Tool Schemas ───────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "list_drive_files",
        "description": (
            "List files in Google Drive. Returns id, name, mimeType, and current "
            "location (folder name or 'root'). Call list_folders first so location "
            "names are resolved. If folder_id is provided, lists files in that folder "
            "only. Otherwise lists all files in My Drive including files already in sub-folders."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "Optional folder ID to list files from. Omit to list all Drive files.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "list_folders",
        "description": (
            "List folders in Google Drive. Returns folder id, name, and parent folder ids. "
            "Use this to discover existing folders before proposing moves or creating new folders."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "parent_folder_id": {
                    "type": "string",
                    "description": "Optional parent folder ID to list subfolders from. Omit to list all folders.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_file_snippet",
        "description": (
            "Get a short text preview of a Google Doc, Sheet, or Slide. "
            "Useful for understanding what an ambiguously-named file actually contains. "
            "Returns '[no preview available]' for binary files like images and PDFs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The file's Drive ID."},
                "mime_type": {"type": "string", "description": "The file's mimeType from list_drive_files."},
            },
            "required": ["file_id", "mime_type"],
        },
    },
    {
        "name": "propose_rename",
        "description": (
            "Propose renaming a file to a better, more descriptive name. "
            "For non-Google files (PDFs, images, etc.), preserve the file extension. "
            "For Google Workspace files (Docs, Sheets, Slides), do NOT add an extension. "
            "Only propose a rename if the current name is unclear or unhelpful."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The file's Drive ID."},
                "new_name": {"type": "string", "description": "The proposed new name for the file."},
            },
            "required": ["file_id", "new_name"],
        },
    },
    {
        "name": "propose_move",
        "description": (
            "Propose moving a file into a folder. "
            "Use the folder's real Drive ID (from list_folders) or a placeholder ID "
            "returned by propose_create_folder (e.g. 'new:Invoices'). "
            "Always call list_folders first to check if the folder already exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The file's Drive ID."},
                "folder_id": {
                    "type": "string",
                    "description": "The destination folder's Drive ID, or a placeholder like 'new:Invoices'.",
                },
            },
            "required": ["file_id", "folder_id"],
        },
    },
    {
        "name": "propose_create_folder",
        "description": (
            "Propose creating a new folder to group related files. "
            "Returns a placeholder ID (e.g. 'new:Invoices') that you can use in propose_move. "
            "Always check list_folders first — don't create a folder that already exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name for the new folder."},
                "parent_id": {
                    "type": "string",
                    "description": "Optional parent folder ID. Omit to create at the top level of My Drive.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "finish_planning",
        "description": (
            "Call this when you have finished reviewing all files and recording all proposals. "
            "This ends the planning phase and triggers the dry-run preview for the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]
