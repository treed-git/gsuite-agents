# Google Drive Organizer

An AI agent that looks at your Google Drive files, suggests better names, and groups them into organized folders — then asks before making any changes.

**The agent never deletes files or changes their contents.** It only renames files and moves them into folders.

---

## How to use

### First time only
```
python setup_wizard.py
```
The wizard walks you through everything step by step (about 5 minutes).

### Every time after that
```
python run.py
```
The agent will scan your Drive, show you a preview of proposed changes, and ask for your confirmation before doing anything.

---

## Running automatically (optional)

If you want the organizer to run on a schedule without asking for confirmation, use the `--apply` flag:

```
python run.py --apply
```

### On Mac/Linux (cron)
Open a terminal and run `crontab -e`, then add a line like this to run every Monday at 9am:

```
0 9 * * 1 cd /path/to/gsuite-agents && python run.py --apply >> organizer.log 2>&1
```

Replace `/path/to/gsuite-agents` with the actual folder path.

### Organize a specific folder only
```
python run.py --folder-id YOUR_FOLDER_ID
```
You can find a folder's ID in its Google Drive URL (the long string of letters/numbers after `/folders/`).

---

## What gets organized

By default, the agent looks at all files in your My Drive. You can limit it to a specific folder using `--folder-id` or by setting `GDRIVE_FOLDER_ID` in your `.env` file.

---

## Files in this project

| File | Purpose |
|------|---------|
| `run.py` | **Run this to organize your Drive** |
| `setup_wizard.py` | **Run this first, one time only** |
| `agent.py` | AI agent logic (internal) |
| `gdrive.py` | Google Drive API (internal) |
| `auth.py` | Google login handling (internal) |
| `tools.py` | Agent tools (internal) |
| `credentials.json` | Your Google credentials (you add this during setup) |
| `token.json` | Saved login session — auto-created after setup |
| `.env` | Your API key — auto-created during setup |
