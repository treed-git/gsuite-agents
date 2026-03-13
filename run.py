"""Main entry point — run this to organize your Google Drive."""

import json
import os
import sys
import argparse

from dotenv import load_dotenv

CACHE_FILE = ".gdrive_cache.json"


def _drive_snapshot(service, folder_id):
    """Return a snapshot of the current Drive state for cache comparison."""
    from gdrive import list_files, list_folders
    files = list_files(service, folder_id=folder_id)
    folders = list_folders(service)
    # Normalise to sorted lists of (id, name, parents) tuples for stable comparison
    file_snap = sorted(
        [(f["id"], f["name"], sorted(f.get("parents") or [])) for f in files]
    )
    folder_snap = sorted(
        [(fo["id"], fo["name"], sorted(fo.get("parents") or [])) for fo in folders]
    )
    return {"files": file_snap, "folders": folder_snap}


def load_analysis_cache(service, folder_id):
    """Return (tracker, files_by_id, folders_by_id) from cache if Drive is unchanged, else None."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        current = _drive_snapshot(service, folder_id)
        if current != data["snapshot"]:
            return None
        from tools import ProposalTracker
        tracker = ProposalTracker()
        tracker.renames = data["proposals"]["renames"]
        tracker.moves = data["proposals"]["moves"]
        tracker.new_folders = data["proposals"]["new_folders"]
        tracker.done = True
        return tracker, data["files_by_id"], data["folders_by_id"]
    except Exception:
        return None


def save_analysis_cache(tracker, files_by_id, folders_by_id, snapshot):
    """Write proposals and Drive snapshot to CACHE_FILE."""
    data = {
        "snapshot": snapshot,
        "proposals": {
            "renames": tracker.renames,
            "moves": tracker.moves,
            "new_folders": tracker.new_folders,
        },
        "files_by_id": files_by_id,
        "folders_by_id": folders_by_id,
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


def clear_analysis_cache():
    """Delete the analysis cache file if it exists."""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)


def check_setup():
    """Check that the required setup has been done. Exit with a helpful message if not."""
    missing = []

    if not os.path.exists("credentials.json"):
        missing.append("credentials.json (Google Drive credentials)")

    if not os.getenv("ANTHROPIC_API_KEY"):
        if os.path.exists(".env"):
            load_dotenv()
        if not os.getenv("ANTHROPIC_API_KEY"):
            missing.append("ANTHROPIC_API_KEY (in .env file)")

    if missing:
        print("\nSetup is not complete. The following are missing:")
        for m in missing:
            print(f"  - {m}")
        print("\nRun this first:  python setup_wizard.py\n")
        sys.exit(1)


def apply_changes(service, tracker, files_by_id, folders_by_id):
    """Apply all proposed changes: create folders, rename files, move files."""
    from gdrive import create_folder, rename_file, move_file
    from googleapiclient.errors import HttpError

    # Step 1: Create new folders, building a map from placeholder → real ID
    placeholder_to_real: dict[str, str] = {}

    for folder_spec in tracker.new_folders:
        placeholder = folder_spec["placeholder_id"]
        name = folder_spec["name"]
        parent_id = folder_spec.get("parent_id")

        # Resolve parent if it's also a placeholder
        if parent_id and parent_id in placeholder_to_real:
            parent_id = placeholder_to_real[parent_id]

        real_id = create_folder(service, name, parent_id)
        placeholder_to_real[placeholder] = real_id
        folders_by_id[real_id] = {"id": real_id, "name": name}
        print(f"  Created folder: {name}")

    # Step 2: Rename files
    for file_id, new_name in tracker.renames.items():
        old_name = files_by_id.get(file_id, {}).get("name", file_id)
        try:
            rename_file(service, file_id, new_name)
            print(f"  Renamed: \"{old_name}\" → \"{new_name}\"")
            if file_id in files_by_id:
                files_by_id[file_id]["name"] = new_name
        except HttpError as e:
            if e.resp.status == 403:
                print(f"  Skipped rename: \"{old_name}\" (no permission)")
            else:
                raise

    # Step 3: Move files
    for file_id, folder_id in tracker.moves.items():
        # Resolve placeholder folder IDs to real IDs
        real_folder_id = placeholder_to_real.get(folder_id, folder_id)

        file_info = files_by_id.get(file_id, {})
        file_name = file_info.get("name", file_id)
        folder_name = folders_by_id.get(real_folder_id, {}).get("name", real_folder_id)

        # Get current parent
        parents = file_info.get("parents", [])
        current_parent = parents[0] if parents else "root"

        try:
            move_file(service, file_id, real_folder_id, current_parent)
            print(f"  Moved: \"{file_name}\" → \U0001f4c1 {folder_name}")
        except HttpError as e:
            if e.resp.status == 403:
                print(f"  Skipped move: \"{file_name}\" (no permission)")
            else:
                raise


def main():
    parser = argparse.ArgumentParser(description="Google Drive File Organizer")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes without asking for confirmation (for automated/scheduled runs)",
    )
    parser.add_argument(
        "--folder-id",
        default=None,
        help="Only organize files within this specific Drive folder ID",
    )
    args = parser.parse_args()

    # Load env and verify setup
    load_dotenv()
    check_setup()

    # Late imports (after env is loaded and setup verified)
    from auth import get_drive_service
    from agent import run_agent
    from tools import ProposalTracker

    folder_id = args.folder_id or os.getenv("GDRIVE_FOLDER_ID")

    print("\n=== Google Drive Organizer ===\n")
    print("Scanning your Drive for files to organize...")

    service = get_drive_service()
    tracker = ProposalTracker()

    cached = load_analysis_cache(service, folder_id)
    if cached:
        print("Drive unchanged — using cached analysis.\n")
        tracker, files_by_id, folders_by_id = cached
    else:
        print("Analyzing files with AI...\n")
        snapshot = _drive_snapshot(service, folder_id)
        files_by_id, folders_by_id = run_agent(service, tracker, folder_id=folder_id)
        save_analysis_cache(tracker, files_by_id, folders_by_id, snapshot)

    if not tracker.has_changes():
        print("Your Drive looks organized! Nothing to do.")
        return

    # Show dry-run plan
    print("Proposed changes:")
    print(tracker.render_plan(files_by_id, folders_by_id))
    print()

    n = tracker.count_changes()
    label = f"{n} change{'s' if n != 1 else ''}"

    if args.apply:
        print(f"Applying {label} (--apply flag set)...\n")
        apply_changes(service, tracker, files_by_id, folders_by_id)
        clear_analysis_cache()
        print(f"\nDone! {label} applied to your Google Drive.")
    else:
        answer = input(f"Apply these {label}? [y/N] ")
        if answer.strip().lower() == "y":
            print()
            apply_changes(service, tracker, files_by_id, folders_by_id)
            clear_analysis_cache()
            print(f"\nDone! {label} applied to your Google Drive.")
        else:
            print("\nAborted. No changes were made.")


if __name__ == "__main__":
    main()
