"""First-time setup wizard for the Google Drive Organizer."""

import os
import sys
import subprocess


def run():
    print()
    print("=" * 55)
    print("  Google Drive Organizer — First Time Setup")
    print("=" * 55)
    print()

    # ── Step 1: Install dependencies ─────────────────────────
    print("Step 1/3: Install required packages")
    print("  Installing dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"\n  ERROR installing packages:\n{result.stderr}")
        print("  Try running:  pip install -r requirements.txt")
        sys.exit(1)
    print("  Done!\n")

    # ── Step 2: Anthropic API key ─────────────────────────────
    print("Step 2/3: Anthropic API Key")

    # Check if already set
    existing_key = _read_env_key("ANTHROPIC_API_KEY")
    if existing_key:
        print(f"  Found existing API key ({existing_key[:8]}...)")
        keep = input("  Keep this key? [Y/n] ").strip().lower()
        if keep not in ("n", "no"):
            print("  Kept.\n")
        else:
            existing_key = None

    if not existing_key:
        print("  You need an API key from: https://console.anthropic.com")
        print("  Sign in → go to 'API Keys' → create one and copy it.")
        print()
        while True:
            key = input("  Paste your API key here: ").strip()
            if key.startswith("sk-ant-"):
                break
            print("  That doesn't look right — Anthropic API keys start with 'sk-ant-'. Try again.")
        _write_env_key("ANTHROPIC_API_KEY", key)
        print("  Saved to .env\n")

    # ── Step 3: Google Drive credentials ─────────────────────
    print("Step 3/3: Google Drive access")

    if os.path.exists("credentials.json"):
        print("  Found credentials.json\n")
    else:
        print()
        print("  To access your Drive, Google requires a credentials file.")
        print("  Here's how to get it (takes about 3 minutes):")
        print()
        print("  1. Go to: https://console.cloud.google.com")
        print("  2. At the top, click 'Select a project' → 'New Project'")
        print("     → give it any name → click 'Create'")
        print("  3. In the search bar, type 'Google Drive API' and click on it")
        print("     → click the blue 'Enable' button")
        print("  4. In the left menu, go to 'APIs & Services' → 'Credentials'")
        print("  5. Click '+ Create Credentials' → choose 'OAuth client ID'")
        print("  6. If prompted to configure consent screen:")
        print("     → choose 'External', fill in an app name (anything), save")
        print("     → go back to Credentials → Create Credentials → OAuth client ID")
        print("  7. For 'Application type', choose 'Desktop app'")
        print("     → give it any name → click 'Create'")
        print("  8. A dialog appears — click the download button (looks like ⬇)")
        print("     → save the file")
        print("  9. Rename that file to 'credentials.json' and move it into:")
        print(f"     {os.path.abspath('.')}")
        print()

        while True:
            input("  Press Enter when credentials.json is in place... ")
            if os.path.exists("credentials.json"):
                print("  Found credentials.json!")
                break
            print(f"  Not found yet. Make sure the file is named exactly 'credentials.json'")
            print(f"  and is in the folder: {os.path.abspath('.')}")
            print()

    # ── Authenticate with Google ──────────────────────────────
    print()
    print("  Now let's connect to your Google account.")
    print("  A browser window will open — log in and click 'Allow'.")
    print()
    input("  Press Enter to open the browser... ")

    # Load the API key we just saved
    _load_dotenv_simple()

    try:
        from auth import get_drive_service
        service = get_drive_service()
        # Quick test — list a single file to confirm access
        service.files().list(pageSize=1, fields="files(id)").execute()
        print()
        print("  Connected to Google Drive!")
    except Exception as e:
        print()
        print(f"  ERROR connecting to Google Drive: {e}")
        print("  Make sure you approved access in the browser and try again.")
        sys.exit(1)

    # ── Done! ────────────────────────────────────────────────
    print()
    print("=" * 55)
    print("  Setup complete!")
    print()
    print("  To organize your Drive, run:")
    print()
    print("      python run.py")
    print()
    print("  Run that command anytime files start to build up.")
    print("=" * 55)
    print()


def _read_env_key(key_name: str) -> str | None:
    """Read a key from .env file if it exists."""
    if not os.path.exists(".env"):
        return None
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key_name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _write_env_key(key_name: str, value: str):
    """Write or update a key in the .env file."""
    lines = []
    updated = False

    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if line.strip().startswith(f"{key_name}="):
                    lines.append(f'{key_name}="{value}"\n')
                    updated = True
                else:
                    lines.append(line)

    if not updated:
        lines.append(f'{key_name}="{value}"\n')

    with open(".env", "w") as f:
        f.writelines(lines)


def _load_dotenv_simple():
    """Load .env file into os.environ (simple parser, no dependency needed yet)."""
    if not os.path.exists(".env"):
        return
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


if __name__ == "__main__":
    run()
