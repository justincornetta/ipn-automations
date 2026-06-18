# IPN Meeting Summary Pipeline

Automates IPN Zoom cloud transcript archiving and director-facing Slack summaries.

Flow:

1. Zoom emits `recording.transcript_completed` or `recording.completed`.
2. Netlify Function validates the Zoom webhook signature.
3. Function dispatches the GitHub Actions workflow.
4. Workflow downloads the Zoom transcript with Server-to-Server OAuth.
5. Workflow saves artifacts to Google Drive.
6. OpenAI generates the standardized summary.
7. IPN Bot posts the summary to private Slack channel `#meeting-summaries`.

The workflow also runs every 15 minutes as a fallback poller for recent Zoom recordings.

## Drive Archive

Authoritative archive:

```text
Main - IPN/Technology/Automations/Meeting Summaries/
```

Default meeting folder structure:

```text
YYYY/<meeting-group>/<YYYY-MM-DD>__<zoom-topic-slug>/
  transcript.vtt
  transcript.txt
  summary.md
  slack-message.md
  metadata.json
  last-error.json      # only when a processing step fails
```

Meeting groups are inferred from the Zoom topic:

- `board`
- `community`
- `psychedelx`
- `ipn-labs`
- `operations`
- `uncategorized`

Set `MEETING_INCLUDE_KEYWORDS` or `MEETING_EXCLUDE_KEYWORDS` as comma-separated filters if the shared Zoom account starts recording meetings that should not be summarized.

## GitHub Secrets

Required:

- `ZOOM_ACCOUNT_ID`
- `ZOOM_CLIENT_ID`
- `ZOOM_CLIENT_SECRET`
- `SLACK_BOT_TOKEN`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `MEETING_SUMMARIES_ROOT_FOLDER_ID`

Alternative Google auth:

- `GOOGLE_SERVICE_ACCOUNT_JSON` may be used instead of the OAuth client/refresh token secrets. Share the `Meeting Summaries` Drive folder with the service account as a writer.

Recommended:

- `SLACK_MEETING_SUMMARIES_CHANNEL_ID`
- `OPENAI_API_KEY` for full structured summaries. Without it, the pipeline posts a clearly labeled fallback summary.
- `OPENAI_MODEL` defaults to `gpt-5.4-nano`
- `MEETING_INCLUDE_KEYWORDS`
- `MEETING_EXCLUDE_KEYWORDS`
- `MEETING_SUMMARY_POLL_WINDOW_DAYS` defaults to `2`
- `MEETING_SUMMARY_RETRY_HOURS` defaults to `24`

Optional Slack channel creation:

- `SLACK_CREATE_MEETING_SUMMARIES_CHANNEL=true`
- `SLACK_MEETING_SUMMARIES_CHANNEL_NAME=meeting-summaries`

Prefer creating the private Slack channel manually, inviting the IPN Bot, and setting `SLACK_MEETING_SUMMARIES_CHANNEL_ID`. Automated private-channel creation requires extra Slack scopes (`groups:write` and `groups:read`) beyond normal posting.

## Netlify Environment Variables

The webhook receiver at `/api/zoom/webhook` needs:

- `ZOOM_WEBHOOK_SECRET_TOKEN`
- `GITHUB_OWNER`
- `GITHUB_REPO`
- `GITHUB_DISPATCH_TOKEN`
- `GITHUB_MEETING_SUMMARY_WORKFLOW_ID` defaults to `meeting_summary_pipeline.yml`
- `GITHUB_REF` defaults to `main`

`GITHUB_DISPATCH_TOKEN` needs permission to dispatch Actions workflows in this repository.

## Google OAuth

The Drive archive needs a refresh token with:

```text
https://www.googleapis.com/auth/drive
```

Generate it locally:

```bash
cd automations/meeting-summary-pipeline
python -m pip install -r requirements.txt
PYTHONPATH=src python scripts/generate_refresh_token.py
```

Set `MEETING_SUMMARIES_ROOT_FOLDER_ID` to the Drive folder ID for `Meeting Summaries`. This avoids ambiguity with shared drives and makes the workflow faster.

## Zoom Setup

Use the same Server-to-Server OAuth app pattern as the analytics dashboard, with recording read scopes sufficient for:

- listing users
- listing cloud recordings
- reading meeting recordings
- reading past meeting participants

Create a Zoom webhook app/event subscription pointing to:

```text
https://<netlify-site>/api/zoom/webhook
```

Subscribe to:

- `recording.transcript_completed`
- `recording.completed`

`recording.completed` is intentionally included because recording completion and transcript completion can arrive at different times. If a transcript is not available yet, the workflow writes an audit record and the 15-minute poller retries.

## Slack Output

Each Slack post includes:

- meeting title, date, group, and attendees when available
- Drive archive link
- executive summary
- key decisions
- action items
- cross-team FYIs
- risks/blockers

Raw transcript text is saved to Drive, not posted to Slack.

## Local Commands

Run tests:

```bash
cd automations/meeting-summary-pipeline
python -m pip install -r requirements.txt
PYTHONPATH=src pytest
```

Dry-run a scheduled poll:

```bash
PYTHONPATH=src python scripts/run_pipeline.py --poll --dry-run
```

Dry-run one meeting:

```bash
PYTHONPATH=src python scripts/run_pipeline.py --meeting-id '<zoom-meeting-uuid>' --dry-run
```

## Operational Notes

- Idempotency key is `Zoom meeting UUID + transcript recording file ID`.
- The Drive meeting folder stores `ipn_idempotency_key`, `ipn_status`, `ipn_group`, and `ipn_slack_ts` in app properties.
- `ipn_status=posted` prevents duplicate Slack posts from duplicate webhooks and fallback polling.
- `ipn_status=failed` is retried by the next webhook/poll and preserves `last-error.json` for diagnosis.

## API References

- Zoom Meetings/Cloud Recordings API: https://developers.zoom.us/docs/api/meetings/
- Zoom Server-to-Server OAuth: https://developers.zoom.us/docs/internal-apps/create/
- Slack `chat.postMessage`: https://api.slack.com/methods/chat.postMessage
- Slack `conversations.create`: https://api.slack.com/methods/conversations.create
- OpenAI API pricing/model docs: https://developers.openai.com/api/docs/pricing
