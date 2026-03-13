"""Claude agentic loop for Google Drive file organization."""

import os
import anthropic

from gdrive import list_files, list_folders, get_file_snippet
from tools import ProposalTracker, TOOL_SCHEMAS

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a Google Drive file organizer assistant. Your job is to help the user keep their Drive tidy by suggesting better file names and grouping files into logical folders.

## Your workflow
1. Call `list_drive_files` to see what files exist.
2. Call `list_folders` to see what folders already exist.
3. For files with unclear names (e.g. "Untitled document", "Document1", generic names), call `get_file_snippet` to peek at the content and understand what the file is about.
4. For each file that needs improvement:
   - Call `propose_rename` if the name is unclear, generic, or unhelpful.
   - Call `propose_move` to assign it to a relevant folder (existing or new).
   - Call `propose_create_folder` first if the folder doesn't exist yet.
5. When you've reviewed every file, call `finish_planning`.

## Important rules
- NEVER modify file contents — only rename and move.
- NEVER delete files.
- If a file already has a clear, descriptive name and is in a sensible location, leave it alone. Don't propose unnecessary changes.
- For non-Google files (PDFs, images, .docx, etc.), always keep the file extension when renaming (e.g. "invoice_march.pdf" → "Invoice March 2024.pdf").
- For Google Workspace files (Docs, Sheets, Slides), do NOT add an extension.
- Before proposing to create a folder, check `list_folders` — reuse an existing folder if one already fits.
- Use placeholder IDs from `propose_create_folder` (e.g. "new:Invoices") when calling `propose_move` for a folder you just proposed.
- Be thoughtful and conservative: a few well-chosen folders are better than many tiny ones.
- Think about grouping by topic, project, or file type (e.g. "Invoices", "Photos", "Work Projects", "Personal").
"""


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
        response = client.messages.create(
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
                size = f.get("size", "")
                size_str = f" ({int(size):,} bytes)" if size else ""
                lines.append(
                    f"- id={f['id']} | name=\"{f['name']}\" | type={f['mimeType']}"
                    f" | created={f.get('createdTime','?')} | modified={f.get('modifiedTime','?')}{size_str}"
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
