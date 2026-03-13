"""Claude agentic loop for Google Drive file organization."""

import os
import time
import anthropic

from gdrive import list_files, list_folders, get_file_snippet
from tools import ProposalTracker, TOOL_SCHEMAS

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a Google Drive file organizer. Your job is to evaluate the user's entire Drive and produce an optimal, clean folder structure — then move every file to its best location.

## Your workflow
1. Call `list_folders` first so folder names are available when you list files.
2. Call `list_drive_files` (no folder_id) to see all files and where they currently live. Each file shows its current location (folder name or "root").
3. Evaluate the existing structure: are folders well-named? are files in the right place? are any folders too broad, too narrow, or redundant?
4. For files whose content is unclear from the name alone, call `get_file_snippet`.
5. Propose an improved structure:
   - Call `propose_create_folder` for any new folders needed.
   - Call `propose_rename` for files with unclear or generic names.
   - Call `propose_move` for every file that belongs in a different (or better) folder — this includes files already in sub-folders if a better home exists.
6. Call `finish_planning` when every file has been reviewed.

## Rules
- NEVER modify file contents — only rename and move.
- NEVER delete files.
- Files at the root (location=root) are a problem to fix. Move them to an appropriate folder if one exists or can be created. Only leave a file at root if genuinely no folder fits.
- It is fine to move a file that is already in a sub-folder if a better folder exists.
- Rename only when the current name is unclear or generic (e.g. "Untitled", "Document1"). A good name is already good — don't change it for style.
- For non-Google files (PDFs, images, .docx, etc.) preserve the file extension when renaming.
- For Google Workspace files (Docs, Sheets, Slides) do NOT add an extension.
- Prefer a few well-chosen folders over many tiny ones. Group by topic, project, or type (e.g. "Invoices", "Photos", "Work Projects", "Personal").
- Before creating a folder, check `list_folders` — reuse an existing folder if it fits.
- Use placeholder IDs from `propose_create_folder` (e.g. "new:Invoices") when calling `propose_move` for a folder you just proposed.
"""


def _create_with_retry(client, **kwargs):
    """Call client.messages.create with exponential backoff on rate limit errors."""
    delay = 60
    for attempt in range(5):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt == 4:
                raise
            print(f"\nRate limit reached — waiting {delay}s before retrying...")
            time.sleep(delay)
            delay = min(delay * 2, 300)


def run_agent(drive_service, tracker: ProposalTracker, folder_id: str | None = None):
    """Run the Claude agent loop until it calls finish_planning().

    Returns (files_by_id, folders_by_id) for use in the dry-run display.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Caches populated as the agent fetches data
    files_by_id: dict = {}
    folders_by_id: dict = {}

    messages = [
        {
            "role": "user",
            "content": "Please review my Google Drive files and propose names and folder organization for them.",
        }
    ]

    while not tracker.done:
        response = _create_with_retry(
            client,
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Agent finished without calling finish_planning — treat as done
            tracker.done = True
            break

        if response.stop_reason != "tool_use":
            break

        # Dispatch tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            result = _dispatch_tool(
                tool_name, tool_input, drive_service, tracker,
                files_by_id, folders_by_id, folder_id
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    return files_by_id, folders_by_id


def _dispatch_tool(name, inputs, service, tracker, files_by_id, folders_by_id, root_folder_id):
    """Route a tool call to the appropriate handler and return a result string."""
    try:
        if name == "list_drive_files":
            fid = inputs.get("folder_id") or root_folder_id
            files = list_files(service, folder_id=fid)
            # Cache for later use
            for f in files:
                files_by_id[f["id"]] = f
            if not files:
                return "No files found."
            lines = []
            for f in files:
                parents = f.get("parents", [])
                parent_id = parents[0] if parents else None
                if parent_id is None or parent_id == "root":
                    location = "root"
                else:
                    location = folders_by_id.get(parent_id, {}).get("name") or parent_id
                lines.append(
                    f"- id={f['id']} | name=\"{f['name']}\" | type={f['mimeType']} | location={location}"
                )
            return "\n".join(lines)

        elif name == "list_folders":
            pid = inputs.get("parent_folder_id")
            folders = list_folders(service, parent_id=pid)
            for fo in folders:
                folders_by_id[fo["id"]] = fo
            if not folders:
                return "No folders found."
            lines = [f"- id={fo['id']} | name=\"{fo['name']}\"" for fo in folders]
            return "\n".join(lines)

        elif name == "get_file_snippet":
            snippet = get_file_snippet(service, inputs["file_id"], inputs["mime_type"])
            return snippet

        elif name == "propose_rename":
            return tracker.propose_rename(inputs["file_id"], inputs["new_name"])

        elif name == "propose_move":
            return tracker.propose_move(inputs["file_id"], inputs["folder_id"])

        elif name == "propose_create_folder":
            return tracker.propose_create_folder(
                inputs["name"], inputs.get("parent_id")
            )

        elif name == "finish_planning":
            return tracker.finish_planning()

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        return f"Error running {name}: {e}"
