#!/usr/bin/env python3
"""Generate local backup health reports from normalized CSV exports (Python 3.10+)."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile

VERSION = "0.1.0"
STATUSES = {"success", "failed", "warning", "running", "cancelled"}
DEMO_TIME = "2026-09-16T12:00:00Z"
OUTPUT_NAMES = ("backup_report.html", "backup_summary.csv", "backup_report.json")


class InputError(ValueError):
    """An input cannot be interpreted reliably."""


@dataclass(frozen=True)
class Job:
    object_name: str
    status: str
    timestamp: datetime
    message: str


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone missing")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"Invalid timestamp {value!r}; use ISO 8601 with Z or a UTC offset.") from exc


def positive_hours(value: str | float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"Invalid hour threshold: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise InputError("Hour thresholds must be finite and greater than zero.")
    return number


def read_rows(path: Path, required: set[str], allowed: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)):
            raise InputError(f"{path.name}: duplicate CSV column names.")
        missing = required - set(fields)
        unexpected = set(fields) - allowed
        if missing or unexpected:
            raise InputError(f"{path.name}: missing columns {sorted(missing)}; unexpected columns {sorted(unexpected)}.")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise InputError(f"{path.name}, line {reader.line_num}: wrong number of columns.")
            cleaned = {key: value.strip() for key, value in row.items()}
            if not cleaned["object_name"]:
                raise InputError(f"{path.name}, line {reader.line_num}: object_name cannot be blank.")
            rows.append(cleaned)
        return rows


def load_jobs(path: Path, now: datetime) -> list[Job]:
    rows = read_rows(path, {"object_name", "status", "timestamp"},
                     {"object_name", "status", "timestamp", "message"})
    jobs = []
    seen = set()
    for row in rows:
        status = row["status"].lower()
        if status not in STATUSES:
            raise InputError(f"{path.name}: unsupported status {row['status']!r} for {row['object_name']!r}.")
        stamp = parse_time(row["timestamp"])
        if stamp > now:
            raise InputError(f"{path.name}: future timestamp for {row['object_name']!r}; check --now and timezone.")
        key = (row["object_name"], stamp)
        if key in seen:
            raise InputError(f"{path.name}: duplicate object/timestamp for {row['object_name']!r}.")
        seen.add(key)
        jobs.append(Job(row["object_name"], status, stamp, row.get("message", "")))
    return jobs


def load_inventory(path: Path, default_hours: float) -> dict[str, float]:
    rows = read_rows(path, {"object_name"}, {"object_name", "max_age_hours"})
    inventory = {}
    for row in rows:
        name = row["object_name"]
        if name in inventory:
            raise InputError(f"{path.name}: duplicate inventory object {name!r}.")
        inventory[name] = positive_hours(row.get("max_age_hours") or default_hours)
    return inventory


def iso(stamp: datetime | None) -> str | None:
    return stamp.isoformat().replace("+00:00", "Z") if stamp else None


def analyze(jobs: list[Job], inventory: dict[str, float], now: datetime,
            default_hours: float) -> list[dict]:
    grouped: dict[str, list[Job]] = {name: [] for name in inventory}
    for job in jobs:
        grouped.setdefault(job.object_name, []).append(job)
    results = []
    for name, history in sorted(grouped.items(), key=lambda item: item[0].casefold()):
        history.sort(key=lambda job: job.timestamp)
        latest = history[-1] if history else None
        success = next((job for job in reversed(history) if job.status == "success"), None)
        age = (now - success.timestamp).total_seconds() / 3600 if success else None
        threshold = inventory.get(name, default_hours)
        critical, warning = [], []
        if latest is None:
            critical.append("No jobs found in supplied history")
        elif latest.status in {"failed", "cancelled"}:
            critical.append(f"Latest job {latest.status}")
        elif latest.status in {"warning", "running"}:
            warning.append(f"Latest job {latest.status}; review required")
        if success is None:
            critical.append("No successful backup in supplied history")
        elif age > threshold:
            critical.append(f"Last successful backup exceeds {threshold:g} hours")
        results.append({
            "object_name": name,
            "health": "CRITICAL" if critical else "WARNING" if warning else "OK",
            "latest_status": latest.status if latest else "no_history",
            "latest_timestamp": iso(latest.timestamp) if latest else None,
            "last_success": iso(success.timestamp) if success else None,
            "age_hours": round(age, 4) if age is not None else None,
            "max_age_hours": threshold,
            "failed_jobs_in_export": sum(job.status == "failed" for job in history),
            "jobs_in_export": len(history),
            "issues": critical + warning,
            "latest_message": latest.message if latest else "",
        })
    return results


def build_report(jobs: list[Job], inventory: dict[str, float], now: datetime,
                 default_hours: float, inventory_supplied: bool) -> dict:
    objects = analyze(jobs, inventory, now, default_hours)
    if not objects:
        raise InputError("No objects found. Supply job rows or an inventory with expected objects.")
    return {
        "tool_version": VERSION,
        "as_of_utc": iso(now),
        "default_max_age_hours": default_hours,
        "inventory_supplied": inventory_supplied,
        "summary": {"objects": len(objects), "jobs_in_export": len(jobs),
                    **{health.lower(): sum(row["health"] == health for row in objects)
                       for health in ("OK", "WARNING", "CRITICAL")}},
        "scope_note": "Only supplied history is evaluated. A successful job does not verify recoverability."
                      + ("" if inventory_supplied else " No inventory: objects absent from the export cannot be detected."),
        "objects": objects,
        "failed_jobs": [{**asdict(job), "timestamp": iso(job.timestamp)}
                        for job in sorted(jobs, key=lambda job: job.timestamp, reverse=True)
                        if job.status == "failed"],
    }


def csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    # Prevent exported, untrusted strings being interpreted as spreadsheet formulas.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def render_csv(report: dict) -> str:
    output = io.StringIO(newline="")
    columns = list(report["objects"][0])
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in report["objects"]:
        writer.writerow({key: csv_safe("; ".join(value) if isinstance(value, list) else value)
                         for key, value in row.items()})
    return output.getvalue()


def render_html(report: dict) -> str:
    def e(value: object) -> str:
        return escape("—" if value is None else str(value), quote=True)

    cards = "".join(f'<div class="card"><span>{label}</span><strong>{report["summary"][key]}</strong></div>'
                    for key, label in (("objects", "Objects reviewed"), ("ok", "OK"),
                                       ("warning", "Warning"), ("critical", "Critical")))
    rows = []
    for obj in report["objects"]:
        age = f'{obj["age_hours"]:.2f}' if obj["age_hours"] is not None else "—"
        rows.append(f'<tr><td><b>{e(obj["object_name"])}</b></td>'
                    f'<td><span class="badge {obj["health"].lower()}">{obj["health"]}</span></td>'
                    f'<td>{e(obj["latest_status"])}</td><td>{e(obj["last_success"])}</td>'
                    f'<td>{age} / {obj["max_age_hours"]:g}</td>'
                    f'<td>{e("; ".join(obj["issues"]) or "Within configured age threshold")}</td>'
                    f'<td>{e(obj["latest_message"])}</td></tr>')
    failures = "".join(f'<tr><td>{e(job["object_name"])}</td><td>{e(job["timestamp"])}</td>'
                       f'<td>{e(job["message"])}</td></tr>' for job in report["failed_jobs"])
    if not failures:
        failures = '<tr><td colspan="3">No failed jobs in supplied history.</td></tr>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backup Health Report</title><style>
:root{{font-family:system-ui,Segoe UI,sans-serif;color:#17283a;background:#f1f5f9}}
body{{max-width:1440px;margin:0 auto;padding:32px 24px}}header{{border-top:5px solid #087e8b;padding:24px 0}}
.eyebrow{{font-size:12px;font-weight:700;letter-spacing:2px;color:#087e8b}}h1{{font-size:34px;margin:8px 0}}
h2{{font-size:21px;margin-top:32px}}p{{line-height:1.6}}.muted{{color:#526579}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}.card{{background:white;border:1px solid #dbe4ec;border-radius:10px;padding:20px}}
.card span{{display:block;color:#526579}}.card strong{{display:block;font-size:36px;margin-top:8px}}
.table-wrap{{overflow-x:auto;background:white;border:1px solid #dbe4ec;border-radius:10px}}
table{{width:100%;border-collapse:collapse;text-align:left;font-size:14px}}th{{background:#e9f0f6;padding:15px 12px}}
td{{padding:15px 12px;border-top:1px solid #e0e7ee;vertical-align:top;overflow-wrap:anywhere;min-width:90px}}
.badge{{display:inline-block;padding:5px 9px;border-radius:5px;font-size:11px;font-weight:750}}
.ok{{background:#d9f4e8;color:#125b3c}}.warning{{background:#fff0bf;color:#715000}}.critical{{background:#ffe1e3;color:#952537}}
.note{{padding:15px 18px;border-left:4px solid #087e8b;background:#e5f2f4}}footer{{font-size:12px;margin-top:30px;color:#526579}}
@media(max-width:650px){{body{{padding:16px}}.cards{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:28px}}}}
@media print{{body{{padding:0;background:white}}.table-wrap{{overflow:visible}}td{{min-width:0}}}}
</style></head><body><header><div class="eyebrow">IT BACKUP REPORT AUTOMATION</div>
<h1>Backup Health Report</h1><p class="muted">As of {e(report["as_of_utc"])} · {report["summary"]["jobs_in_export"]} job records evaluated</p></header>
<section class="cards" aria-label="Summary">{cards}</section>
<h2>Current object health</h2><p class="muted">Age / limit is in hours. Missing success history and latest failed or cancelled jobs are critical. Warnings and running jobs need review.</p>
<div class="table-wrap"><table><thead><tr><th>Object</th><th>Health</th><th>Latest status</th><th>Last success (UTC)</th><th>Age / limit</th><th>Finding</th><th>Latest message</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<h2>Failed jobs in supplied history</h2><p class="muted">Historical failures remain here even when a later successful job restores current health.</p>
<div class="table-wrap"><table><thead><tr><th>Object</th><th>Timestamp (UTC)</th><th>Message</th></tr></thead><tbody>{failures}</tbody></table></div>
<p class="note">{e(report["scope_note"])}</p><footer>Version {VERSION} · Generated locally · No external scripts, fonts, or network requests</footer></body></html>'''


def write_reports(report: dict, output_dir: Path, input_paths: list[Path]) -> None:
    inputs = {path.resolve() for path in input_paths}
    for name in OUTPUT_NAMES:
        if (output_dir / name).resolve() in inputs:
            raise InputError("Output would overwrite an input file; choose another --output-dir.")
    payloads = (render_html(report), render_csv(report), json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in zip(OUTPUT_NAMES, payloads):
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=output_dir,
                                             prefix=".backup-report-", delete=False) as handle:
                temp_name = handle.name
                handle.write(payload)
            os.replace(temp_name, output_dir / name)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Normalized job CSV export")
    source.add_argument("--demo", action="store_true", help="Run bundled fictional data at a fixed reference time")
    parser.add_argument("--inventory", type=Path, help="CSV of expected objects and optional age limits")
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    parser.add_argument("--max-age-hours", default="24", help="Default success age limit; default: 24")
    parser.add_argument("--now", help="Reference ISO timestamp with timezone; default: current UTC")
    parser.add_argument("--fail-on-alert", action="store_true", help="Exit 1 when any object is WARNING or CRITICAL")
    args = parser.parse_args(argv)
    try:
        limit = positive_hours(args.max_age_hours)
        if args.demo:
            if args.inventory or args.now:
                raise InputError("--demo already selects its inventory and reference time; use --input for custom data.")
            root = Path(__file__).resolve().parent
            args.input, args.inventory = root / "sample_jobs.csv", root / "sample_inventory.csv"
            now = parse_time(DEMO_TIME)
        else:
            now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        jobs = load_jobs(args.input, now)
        inventory = load_inventory(args.inventory, limit) if args.inventory else {}
        report = build_report(jobs, inventory, now, limit, args.inventory is not None)
        write_reports(report, args.output_dir, [args.input] + ([args.inventory] if args.inventory else []))
        summary = report["summary"]
        print(f"Objects: {summary['objects']} | OK: {summary['ok']} | Warning: {summary['warning']} | Critical: {summary['critical']}")
        print(f"Report: {(args.output_dir / OUTPUT_NAMES[0]).resolve()}")
        return 1 if args.fail_on_alert and (summary["warning"] or summary["critical"]) else 0
    except (InputError, OSError, UnicodeError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
