# Macabi Appointment Checker

Automated bot that checks the Maccabi healthcare portal for available appointments with a specific doctor, and sends an email notification when one is found. Runs hourly via cron.

## How it works

1. Logs into the Maccabi4u portal using your credentials (via Playwright/Chromium)
2. Navigates to the appointment booking section and searches for your doctor
3. Applies optional filters (city, appointment type, max days away)
4. Sends a Gmail notification if an appointment is found
5. Suppresses repeat emails for the same appointment (max one per 24h, unless a closer date is found)

## Setup

### 1. Create a job file

Each doctor/configuration is a `.env`-format file inside the `jobs/` directory. Use the interactive setup via Claude Code:

```
/macabi-setup
```

Or create a file manually:

```bash
cp jobs/doctor1.env jobs/myname.env
# edit jobs/myname.env with your details
```

### 2. Environment variables

Each job file supports the following variables:

| Variable | Required | Description |
|---|---|---|
| `MACABI_ID` | Yes | Israeli ID number (תעודת זהות) |
| `MACABI_PASSWORD` | Yes | Maccabi portal password |
| `DOCTOR_NAME` | Yes | Doctor's full name in Hebrew, last name first (e.g. `קרבץ לאוניד`) |
| `GMAIL_SENDER` | Yes | Gmail address to send notifications from |
| `GMAIL_APP_PASSWORD` | Yes | Gmail App Password (16-char code from myaccount.google.com → Security → App passwords) |
| `GMAIL_RECIPIENT` | Yes | Email address to receive notifications |
| `HEADLESS` | No | `true` (default) to run silently, `false` to show browser window |
| `APPOINTMENT_CITY` | No | Comma-separated cities to filter by (e.g. `אשקלון,נתיבות`). Empty = any city |
| `APPOINTMENT_TYPE` | No | `מרחוק` (remote) or `במרפאה` (in-person). Empty = either |
| `MAX_DAYS_FROM_NOW` | No | Only accept appointments within this many days. Empty = no limit |

### 3. Run setup

Installs Python dependencies, Playwright Chromium, and registers the hourly cron job:

```bash
bash setup_cron.sh
```

### 4. Test manually

```bash
source venv/bin/activate && python checker.py --job jobs/myname.env
```

## Multiple doctors

Add one file per doctor inside `jobs/`. All jobs run sequentially on the same hourly cron schedule — no extra configuration needed.

Each job gets its own notification state file (e.g. `last_notification_doctor1.txt`) so suppression logic is independent per job.

Log entries are prefixed with the job name for easy filtering:

```
2026-03-09 10:00:01 [INFO] [doctor1] Searching for doctor: ...
2026-03-09 10:02:14 [INFO] [doctor2] Searching for doctor: ...
```

## Files

| File | Description |
|---|---|
| `checker.py` | Main bot script |
| `setup_cron.sh` | One-time setup: installs deps and registers cron |
| `run.sh` | Wrapper script executed by cron every hour |
| `requirements.txt` | Python dependencies (`playwright`, `python-dotenv`) |
| `jobs/` | Per-job `.env` files (one file = one doctor/configuration) |
| `logs/checker.log` | Rotating log file (up to 5 MB × 3 backups) |
| `last_notification_<job>.txt` | Per-job notification state (prevents email spam) |
| `debug_search.txt` | Raw page text from last search run (for debugging) |

## Useful commands

```bash
# View live logs
tail -f logs/checker.log

# Check registered cron jobs
crontab -l

# Remove the cron job
crontab -l | grep -v run.sh | crontab -
```

## Gmail App Password

A Gmail App Password is required — your regular Gmail password will not work.

1. Go to [myaccount.google.com](https://myaccount.google.com) → Security
2. Enable 2-Step Verification if not already enabled
3. Search for "App passwords" and create one for this app
4. Copy the 16-character code into `GMAIL_APP_PASSWORD` in your job file
