"""Export collected leads to CSV or JSON.

Format is chosen by file extension:
  .csv  -> one row per lead, multi-value fields joined with " | "
  .json -> structured payload with nested contact lists

Supports incremental runs: export_leads can merge new leads into an
existing output file (default) so every run builds on the last one.
"""

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from core.filter import is_provider_name, url_is_denied
from core.models import CSV_HEADERS, Lead

logger = logging.getLogger(__name__)


def purge_invalid(leads: list) -> list:
    """Drop leads that current filters now reject (denied hosts or known
    marketing/lead-gen providers). Makes the dataset self-healing: re-running
    against an old output file cleans junk collected by earlier pipelines."""
    kept = []
    dropped = 0
    for lead in leads:
        if url_is_denied(lead.website or "") or is_provider_name(lead.business_name or ""):
            dropped += 1
            continue
        kept.append(lead)
    if dropped:
        logger.info("Purged %d leads with denied hosts / provider names", dropped)
    return kept


def _host_key(url: str) -> str:
    """Normalise a website URL to a stable merge key (host, no www/scheme)."""
    try:
        host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
        return host or (url or "").lower()
    except ValueError:
        return (url or "").lower()


def load_leads(path: str) -> list:
    """Load previously exported leads from CSV or JSON, or [] when missing."""
    out_path = Path(path)
    if not out_path.exists():
        return []
    try:
        if out_path.suffix.lower() == ".json":
            data = json.loads(out_path.read_text(encoding="utf-8"))
            return [_lead_from_dict(item) for item in data.get("leads", [])]
        with out_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            return [_lead_from_csv(row) for row in reader]
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("Could not read existing output %s: %s", path, exc)
        return []


def _lead_from_dict(item: dict) -> Lead:
    lead = Lead(
        business_name=item.get("business_name") or "Unknown",
        niche=item.get("niche", "") or "",
        website=item.get("website") or None,
        emails=list(item.get("emails") or []),
        whatsapp_numbers=list(item.get("whatsapp_numbers") or []),
        instagram_handles=list(item.get("instagram_handles") or []),
        linkedin_urls=list(item.get("linkedin_urls") or []),
        phones=list(item.get("phones") or []),
        source_query=item.get("source_query") or None,
        email_origin=item.get("email_origin") or "scraped",
        scraped_at=item.get("scraped_at") or datetime.now(timezone.utc).isoformat(),
    )
    return lead


def _lead_from_csv(row: dict) -> Lead:
    def split(val):
        return [v for v in (val or "").split(" | ") if v]

    return Lead(
        business_name=row.get("business_name") or "Unknown",
        niche=row.get("niche", "") or "",
        website=(row.get("website") or "").strip() or None,
        emails=split(row.get("emails")),
        whatsapp_numbers=split(row.get("whatsapp_numbers")),
        instagram_handles=split(row.get("instagram_handles")),
        linkedin_urls=split(row.get("linkedin_urls")),
        phones=split(row.get("phones")),
        source_query=row.get("source_query") or None,
        email_origin=row.get("email_origin") or "scraped",
        scraped_at=row.get("scraped_at") or datetime.now(timezone.utc).isoformat(),
    )


def merge_leads(new_leads: list, existing: list) -> list:
    """Merge new leads into existing, keeping unique websites and the richer
    version of any duplicate (more contact points wins)."""
    merged: dict[str, Lead] = {}
    for lead in list(existing) + list(new_leads):
        key = _host_key(lead.website or "")
        if not key:
            continue
        prev = merged.get(key)
        if prev is None or len(_contact_count(lead)) >= len(_contact_count(prev)):
            merged[key] = lead
    return sorted(merged.values(), key=lambda l: l.quality_score, reverse=True)


def _contact_count(lead: Lead) -> list:
    return (
        lead.emails
        + lead.whatsapp_numbers
        + lead.instagram_handles
        + lead.linkedin_urls
        + lead.phones
    )


def export_leads(leads: list, path: str, *, merge: bool = True) -> Path:
    """Write leads to the output file, optionally merging prior results."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    to_write = list(leads)
    if merge and out_path.exists():
        existing = purge_invalid(load_leads(path))
        if existing:
            to_write = merge_leads(leads, existing)
            logger.info("Merged %d new leads with %d existing -> %d total",
                        len(leads), len(existing), len(to_write))

    to_write = purge_invalid(to_write)
    to_write = sorted(to_write, key=lambda l: l.quality_score, reverse=True)

    if out_path.suffix.lower() == ".json":
        _export_json(to_write, out_path)
    else:
        _export_csv(to_write, out_path)
    return out_path


def _export_csv(leads: list[Lead], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADERS)
        for lead in leads:
            writer.writerow(lead.flat_row())
    logger.info("Exported %d leads to CSV: %s", len(leads), path)


def _export_json(leads: list[Lead], path: Path) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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