#!/usr/bin/env python3
"""Macabi appointment checker bot."""

import argparse
import asyncio
import logging
import os
import re
import smtplib
import sys
import traceback
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = SCRIPT_DIR / "logs" / "checker.log"
LOGIN_URL = "https://www.maccabi4u.co.il/"
APPOINTMENTS_URL = "https://www.maccabi4u.co.il/new/personal-area/doctor-appointments/"

# Set after argument parsing; default to legacy path for backward compatibility
NOTIFICATION_FILE = SCRIPT_DIR / "last_notification.txt"
JOB_NAME = ""


def setup_logging():
    LOG_FILE.parent.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


def log(level: str, msg: str, *args):
    """Log with optional job-name prefix."""
    prefix = f"[{JOB_NAME}] " if JOB_NAME else ""
    getattr(logging, level)(prefix + msg, *args)


def load_config(job_path: Path | None) -> dict:
    env_file = job_path if job_path else SCRIPT_DIR / ".env"
    load_dotenv(env_file)

    required = [
        "MACABI_ID",
        "MACABI_PASSWORD",
        "DOCTOR_NAME",
        "GMAIL_SENDER",
        "GMAIL_APP_PASSWORD",
        "GMAIL_RECIPIENT",
    ]

    config = {}
    missing = []
    for key in required:
        val = os.getenv(key)
        if not val:
            missing.append(key)
        else:
            config[key] = val

    if missing:
        log("error", "Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    config["GMAIL_APP_PASSWORD"] = config["GMAIL_APP_PASSWORD"].replace(" ", "")
    config["HEADLESS"] = os.getenv("HEADLESS", "true").lower() != "false"
    config["APPOINTMENT_CITIES"] = [c.strip() for c in os.getenv("APPOINTMENT_CITY", "").split(",") if c.strip()]
    config["APPOINTMENT_TYPE"] = os.getenv("APPOINTMENT_TYPE", "")
    raw_max_days = os.getenv("MAX_DAYS_FROM_NOW", "")
    config["MAX_DAYS_FROM_NOW"] = int(raw_max_days) if raw_max_days.isdigit() else None
    return config


def parse_appt_date(date_str: str) -> datetime | None:
    """Parse appointment date string like 'יום ג\' 26/05/26' into a datetime."""
    match = re.search(r"(\d{2}/\d{2}/\d{2})", date_str)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d/%m/%y")
        except ValueError:
            pass
    return None


def should_send_email(appt_date: str | None) -> bool:
    if appt_date is None:
        return False

    if not NOTIFICATION_FILE.exists():
        return True

    try:
        content = NOTIFICATION_FILE.read_text().strip().splitlines()
        last_ts = datetime.fromisoformat(content[0])
        last_status = content[1] if len(content) > 1 else "not_found"
        last_date_str = content[2] if len(content) > 2 else ""
    except Exception:
        log("warning", "Could not parse %s, defaulting to send", NOTIFICATION_FILE)
        return True

    if last_status == "not_found":
        return True

    # If the new appointment is earlier than the previously notified one → send
    new_dt = parse_appt_date(appt_date)
    last_dt = parse_appt_date(last_date_str)
    if new_dt and last_dt and new_dt < last_dt:
        log("info", "Closer appointment found (%s < %s) — sending notification", appt_date, last_date_str)
        return True

    # Otherwise suppress if < 24h since last email
    if datetime.now() - last_ts < timedelta(hours=24):
        log("info", "Email suppressed (sent < 24h ago and no closer appointment)")
        return False

    return True


def record_notification(appt_date: str | None):
    status = "found" if appt_date else "not_found"
    date_line = f"\n{appt_date}" if appt_date else ""
    NOTIFICATION_FILE.write_text(f"{datetime.now().isoformat()}\n{status}{date_line}\n")


async def login(page, config: dict):
    log("info", "Navigating to main page...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)

    # Step 1: Click "למכבי Online" — opens a popup
    log("info", "Step 1: clicking למכבי Online")
    async with page.expect_popup() as popup_info:
        await page.get_by_role("link", name="למכבי Online").click()
    page1 = await popup_info.value
    await page1.wait_for_load_state("networkidle", timeout=15000)

    # Step 2: Fill ID → click המשך
    log("info", "Step 2: filling ID and clicking המשך")
    await page1.get_by_role("textbox", name="מספר תעודת זהות").fill(config["MACABI_ID"])
    await page1.get_by_role("button", name="המשך").click()
    await page1.wait_for_load_state("networkidle", timeout=15000)

    # Step 3: לכניסה בדרך אחרת (skip phone push)
    log("info", "Step 3: clicking לכניסה בדרך אחרת")
    await page1.locator("#verifyHub1").get_by_text("לכניסה בדרך אחרת").click()
    await page1.wait_for_load_state("networkidle", timeout=15000)

    # Step 4: כניסה עם סיסמה
    log("info", "Step 4: clicking כניסה עם סיסמה")
    await page1.locator("#chooseType").get_by_text("כניסה עם סיסמה").click()
    await page1.wait_for_load_state("networkidle", timeout=15000)

    # Step 5: Fill ID + password → click המשך
    log("info", "Step 5: filling ID + password and clicking המשך")
    await page1.get_by_role("textbox", name="מספר תעודת זהות").fill(config["MACABI_ID"])
    await page1.get_by_role("textbox", name="סיסמה").fill(config["MACABI_PASSWORD"])
    await page1.get_by_role("button", name="המשך").click()
    await page1.wait_for_load_state("networkidle", timeout=15000)

    # Close the modal that appears after login
    modal_close = page1.locator(".node_modules-\\@maccabi-m-ui-src-components-Modal-Modal-module__exitButton___nfFs_")
    await modal_close.wait_for(state="visible", timeout=10000)
    await modal_close.click()
    log("info", "Closed post-login modal")

    log("info", "Login successful, now at: %s", page1.url)

    return page1


async def navigate_to_appointments(page):
    log("info", "Navigating to new appointment booking...")

    # Click "זימון תור חדש" (3rd button on page)
    await page.locator("button").filter(has_text="זימון תור חדש").nth(2).click()
    await page.wait_for_load_state("networkidle", timeout=15000)
    
    # Click המשך (2nd button)
    await page.get_by_role("button", name="המשך").nth(1).click()
    await page.wait_for_load_state("networkidle", timeout=15000)

    # Select "רופאים/ות" category
    await page.get_by_role("button", name="רופאים/ות", exact=True).click()
    await page.wait_for_load_state("networkidle", timeout=15000)


async def search_doctor(
    page,
    doctor_name: str,
    cities: list[str] | None = None,
    appt_type: str = "",
    max_days: int | None = None,
) -> str | None:
    """Search for a doctor and return the nearest appointment date string, or None if not found.

    cities    — list of cities to accept (e.g. ["שדרות", "נתיבות"]). Empty = any.
    appt_type — "מרחוק" or "במרפאה". Empty = either.
    max_days  — only accept appointments within this many days from today. None = no limit.
    """
    cities = cities or []
    log("info", "Searching for doctor: %s (cities=%r, type=%r, max_days=%r)", doctor_name, cities, appt_type, max_days)

    await page.get_by_role("textbox", name="שם משפחה, שם פרטי").fill(doctor_name)
    await page.get_by_role("button", name="חיפוש", exact=True).click()

    # Wait for results to actually render (not just networkidle)
    try:
        await page.wait_for_selector("text=תור פנוי קרוב", timeout=15000)
    except Exception:
        log("warning", "'תור פנוי קרוב' did not appear after search")

    page_text = await page.inner_text("body")

    # Save raw text for debugging
    debug_text_file = SCRIPT_DIR / "debug_search.txt"
    debug_text_file.write_text(page_text, encoding="utf-8")
    log("info", "Saved raw page text to %s", debug_text_file)

    if "לא נמצאו" in page_text or "לא נמצאו תוצאות" in page_text:
        log("info", "No doctor results found")
        return None

    # Each card in the page text has the structure:
    #   כתובת\n<address>\nתור פנוי קרוב\n<type>:\n<date>\n...\nזימון תור
    # The city is in the address line BEFORE "תור פנוי קרוב", so we match both together.
    card_pattern = re.compile(
        r"כתובת\n(.+)\nתור פנוי קרוב\n(.*?)זימון תור",
        re.DOTALL,
    )
    cards = card_pattern.findall(page_text)
    log("info", "Found %d result card(s)", len(cards))

    for i, (address, appt_section) in enumerate(cards, 1):
        address = address.strip()
        log("info", "Card %d: address=%r", i, address)

        # Apply city filter — accept if any of the cities appears in the address
        if cities and not any(c in address for c in cities):
            log("info", "Card %d skipped: none of cities %r in address %r", i, cities, address)
            continue

        # Extract date: type is on one line, date is on the next line
        if appt_type:
            match = re.search(re.escape(appt_type) + r":\n(יום\s+\S+\s+\d{2}/\d{2}/\d{2})", appt_section)
        else:
            match = re.search(r"יום\s+\S+\s+\d{2}/\d{2}/\d{2}", appt_section)

        if not match:
            log("info", "Card %d skipped: no date matched for type=%r in: %r", i, appt_type, appt_section[:100])
            continue

        appt_date = match.group(1) if match.lastindex else match.group(0)

        # Apply max_days filter
        if max_days is not None:
            appt_dt = parse_appt_date(appt_date)
            if appt_dt and (appt_dt - datetime.now()).days > max_days:
                log("info", "Card %d skipped: date %s is more than %d days away", i, appt_date, max_days)
                continue

        log("info", "Found appointment: type=%r cities=%r date=%s", appt_type or "any", cities or "any", appt_date)
        return appt_date

    log("info", "No appointments matched filters (cities=%r, type=%r, max_days=%r)", cities, appt_type, max_days)
    return None


def send_email(config: dict, doctor_name: str, appt_date: str = ""):
    subject = f"נמצא תור פנוי עם {doctor_name}"
    date_line = f"תאריך קרוב: {appt_date}\n" if appt_date else ""
    type_line = f"סוג תור: {config['APPOINTMENT_TYPE']}\n" if config.get("APPOINTMENT_TYPE") else ""
    city_line = f"עיר: {', '.join(config['APPOINTMENT_CITIES'])}\n" if config.get("APPOINTMENT_CITIES") else ""
    body = (
        f"שלום,\n\n"
        f"נמצא תור פנוי עם {doctor_name} בפורטל מכבי.\n\n"
        f"{date_line}{type_line}{city_line}"
        f"\nלקביעת תור: {APPOINTMENTS_URL}\n\n"
        f"הבוט שלך"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config["GMAIL_SENDER"]
    msg["To"] = config["GMAIL_RECIPIENT"]

    log("info", "Sending email to %s...", config["GMAIL_RECIPIENT"])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config["GMAIL_SENDER"], config["GMAIL_APP_PASSWORD"])
        smtp.sendmail(config["GMAIL_SENDER"], config["GMAIL_RECIPIENT"], msg.as_string())
    log("info", "Email sent successfully")


async def run_check(config: dict):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config["HEADLESS"],
            args=["--lang=he-IL"],
        )
        context = await browser.new_context(
            locale="he-IL",
            timezone_id="Asia/Jerusalem",
        )
        page = await context.new_page()

        try:
            page1 = await login(page, config)
            await navigate_to_appointments(page1)
            appt_date = await search_doctor(
                page1,
                config["DOCTOR_NAME"],
                cities=config["APPOINTMENT_CITIES"],
                appt_type=config["APPOINTMENT_TYPE"],
                max_days=config["MAX_DAYS_FROM_NOW"],
            )
            found = appt_date is not None

            if should_send_email(appt_date):
                send_email(config, config["DOCTOR_NAME"], appt_date or "")

            record_notification(appt_date)

            if found:
                log("info", "Run complete: appointments FOUND for %s (%s)", config["DOCTOR_NAME"], appt_date)
            else:
                log("info", "Run complete: no appointments found for %s", config["DOCTOR_NAME"])

        except PlaywrightTimeout as e:
            log("error", "Timeout during check: %s", e)
            sys.exit(1)
        except Exception as e:
            log("error", "Unexpected error: %s\n%s", e, traceback.format_exc())
            sys.exit(1)
        finally:
            await browser.close()


def main():
    global NOTIFICATION_FILE, JOB_NAME

    parser = argparse.ArgumentParser()
    parser.add_argument("--job", metavar="PATH", help="Path to a job .env file (e.g. jobs/doctor1.env)")
    args = parser.parse_args()

    job_path = Path(args.job).resolve() if args.job else None
    if job_path:
        JOB_NAME = job_path.stem
        NOTIFICATION_FILE = SCRIPT_DIR / f"last_notification_{JOB_NAME}.txt"

    setup_logging()
    log("info", "=== Macabi appointment checker starting ===")
    config = load_config(job_path)
    asyncio.run(run_check(config))


if __name__ == "__main__":
    main()
