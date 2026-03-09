Set up the Maccabi appointment checker by collecting configuration, writing a job file, running setup_cron.sh, and optionally running the checker.

Follow these steps in order:

## Step 1 — Job name (required)

Use AskUserQuestion to ask:
- A short name for this job, used as the filename (e.g. `doctor1`, `karatz`, `specialist`) — no spaces, no special characters

The job will be saved as `jobs/<name>.env`.

## Step 2 — Maccabi login (required)

Use AskUserQuestion to ask all three together:
- Israeli ID number (תעודת זהות)
- Maccabi portal password (סיסמה)
- Doctor full name in Hebrew, last name first (e.g. קרבץ לאוניד)

## Step 3 — Email notifications (required)

Use AskUserQuestion to ask all three together:
- Gmail address to send notifications FROM
- Gmail app password — 16-character code generated at myaccount.google.com → Security → App passwords (NOT your regular Gmail password)
- Email address to RECEIVE notifications (can be the same Gmail)

## Step 4 — Appointment filters (optional)

Use AskUserQuestion to ask all four together. Tell the user to leave any field blank to skip that filter:
- Cities to filter by, comma-separated (e.g. אשקלון,נתיבות) — blank = any city
- Appointment type: מרחוק (remote) or במרפאה (in-person) — blank = either
- Maximum days from today to accept (e.g. 30) — blank = no limit
- Show browser window while running? (yes/no) — default is no (runs silently)

## Step 5 — Write job file

Write the collected values to `/Users/shaymark/Documents/automations/macabi/jobs/<name>.env` using this exact format:

```
MACABI_ID=<id>
MACABI_PASSWORD=<password>
DOCTOR_NAME=<doctor name>
GMAIL_SENDER=<gmail address>
GMAIL_APP_PASSWORD=<app password>
GMAIL_RECIPIENT=<recipient email>
HEADLESS=<true if user said no to visible browser, false if yes>
# Optional filters — leave empty to match any
APPOINTMENT_CITY=<cities or empty>
APPOINTMENT_TYPE=<type or empty>
MAX_DAYS_FROM_NOW=<number or empty>
```

Make sure the `jobs/` directory exists before writing:
```bash
mkdir -p /Users/shaymark/Documents/automations/macabi/jobs
```

## Step 6 — Run setup_cron.sh

Run the setup script which installs the Python virtual environment, dependencies, Playwright Chromium browser, and registers the hourly cron job:

```bash
cd /Users/shaymark/Documents/automations/macabi && bash setup_cron.sh
```

Show the output to the user and confirm the cron job was registered.

## Step 7 — Test run

Use AskUserQuestion to ask: "Setup complete! Would you like to run the checker now to test it?"

If yes, run:
```bash
cd /Users/shaymark/Documents/automations/macabi && source venv/bin/activate && python checker.py --job jobs/<name>.env
```

Then read the last 30 lines of `/Users/shaymark/Documents/automations/macabi/logs/checker.log` and summarize:
- Whether an appointment was found
- The appointment date and type if found
- Whether an email notification was sent
