"""Live dashboard server (stdlib only).

Read-only view over the scraper:
  - serves dashboard/index.html + style.css + app.js
  - GET  /api/status     -> running?, niche/queries, probed, leads, elapsed, log tail
  - GET  /api/leads      -> parsed leads from newest data file (JSON or CSV)
  - GET  /api/export.csv -> CSV download of current leads
  - POST /api/run        -> spawn `python -u main.py ...` (never edits scraper)
  - POST /api/stop       -> stop the spawned run

Run via:  python dashboard/run.py
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import threading
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DASH = Path(__file__).resolve().parent
LOG_PATH = DASH / ".last_run.log"

KNOWN_NICHES = [
    "real_estate", "finance", "healthcare", "legal", "saas",
    "ecommerce", "coaching", "automotive", "hospitality",
]

# ---------------------------------------------------------------- state

_lock = threading.Lock()
_log = deque(maxlen=500)  # in-memory tail of current/prior run
_run = {
    "proc": None,          # subprocess.Popen | None
    "cmd": [],             # list[str]
    "cmd_str": "",
    "niches": [],
    "max": None,
    "out_file": "data/leads.csv",
    "seeds": "",
    "started_at": None,    # datetime | None
    "ended_at": None,      # datetime | None
    "exit_code": None,
    "queries_seen": [],
}
_leads_override = {"path": None}  # set via --leads


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------- quality (mirrors core/models.py, standalone copy)

def quality_score(emails, wa, ig, li, phones) -> int:
    s = 0
    s += min(len(emails), 5) * 12
    s += min(len(wa), 3) * 8
    s += min(len(ig), 3) * 5
    s += min(len(li), 3) * 4
    s += min(len(phones), 3) * 2
    if emails:
        s += 5
    if wa:
        s += 5
    return min(s, 100)


def quality_label(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


# ---------------------------------------------------------------- leads loading (read-only)

def _split(v: str) -> list:
    if not v:
        return []
    return [p.strip() for p in str(v).split(" | ") if p.strip()]


def _norm_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        # JSON sometimes stores a joined string; CSV always does.
        return _split(v) if " | " in v else ([v] if v.strip() else [])
    return [str(x).strip() for x in list(v) if str(x).strip()]


def _lead_from_any(item: dict) -> dict:
    emails = _norm_list(item.get("emails"))
    wa = _norm_list(item.get("whatsapp_numbers"))
    ig = _norm_list(item.get("instagram_handles"))
    li = _norm_list(item.get("linkedin_urls"))
    ph = _norm_list(item.get("phones"))
    try:
        score = int(item.get("quality_score", "") or 0)
    except (TypeError, ValueError):
        score = 0
    label = (item.get("quality_label") or "").strip().lower()
    if not label or label not in ("high", "medium", "low") or not item.get("quality_score"):
        score = quality_score(emails, wa, ig, li, ph)
        label = quality_label(score)
    return {
        "business_name": item.get("business_name") or "Unknown",
        "niche": item.get("niche") or "",
        "website": item.get("website") or "",
        "emails": emails,
        "whatsapp_numbers": wa,
        "instagram_handles": ig,
        "linkedin_urls": li,
        "phones": ph,
        "source_query": item.get("source_query") or "",
        "quality_label": label,
        "quality_score": score,
        "scraped_at": item.get("scraped_at") or "",
    }


def _host_key(url: str) -> str:
    """Stable merge key: bare hostname (no scheme/www/path)."""
    try:
        host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    except ValueError:
        return (url or "").lower()
    return host or (url or "").lower()


def candidate_files() -> list[Path]:
    cands: list[Path] = []
    if _leads_override["path"]:
        cands.append(Path(_leads_override["path"]))
    with _lock:
        out = _run.get("out_file") or ""
    if out:
        cands.append(ROOT / out if not Path(out).is_absolute() else Path(out))
    cands += [ROOT / "data" / "leads.json", ROOT / "data" / "leads.csv"]
    # Support the doc-mentioned `output/` CSV dir if a user points --out there.
    outdir = ROOT / "output"
    if outdir.is_dir():
        try:
            cands += sorted(
                (p for p in outdir.glob("*.csv") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:3]
        except OSError:
            pass
    # de-dupe, keep order
    seen, uniq = set(), []
    for p in cands:
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def _read_one(src: Path) -> list[dict]:
    if src.suffix.lower() == ".json":
        data = json.loads(src.read_text(encoding="utf-8"))
        items = data.get("leads", data) if isinstance(data, dict) else data
        return [_lead_from_any(x) for x in items if isinstance(x, dict)]
    with src.open(newline="", encoding="utf-8-sig") as fh:
        return [_lead_from_any(r) for r in csv.DictReader(fh)]


def _contacts_n(l: dict) -> int:
    return len(l["emails"]) + len(l["whatsapp_numbers"]) + len(l["instagram_handles"]) + len(l["linkedin_urls"]) + len(l["phones"])


def load_leads() -> tuple[list[dict], Path | None]:
    """Return (leads, newest_source). Merges all candidates in memory
    (display only, never writes) so idle state shows *all* last results
    even when data/leads.json and data/leads.csv diverge."""
    existing = []
    for p in candidate_files():
        try:
            ap = p if p.is_absolute() else (ROOT / p)
            if ap.is_file() and ap.stat().st_size > 0:
                existing.append(ap)
        except OSError:
            continue
    if not existing:
        return [], None
    existing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    merged: dict[str, dict] = {}
    for src in existing:
        try:
            for l in _read_one(src):
                key = _host_key(l["website"] or l["business_name"])
                if not key:
                    continue
                prev = merged.get(key)
                if prev is None or _contacts_n(l) >= _contacts_n(prev):
                    merged[key] = l
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    leads = sorted(merged.values(), key=lambda l: (l["quality_score"], l["scraped_at"]), reverse=True)
    return leads, existing[0]


# ---------------------------------------------------------------- log parsing

RE_SEARCH = re.compile(r"Searching:\s*(.+?)\s*$")
RE_PROBE = re.compile(r"Probing\s+(https?://\S+)")
RE_CACHED = re.compile(r"Using cached results for\s+(.+?)\s+\((\d+)\s+urls\)")
RE_COLLECTED = re.compile(r"collected\s+(\d+)\s+qualified leads for\s+(\S+)")
RE_EXPORT = re.compile(r"Exported\s+(\d+)\s+leads to\s+(CSV|JSON):\s*(\S+)")


def parse_log(lines: list[str]) -> dict:
    probed = 0
    searches = 0
    collected = 0
    per_niche: dict[str, int] = {}
    queries: list[str] = []
    cur_q, cur_u = "", ""
    for ln in lines:
        m = RE_SEARCH.search(ln)
        if m:
            searches += 1
            q = m.group(1).strip().strip("'\"")
            cur_q = q
            if q not in queries:
                queries.append(q)
        m = RE_PROBE.search(ln)
        if m:
            probed += 1
            cur_u = m.group(1)
        m = RE_COLLECTED.search(ln)
        if m:
            n = int(m.group(1))
            per_niche[m.group(2)] = n
    collected = sum(per_niche.values())
    return {
        "candidates_probed": probed,
        "searches": searches,
        "leads_collected": collected,
        "per_niche": per_niche,
        "current_query": cur_q,
        "current_url": cur_u,
        "queries_seen": queries[-12:],
    }


def is_running() -> bool:
    with _lock:
        p = _run["proc"]
        return p is not None and p.poll() is None


def build_status() -> dict:
    with _lock:
        snapshot_lines = list(_log)
        snap = dict(_run)
        proc = snap["proc"]
        running = proc is not None and proc.poll() is None
    stats = parse_log(snapshot_lines)
    leads, src = load_leads()
    now = utcnow()
    started = snap["started_at"]
    ended = snap["ended_at"]
    if running and started:
        elapsed = (now - started).total_seconds()
    elif started and ended:
        elapsed = (ended - started).total_seconds()
    elif started:
        elapsed = (now - started).total_seconds()
    else:
        elapsed = 0.0
    # live leads_found: during a run show log-collected, else file total
    file_total = len(leads)
    leads_found = stats["leads_collected"] if running else file_total
    if running:
        leads_found = max(leads_found, 0)
    niches = list(snap["niches"]) or sorted({l["niche"] for l in leads if l["niche"]})
    try:
        leads_mtime = (
            datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc).isoformat()
            if src and src.exists() else None
        )
    except OSError:
        leads_mtime = None
    return {
        "running": running,
        "pid": proc.pid if proc else None,
        "niche": ", ".join(snap["niches"]) if snap["niches"] else ("-" if not niches else ", ".join(niches)),
        "niches": snap["niches"] or niches,
        "max": snap["max"],
        "out_file": snap["out_file"],
        "cmd": snap["cmd_str"],
        "started_at": iso(started),
        "ended_at": iso(ended),
        "exit_code": None if running else snap["exit_code"],
        "elapsed_s": round(elapsed, 1),
        "candidates_probed": stats["candidates_probed"],
        "searches": stats["searches"],
        "leads_found": leads_found,
        "leads_total": file_total,
        "leads_collected_log": stats["leads_collected"],
        "per_niche": stats["per_niche"],
        "current_query": stats["current_query"],
        "current_url": stats["current_url"],
        "queries_seen": stats["queries_seen"] or snap["queries_seen"],
        "log_tail": snapshot_lines[-80:],
        "log_lines": len(snapshot_lines),
        "source_file": str(src.relative_to(ROOT)) if src and _is_under(src, ROOT) else (str(src) if src else None),
        "leads_mtime": leads_mtime,
        "updated_at": now.isoformat(),
    }


def _is_under(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- run spawning (display plumbing only)

def _append_log(line: str) -> None:
    with _lock:
        _log.append(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _reader(proc: subprocess.Popen) -> None:
    try:
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, ""):
            if raw == "":
                break
            _append_log(raw.rstrip("\n"))
    finally:
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        code = proc.poll()
        with _lock:
            _run["ended_at"] = utcnow()
            _run["exit_code"] = code
        _append_log(f"### EXIT code={code} at {utcnow().isoformat()}")
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass


def _os_windows() -> bool:
    import os
    return os.name == "nt"


def _resolve_python() -> str:
    """Best interpreter to spawn the scraper with.

    Prefer the project virtualenv so the dashboard "Run" button works no
    matter how the server itself was started. Falls back to the current
    interpreter (e.g. when there is no .venv).
    """
    import sys
    rel = Path("Scripts") / "python.exe" if _os_windows() else Path("bin") / "python"
    venv_py = ROOT / ".venv" / rel
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _resolve_niche_ids() -> list:
    """Niche ids from the scraper config when importable, else builtin list."""
    try:
        from config.niches import all_niche_ids
        return all_niche_ids()
    except Exception:  # noqa: BLE001
        return KNOWN_NICHES


def start_run(opts: dict) -> tuple[bool, dict]:
    niche_opts = _resolve_niche_ids()
    niche = opts.get("niche") or [niche_opts[0]]
    if isinstance(niche, str):
        niche = [n.strip() for n in niche.replace(",", " ").split() if n.strip()]
    niche = [n for n in niche if n in niche_opts] or [niche_opts[0]]
    try:
        max_leads = max(1, min(int(opts.get("max", 6)), 500))
    except (TypeError, ValueError):
        max_leads = 6
    out = str(opts.get("out") or "data/leads.csv").strip() or "data/leads.csv"
    # confine --out to repo tree (never absolute-escape / scraper dirs are untouched anyway)
    if Path(out).is_absolute():
        out = "data/leads.csv"
    seeds = str(opts.get("seeds") or "").strip()
    if seeds and (".." in seeds or seeds.startswith("/")):
        seeds = ""
    try:
        workers = int(opts.get("workers") or 2)
        workers = max(1, min(workers, 8))
    except (TypeError, ValueError):
        workers = 2

    with _lock:
        p = _run["proc"]
        if p is not None and p.poll() is None:
            return False, {"error": "a scrape is already running", "pid": p.pid}

    py = _resolve_python()  # venv-aware: works from any interpreter
    cmd = [py, "-u", "main.py", "--niche", *niche, "--max", str(max_leads),
           "--out", out, "--workers", str(workers)]
    if seeds:
        cmd += ["--seeds", seeds]
    if opts.get("emails_only"):
        cmd += ["--emails-only"]
    try:
        mq = int(opts.get("min_quality") or 0)
        if mq > 0:
            cmd += ["--min-quality", str(max(1, min(mq, 100)))]
    except (TypeError, ValueError):
        pass
    try:
        mx = int(opts.get("max_quality") or 100)
        if mx < 100:
            cmd += ["--max-quality", str(max(0, min(mx, 100)))]
    except (TypeError, ValueError):
        pass
    if opts.get("no_enrich"):
        cmd += ["--no-enrich"]

    # friendly display string (quote only paths with spaces)
    def q(a: str) -> str:
        return f'"{a}"' if " " in a else a

    cmd_str = " ".join(q(a) for a in cmd)

    try:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except OSError as exc:
        return False, {"error": f"failed to launch scraper: {exc}"}

    with _lock:
        _run.update(proc=proc, cmd=cmd, cmd_str=cmd_str, niches=niche,
                    max=max_leads, out_file=out, seeds=seeds,
                    started_at=utcnow(), ended_at=None, exit_code=None,
                    queries_seen=[])
    _append_log(f"### START {utcnow().isoformat()} :: {cmd_str}")
    t = threading.Thread(target=_reader, args=(proc,), daemon=True)
    t.start()
    return True, {"pid": proc.pid, "cmd": cmd_str}


def stop_run() -> dict:
    with _lock:
        p = _run["proc"]
    if p is None or p.poll() is not None:
        return {"ok": True, "running": False}
    try:
        p.terminate()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    _append_log("### STOP requested by dashboard")
    return {"ok": True, "running": True}


def load_persisted_log() -> None:
    try:
        if LOG_PATH.is_file():
            tail = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
            with _lock:
                _log.clear()
                _log.extend(tail)
                # recover last START cmd for idle display
                for ln in reversed(tail):
                    if ln.startswith("### START"):
                        parts = ln.split("::", 1)
                        if len(parts) == 2:
                            _run["cmd_str"] = parts[1].strip()
                        break
    except OSError:
        pass


# ---------------------------------------------------------------- HTTP

MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".json": "application/json",
        ".csv": "text/csv; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadDash/1.0"

    def log_message(self, *a):  # quiet; dashboard has its own log view
        pass

    # -- helpers
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _static(self, name: str):
        target = (DASH / name).resolve()
        if not str(target).startswith(str(DASH.resolve())) or not target.is_file():
            self._json({"error": "not found"}, 404)
            return
        self._send(200, target.read_bytes(), MIME.get(target.suffix, "application/octet-stream"))

    # -- routes
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path in ("/style.css", "/app.js"):
            return self._static(path.lstrip("/"))
        if path == "/api/status":
            return self._json(build_status())
        if path == "/api/leads":
            leads, src = load_leads()
            niches = sorted({l["niche"] for l in leads if l["niche"]})
            return self._json({
                "leads": leads, "total": len(leads),
                "source_file": str(src.relative_to(ROOT)) if src and _is_under(src, ROOT)
                else (str(src) if src else None),
                "niches": niches,
                "updated_at": utcnow().isoformat(),
            })
        if path in ("/api/export.csv", "/export.csv"):
            leads, _ = load_leads()
            import io
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["business_name", "niche", "website", "emails", "whatsapp_numbers",
                        "instagram_handles", "linkedin_urls", "phones", "source_query",
                        "quality_label", "quality_score", "scraped_at"])
            for l in leads:
                w.writerow([l["business_name"], l["niche"], l["website"],
                            " | ".join(l["emails"]), " | ".join(l["whatsapp_numbers"]),
                            " | ".join(l["instagram_handles"]), " | ".join(l["linkedin_urls"]),
                            " | ".join(l["phones"]), l["source_query"],
                            l["quality_label"], l["quality_score"], l["scraped_at"]])
            raw = ("\ufeff" + buf.getvalue()).encode("utf-8")
            return self._send(200, raw, "text/csv; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="leads.csv"'})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            opts = json.loads(raw.decode() or "{}") if raw else {}
            if not isinstance(opts, dict):
                opts = {}
        except (ValueError, UnicodeDecodeError):
            opts = {}
        if path == "/api/run":
            ok, info = start_run(opts)
            return self._json(info, 200 if ok else 409)
        if path == "/api/stop":
            return self._json(stop_run())
        return self._json({"error": "not found"}, 404)


def serve(host="127.0.0.1", port=8765, leads: str | None = None):
    if leads:
        _leads_override["path"] = leads
    load_persisted_log()
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv
