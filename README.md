# IT Backup Report Automation

A small, vendor-neutral Python tool that turns normalized backup CSV exports into a readable daily health report. It helps administrators spot failed jobs, overdue successful backups, and expected objects missing from an export.

**Status: initial working release, v0.1.0.** This project was developed with AI assistance and tested using fictional data. It has not been validated against a production backup environment. It makes no claims about adoption, vendor certification, or recovery guarantees.

## What it does

- Reviews the latest job and most recent successful backup for each object.
- Flags failures, cancellations, warnings, running jobs, and overdue successes.
- Checks an optional inventory to find objects with no reported jobs.
- Supports individual age limits, such as 24 hours for daily and 168 for weekly backups.
- Keeps historical failures visible after a successful retry.
- Generates **HTML**, **CSV (Excel-readable)**, and **JSON** reports locally.
- Uses Python's standard library only: no packages, API keys, or API credits required.

The tool does not connect to backup systems, modify jobs, create tickets, send email, or upload data. Vendor-specific exports must first be mapped to the documented CSV schema.

## Try the demo

Requirements: **Python 3.10 or newer** on Windows, macOS, or Linux. Download Python if needed from https://www.python.org/downloads/.

On Windows, extract the project and double-click **RUN_DEMO.cmd**. Alternatively, open a terminal in this folder:

```powershell
py -3 backup_report.py --demo
```

On macOS or Linux:

```bash
python3 backup_report.py --demo
```

Open `reports/backup_report.html` in your browser. Also generated:

- `reports/backup_summary.csv` — object-level summary for spreadsheet review.
- `reports/backup_report.json` — structured results for future integrations.

The demo uses a fixed reference time of **2026-09-16 12:00 UTC**, so the result remains reproducible: **8 objects, 3 OK, 2 warning, 3 critical**. All demo object names and messages are fictional. `example_report.html` is a pre-generated copy you can open without installing Python.

## Use your own data

Export your backup data, map its fields to the following schema, and save it as a UTF-8 CSV. Run:

```powershell
py -3 backup_report.py --input jobs.csv --inventory inventory.csv --output-dir reports --max-age-hours 24
```

Use `python3` instead of `py -3` on macOS/Linux. The default reference time is the current UTC time. For a historical analysis, add `--now 2026-09-16T12:00:00Z`.

### Job CSV

Required headers: `object_name,status,timestamp`. Optional header: `message`.

```csv
object_name,status,timestamp,message
example-web-01,success,2026-09-16T08:00:00-04:00,Daily backup completed
```

| Field | Meaning |
| --- | --- |
| `object_name` | Stable, case-sensitive object identifier. Use a VM name, fileset name, or a name combining object and policy. |
| `status` | `success`, `failed`, `warning`, `running`, or `cancelled`; case-insensitive. |
| `timestamp` | For completed jobs, completion time. For running jobs, observation time. Must be ISO 8601 with `Z` or an explicit UTC offset. |
| `message` | Optional diagnostic text; quote it if it contains commas or newlines. |

Each row is one job/observation. Sort order does not matter. For a single job that changes state, export its latest state only. Multiple observations of the same object at the same timestamp are rejected as ambiguous. Future timestamps and unknown statuses are rejected rather than silently ignored. For independent backup policies on one server, use distinct object names such as `server01/daily` and `server01/logs`.

### Inventory CSV

```csv
object_name,max_age_hours
example-web-01,24
example-weekly-01,168
```

`object_name` is required. The `max_age_hours` column is optional, and blank values use `--max-age-hours` (default: 24). Thresholds must be finite positive numbers. Duplicate inventory names are rejected. Objects present in the job export but absent from inventory are still evaluated using the default limit.

An inventory is strongly recommended: without it, the program cannot discover an object entirely absent from the job export. Supply enough history to include each object's last successful backup; no success in an abbreviated export means **no evidence in that export**, not proof that the object has never been backed up.

## How health is calculated

| Condition | Health |
| --- | --- |
| Expected object has no job history | CRITICAL |
| No `success` row in supplied history | CRITICAL |
| Most recent success is older than the object's threshold | CRITICAL |
| Latest job is `failed` or `cancelled` | CRITICAL |
| Latest job is `warning` or `running`, with a recent success | WARNING |
| Latest job is `success` and success age is within the limit | OK |

Critical conditions take precedence. Age exactly equal to the limit is accepted. A warning is conservatively not counted as a successful backup. A later successful retry can restore OK health; the earlier failure remains in the history section. Failure counts cover **all supplied history**, not just the last day. Age checks do not evaluate full SLA retention, application consistency, replication, or restorability. Restore tests remain necessary.

## Automate a daily report

In Windows Task Scheduler, create a daily task after the export is refreshed. Set **Program/script** to the full path of `python.exe`, set **Start in** to the project folder, and use arguments like:

```text
backup_report.py --input "C:\BackupExports\jobs.csv" --inventory "C:\BackupExports\inventory.csv" --output-dir "C:\BackupReports" --fail-on-alert
```

The CSV export process is separate; this script reads the files available at run time. An old export can show stale backups. Existing output files are replaced on successful runs, so use a dated output directory if you want an archive. Invalid input exits before generating reports; a previous report may still exist, so check the exit code and report timestamp.

| Exit code | Meaning |
| --- | --- |
| 0 | Report generated; with `--fail-on-alert`, all objects are OK. Without that option, alerts do not change the exit code. |
| 1 | Report generated and at least one object is WARNING or CRITICAL (`--fail-on-alert` only). |
| 2 | Invalid arguments, invalid input, or a file access/write error. |

## Test

```powershell
py -3 -m unittest -v
```

Use `python3 -m unittest -v` on macOS/Linux. Tests cover retry recovery, current failures, missing inventory objects, thresholds and timezones, malformed input, HTML escaping, CSV formula protection, and CLI output/exit codes.

## Data handling

The program runs locally and has no network calls. HTML values are escaped and spreadsheet formula prefixes are neutralized in CSV reports. JSON retains the original strings for programmatic use. Do not publish real backup exports, customer/server names, credentials, or generated production reports. The included samples are safe fictional examples. For very large exports, note that this initial version reads records into memory.

## Contributing and roadmap

See `CONTRIBUTING.md`. Useful next steps include vendor-specific CSV adapters, export freshness checks, and optional ticket drafts. These are future ideas, not implemented features. Reports currently use only the fields and rules above.

## License

MIT; see `LICENSE`.
