# Public availability

`update_schedule.py` reads the public calendar and Korean public holidays. It
publishes only start/end times and the all-day flag, never event names, IDs,
locations or descriptions. The snapshot covers five weeks starting on Monday
in Asia/Seoul. A complete new file replaces the old file atomically.

The Pages workflow runs every five minutes (also on push/manual dispatch). It
checks out the `schedule-data` branch into `_availability`, refreshes its
`schedule.json`, and commits only that file back to `schedule-data`. The branch
must exist before enabling this workflow and contains only this time-only JSON.
The workflow's write permission is used for these snapshot commits. Failed
calendar reads retain the previous snapshot without advancing `generatedAt`.

The browser reads the raw `schedule-data/schedule.json` directly, independently
of full-site Pages deployments. This avoids relying on repeat deployments of
the same source commit for changing data. The JSON packaged with the page and
the browser's last valid snapshot are fallbacks. The newest valid snapshot wins;
malformed, future-dated or older responses do not replace it.

Stale snapshots remain visible with their actual update time. Dates outside
their coverage say `확인 필요`, so an unavailable date cannot appear free. A
refresh never hides an already displayed calendar. Only time fields are stored
in the browser. No calendar titles or contact details are added to the page.

Run regression checks from the repository root:

```bash
python3 -m unittest discover -s scripts -p 'test_schedule.py'
node scripts/test_schedule_ui.cjs
```
