"""Export collected leads to CSV or JSON.

Format is chosen by file extension:
  .csv  -> one row per lead, multi-value fields joined with " | "
  .json -> structured payload with nested contact lists
"""

import csv
import json
import logging
from pathlib import Path

from core.models import CSV_HEADERS, Lead

logger = logging.getLogger(__name__)


def export_leads(leads: list[Lead], path: str) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.suffix.lower() == ".json":
        _export_json(leads, out_path)
    else:
        _export_csv(leads, out_path)
    return out_path


def _export_csv(leads: list[Lead], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADERS)
        for lead in leads:
            writer.writerow(lead.flat_row())
    logger.info("Exported %d leads to CSV: %s", len(leads), path)


def _export_json(leads: list[Lead], path: Path) -> None:
    payload = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "lead_count": len(leads),
        "leads": [lead.to_dict() for lead in leads],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Exported %d leads to JSON: %s", len(leads), path)


def dedupe_leads(leads: list[Lead], key="website") -> list:
    """Remove leads sharing the same unique key (default: website)."""
    seen: set = set()
    result: list = []
    for lead in leads:
        value = getattr(lead, key) or ""
        value = value.lower()
        if value in seen:
            continue
        seen.add(value)
        result.append(lead)
    return result