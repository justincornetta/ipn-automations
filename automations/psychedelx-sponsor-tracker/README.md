# PsychedelX Sponsor Tracker (GitHub Actions)

Runs a daily Gmail → Google Sheets sync for the PsychedelX sponsorship tracker, then posts a privacy-safe operational update to Slack as the IPN Bot.

This is intended to replace the “computer must be on” local cron.

## What it does

- Searches Gmail (past 24 hours) for sponsorship-related threads.
- Updates only these tabs in the *native* Google Sheets tracker:
  - `PsychedelX 2026 Pipeline`
  - `Automation Audit`
- Builds a follow-up reminder list for rows with `Next Follow-Up Due` <= today (excluding `Closed Won` / `Closed Lost`).
- Posts a formatted message to Slack channel `#partnerships-updates` (channel ID `C0B4G57B719`) using `SLACK_BOT_TOKEN`.

## Repo setup

1. Put this folder in a GitHub repository (recommended: a dedicated private repo such as `ipn-automations`).
2. Ensure `.github/workflows/psychedelx_sponsor_tracker.yml` exists in the repo root (this repo includes it).

## Required GitHub Secrets

Create these repository secrets:

- `SLACK_BOT_TOKEN` — IPN Bot token with `chat:write` access.
- `GOOGLE_CLIENT_ID` — OAuth client id (installed app or web app).
- `GOOGLE_CLIENT_SECRET` — OAuth client secret.
- `GOOGLE_REFRESH_TOKEN` — refresh token for the Gmail/Sheets scopes listed below.
- `GOOGLE_USER_EMAIL` — mailbox user (e.g. `justin@intercollegiatepsychedelics.net`) used for Gmail `users.messages.*`.

Optional (override defaults):
- `TRACKER_SHEET_ID` — defaults to `1E_kHmYj-JZ8MCDDeeJWqOPUbIqnu5AgRdC2uBfmp3fw`
- `TRACKER_TAB_NAME` — defaults to `PsychedelX 2026 Pipeline`
- `AUDIT_TAB_NAME` — defaults to `Automation Audit`
- `SLACK_CHANNEL_ID` — defaults to `C0B4G57B719`

## OAuth scopes

The refresh token must be created with these scopes:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/spreadsheets`

## Generating a refresh token (one-time)

Use a local one-time helper (recommended) to generate `GOOGLE_REFRESH_TOKEN` for the mailbox that should be scanned.

This repo includes `scripts/generate_refresh_token.py` which prints a refresh token after you complete the Google consent flow.

## Notes / safety

- Slack messages are high-level only; no email body quotes are posted.
- If required columns are missing or the sheet shape changes, the run exits without writing tracker updates.
