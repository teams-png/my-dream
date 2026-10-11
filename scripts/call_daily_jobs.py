"""Render Cron Job: asks the live site to run its once-a-day jobs (same URL the GitHub Action calls).

Needs BOOKPILOT_URL (e.g. https://app.example.com) and CRON_SECRET (the web service's value) in the environment.
Uses only the standard library, so the cron service needs no build step.
"""
import os
import sys
import time
import urllib.request

url = os.environ.get("BOOKPILOT_URL", "").rstrip("/")
key = os.environ.get("CRON_SECRET", "")
if not url or not key:
    sys.exit("BOOKPILOT_URL and CRON_SECRET must be set")

for attempt in range(3):
    try:
        req = urllib.request.Request(f"{url}/cron/daily/", data=b"", method="POST", headers={"X-Cron-Key": key})
        with urllib.request.urlopen(req, timeout=900) as resp:
            print(resp.status, resp.read().decode()[:2000])
            sys.exit(0)
    except Exception as exc:  # retry a deploy restart or a slow wake-up
        print(f"attempt {attempt + 1} failed: {exc}")
        time.sleep(30)
sys.exit(1)
