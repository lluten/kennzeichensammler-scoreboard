#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import zlib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable


DATE_FORMAT = "%d.%m.%Y"
SITE_DIRS_TO_SKIP = {"assets", "data", "example", "profiles", "scripts", ".git", "__pycache__"}
ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "index.html"
PROFILES_DIR = ROOT / "profiles"
DATA_DIR = ROOT / "data"
FRIENDS_DIR = DATA_DIR / "friends"
CATALOG_PATH = DATA_DIR / "catalog.db"

# Backup `land` values mapped into the three profile tabs.
LAND_CATEGORY_MAP = {
    "deutschland": "germany",
    "germany": "germany",
    "de": "germany",
    "laender": "europe",
    "länder": "europe",
    "europe": "europe",
    "europa": "europe",
    "austria": "europe",
    "oesterreich": "europe",
    "schweiz": "europe",
    "bulgarien": "europe",
    "frankreich": "europe",
    "greece": "europe",
    "irland": "europe",
    "italien": "europe",
    "kosovo": "europe",
    "kroatien": "europe",
    "luxemburg": "europe",
    "moldawien": "europe",
    "montenegro": "europe",
    "nmk": "europe",
    "norwegen": "europe",
    "polen": "europe",
    "romania": "europe",
    "russland": "europe",
    "serbien": "europe",
    "slowakei": "europe",
    "slowenien": "europe",
    "tschechien": "europe",
    "turkey": "europe",
    "uk": "europe",
    "uk2": "europe",
    "ukraine": "europe",
    "belarus": "europe",
    "usa": "usa",
    "us": "usa",
    "amerika": "usa",
    "america": "usa",
}

CATEGORY_META = {
    "germany": {"id": "germany", "label": "Germany", "catalog_lands": ["deutschland"]},
    "europe": {
        "id": "europe",
        "label": "Europe",
        "catalog_lands": [
            "laender",
            "austria",
            "schweiz",
            "bulgarien",
            "frankreich",
            "greece",
            "irland",
            "italien",
            "kosovo",
            "kroatien",
            "luxemburg",
            "moldawien",
            "montenegro",
            "nmk",
            "norwegen",
            "polen",
            "romania",
            "russland",
            "serbien",
            "slowakei",
            "slowenien",
            "tschechien",
            "turkey",
            "uk",
            "uk2",
            "ukraine",
            "belarus",
        ],
    },
    "usa": {"id": "usa", "label": "USA", "catalog_lands": ["usa"]},
}


@dataclass
class CatalogEntry:
    kennid: int
    land: str
    code: str
    name: str
    region: str
    points: int


class RegionCatalog:
    """Lookup plate codes/names from the app's catalog database."""

    def __init__(self, path: Path):
        self.path = path
        self.by_land_id: dict[tuple[str, int], CatalogEntry] = {}
        self.by_category: dict[str, list[CatalogEntry]] = {
            "germany": [],
            "europe": [],
            "usa": [],
        }
        if path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            if table in {"global", "global2"}:
                continue
            cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
            if not {"id", "kennzeichen", "ort"}.issubset(cols):
                continue
            for row in conn.execute(
                f'SELECT id, kennzeichen, ort, bundesland, punkte, land FROM "{table}"'
            ):
                kennid = int(row["id"])
                if kennid <= 1:
                    continue
                land = str(row["land"] or table).strip().lower()
                code = str(row["kennzeichen"] or "").strip()
                name = str(row["ort"] or "").strip() or code or str(kennid)
                region = str(row["bundesland"] or "").strip()
                points = int(row["punkte"] or 0)
                entry = CatalogEntry(
                    kennid=kennid,
                    land=land,
                    code=code or str(kennid),
                    name=name,
                    region=region,
                    points=points,
                )
                self.by_land_id[(land, kennid)] = entry
                category = LAND_CATEGORY_MAP.get(land, "europe")
                self.by_category[category].append(entry)
        conn.close()
        for category_id, entries in self.by_category.items():
            # Deduplicate by (land, kennid) while keeping stable code order.
            unique = {}
            for entry in entries:
                unique[(entry.land, entry.kennid)] = entry
            self.by_category[category_id] = sorted(
                unique.values(),
                key=lambda item: (item.code.lower(), item.name.lower(), item.kennid),
            )

    def lookup(self, land: str, kennid: int) -> CatalogEntry | None:
        return self.by_land_id.get((land.strip().lower(), int(kennid)))

    def label_for(self, land: str, kennid: int) -> str:
        entry = self.lookup(land, kennid)
        if not entry:
            return str(kennid)
        if entry.code and entry.name and entry.code != entry.name:
            return f"{entry.code} — {entry.name}"
        return entry.code or entry.name or str(kennid)


@dataclass
class BackupSource:
    friend_id: str
    display_name: str
    path: Path


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = []
    last_dash = False
    for char in lowered:
        if char.isalnum():
            cleaned.append(char)
            last_dash = False
        else:
            if not last_dash:
                cleaned.append("-")
            last_dash = True
    slug = "".join(cleaned).strip("-")
    return slug or "collector"


def parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, DATE_FORMAT).date()


def format_date_iso(date_obj) -> str:
    return date_obj.isoformat()


def format_date_label(date_obj) -> str:
    return date_obj.strftime("%d.%m.%Y")


def parse_backup_date_from_name(file_name: str):
    """Extract DD.MM.YYYY from backup filenames like KennzeichensammlerBackupX-15.07.2026."""
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", file_name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), DATE_FORMAT).date()
    except ValueError:
        return None


def backup_sort_key(path: Path):
    """Prefer newer embedded filename dates; fall back to filename text."""
    parsed = parse_backup_date_from_name(path.name)
    return (parsed is not None, parsed or date.min, path.name)


def detect_backup_bytes(path: Path) -> bytes | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        payload = zlib.decompress(raw)
    except zlib.error:
        return None
    if not payload.startswith(b"KX1SQLite format 3\x00"):
        return None
    return payload[3:]


def discover_backups(root: Path) -> list[BackupSource]:
    """Expect backups/<FriendName>/<backup-file> and name collectors from the folder."""
    backups: list[BackupSource] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if any(part in SITE_DIRS_TO_SKIP for part in path.parts if part != root.name):
            continue
        relative = path.relative_to(root)
        # Require a friend folder: skip loose files directly under the input root.
        if len(relative.parts) < 2:
            continue
        friend_token = relative.parts[0]
        if friend_token.startswith("."):
            continue
        sqlite_bytes = detect_backup_bytes(path)
        if sqlite_bytes is None:
            continue
        backups.append(
            BackupSource(
                friend_id=slugify(friend_token),
                display_name=friend_token.strip(),
                path=path,
            )
        )
    deduped: dict[str, BackupSource] = {}
    for backup in backups:
        existing = deduped.get(backup.friend_id)
        if existing is None or backup_sort_key(backup.path) > backup_sort_key(existing.path):
            deduped[backup.friend_id] = backup
    return sorted(deduped.values(), key=lambda item: item.display_name.lower())


def fetch_rows_from_backup(path: Path) -> list[dict[str, str | int]]:
    sqlite_bytes = detect_backup_bytes(path)
    if sqlite_bytes is None:
        raise ValueError(f"{path} is not a supported backup file")

    # sqlite3 on this machine can open a temporary file more reliably than an in-memory URI.
    temp_path = ROOT / ".tmp_decode.sqlite"
    temp_path.write_bytes(sqlite_bytes)
    try:
        conn = sqlite3.connect(temp_path)
        conn.row_factory = sqlite3.Row
        rows = [
            {
                "kennid": int(row["kennid"]),
                "datum": str(row["datum"]),
                "land": str(row["land"]),
            }
            for row in conn.execute(
                "SELECT kennid, datum, land FROM gesehen ORDER BY datum ASC, kennid ASC"
            ).fetchall()
        ]
        conn.close()
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return rows


def compute_streak(active_dates: Iterable) -> int:
    ordered = sorted(set(active_dates))
    if not ordered:
        return 0
    best = 1
    current = 1
    for previous, current_date in zip(ordered, ordered[1:]):
        if current_date == previous + timedelta(days=1):
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def land_to_category(land: str) -> str:
    key = land.strip().lower()
    return LAND_CATEGORY_MAP.get(key, "europe" if key else "germany")


def activity_level(count: int, thresholds: list[int]) -> int:
    if count <= 0:
        return 0
    level = 1
    for index, threshold in enumerate(thresholds, start=1):
        if count >= threshold:
            level = index
    return min(level, 4)


def build_calendar_heatmap(sightings_per_day: Counter, last_date) -> list[dict]:
    """Build a GitHub-style calendar covering ~52 weeks ending on last_date."""
    # Align end to last activity; start on the Sunday of the week 52 weeks earlier.
    end = last_date
    start = end - timedelta(days=52 * 7 - 1)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # Sunday-start like GitHub

    positive_counts = [count for count in sightings_per_day.values() if count > 0]
    if positive_counts:
        ordered = sorted(positive_counts)
        thresholds = [
            ordered[0],
            ordered[max(0, len(ordered) // 3)],
            ordered[max(0, (2 * len(ordered)) // 3)],
            ordered[-1],
        ]
        # Ensure strictly increasing thresholds where possible.
        for index in range(1, 4):
            thresholds[index] = max(thresholds[index], thresholds[index - 1])
    else:
        thresholds = [1, 2, 3, 4]

    days = []
    cursor = start
    while cursor <= end:
        count = int(sightings_per_day.get(cursor, 0))
        days.append(
            {
                "date": format_date_iso(cursor),
                "label": format_date_label(cursor),
                "count": count,
                "level": activity_level(count, thresholds),
            }
        )
        cursor += timedelta(days=1)
    return days


def build_region_categories(parsed_rows: list[dict], catalog: RegionCatalog) -> dict:
    """Group collected kennids into Germany / Europe / USA tabs with catalog names."""
    collected: dict[str, dict[tuple[str, int], dict]] = {
        "germany": {},
        "europe": {},
        "usa": {},
    }

    for row in parsed_rows:
        land = str(row["land"])
        category = land_to_category(land)
        kennid = int(row["kennid"])
        key = (land.strip().lower(), kennid)
        entry = catalog.lookup(land, kennid)
        bucket = collected[category].setdefault(
            key,
            {
                "kennid": kennid,
                "land": land,
                "code": entry.code if entry else str(kennid),
                "name": entry.name if entry else str(kennid),
                "region": entry.region if entry else "",
                "label": catalog.label_for(land, kennid),
                "count": 0,
                "collected": True,
                "firstSeenDate": format_date_iso(row["date"]),
                "points": entry.points if entry else 0,
            },
        )
        bucket["count"] += 1
        if row["date"].isoformat() < bucket["firstSeenDate"]:
            bucket["firstSeenDate"] = format_date_iso(row["date"])

    categories = {}
    for category_id, meta in CATEGORY_META.items():
        collected_items = list(collected[category_id].values())
        collected_keys = {(item["land"].strip().lower(), item["kennid"]) for item in collected_items}
        catalog_total = len(catalog.by_category.get(category_id, []))
        # Prefer listing collected regions with real names; include zeros from catalog
        # only when the category is small enough to stay readable.
        items = sorted(
            collected_items,
            key=lambda item: (-item["count"], item["code"].lower(), item["name"].lower()),
        )
        if catalog_total and catalog_total <= 80:
            for entry in catalog.by_category[category_id]:
                key = (entry.land, entry.kennid)
                if key in collected_keys:
                    continue
                items.append(
                    {
                        "kennid": entry.kennid,
                        "land": entry.land,
                        "code": entry.code,
                        "name": entry.name,
                        "region": entry.region,
                        "label": f"{entry.code} — {entry.name}" if entry.code != entry.name else entry.code,
                        "count": 0,
                        "collected": False,
                        "firstSeenDate": None,
                        "points": entry.points,
                        "share": 0.0,
                    }
                )
        total = sum(item["count"] for item in items)
        for item in items:
            item["share"] = round(item["count"] / total, 4) if total else 0.0
        categories[category_id] = {
            "id": category_id,
            "label": meta["label"],
            "uniqueCount": len(collected_items),
            "catalogTotal": catalog_total,
            "completion": round(len(collected_items) / catalog_total, 4) if catalog_total else None,
            "totalSightings": total,
            "items": items,
        }
    return categories


def build_friend_stats(
    friend_id: str,
    display_name: str,
    rows: list[dict[str, str | int]],
    catalog: RegionCatalog,
) -> dict:
    parsed_rows = [
        {
            "kennid": int(row["kennid"]),
            "datum": str(row["datum"]),
            "land": str(row["land"]),
            "date": parse_date(str(row["datum"])),
        }
        for row in rows
    ]
    parsed_rows.sort(key=lambda row: (row["date"], row["kennid"], row["land"]))
    total_sightings = len(parsed_rows)
    unique_kennids = len({row["kennid"] for row in parsed_rows})
    active_dates = [row["date"] for row in parsed_rows]
    first_date = min(active_dates)
    last_date = max(active_dates)
    active_days = len(set(active_dates))
    span_days = (last_date - first_date).days + 1
    repeat_sightings = total_sightings - unique_kennids
    repeat_rate = repeat_sightings / total_sightings if total_sightings else 0.0
    discovery_efficiency = unique_kennids / total_sightings if total_sightings else 0.0
    activity_consistency = active_days / span_days if span_days else 0.0
    longest_streak = compute_streak(active_dates)

    land_counts = Counter(row["land"] for row in parsed_rows)
    sightings_per_day = Counter(row["date"] for row in parsed_rows)
    seen_kennids: set[int] = set()
    cumulative_unique = 0
    cumulative_total = 0
    daily_rollup: dict = {}
    first_seen_rows = []

    for row in parsed_rows:
        row_date = row["date"]
        if row["kennid"] not in seen_kennids:
            seen_kennids.add(row["kennid"])
            cumulative_unique += 1
            entry = catalog.lookup(str(row["land"]), int(row["kennid"]))
            first_seen_rows.append(
                {
                    "kennid": row["kennid"],
                    "firstSeenDate": format_date_iso(row_date),
                    "land": row["land"],
                    "category": land_to_category(str(row["land"])),
                    "label": catalog.label_for(str(row["land"]), int(row["kennid"])),
                    "code": entry.code if entry else str(row["kennid"]),
                }
            )
            is_new = True
        else:
            is_new = False
        cumulative_total += 1
        bucket = daily_rollup.setdefault(
            row_date,
            {
                "date": format_date_iso(row_date),
                "label": format_date_label(row_date),
                "totalSightings": 0,
                "newDiscoveries": 0,
                "repeatSightings": 0,
                "cumulativeSightings": 0,
                "cumulativeUniqueKennids": 0,
            },
        )
        bucket["totalSightings"] += 1
        if is_new:
            bucket["newDiscoveries"] += 1
        else:
            bucket["repeatSightings"] += 1
        bucket["cumulativeSightings"] = cumulative_total
        bucket["cumulativeUniqueKennids"] = cumulative_unique

    daily_series = [daily_rollup[date_obj] for date_obj in sorted(daily_rollup)]
    best_total_day = max(daily_series, key=lambda day: (day["totalSightings"], day["date"]))
    best_new_day = max(daily_series, key=lambda day: (day["newDiscoveries"], day["date"]))
    region_categories = build_region_categories(parsed_rows, catalog)
    calendar_heatmap = build_calendar_heatmap(sightings_per_day, last_date)

    profile = {
        "friendId": friend_id,
        "displayName": display_name,
        "sourceBackup": "",
        "stats": {
            "totalSightings": total_sightings,
            "uniqueKennids": unique_kennids,
            "activeDays": active_days,
            "firstSeenDate": format_date_iso(first_date),
            "lastSeenDate": format_date_iso(last_date),
            "spanDays": span_days,
            "repeatSightings": repeat_sightings,
            "repeatRate": round(repeat_rate, 4),
            "newDiscoveries": unique_kennids,
            "discoveryEfficiency": round(discovery_efficiency, 4),
            "activityConsistency": round(activity_consistency, 4),
            "longestStreakDays": longest_streak,
            "bestDayBySightings": best_total_day,
            "bestDayByUniqueDiscoveries": best_new_day,
            "averageSightingsPerActiveDay": round(total_sightings / active_days, 2) if active_days else 0.0,
            "germanyUnique": region_categories["germany"]["uniqueCount"],
            "europeUnique": region_categories["europe"]["uniqueCount"],
            "usaUnique": region_categories["usa"]["uniqueCount"],
        },
        "landBreakdown": [
            {"land": land, "count": count, "share": round(count / total_sightings, 4)}
            for land, count in sorted(land_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "regionCategories": region_categories,
        "series": {
            "dailyActivity": daily_series,
            "calendarHeatmap": calendar_heatmap,
        },
        "firstSeenKennids": first_seen_rows,
        "recentHighlights": [
            f"{unique_kennids} unique Kennzeichen IDs collected",
            f"{active_days} active day{'s' if active_days != 1 else ''} across the archive",
            f"{len(land_counts)} land bucket{'s' if len(land_counts) != 1 else ''} represented",
        ],
    }
    return profile


def build_awards(friends: list[dict]) -> list[dict]:
    if not friends:
        return []

    def winner(metric_name: str, title: str, context: str, formatter):
        champ = max(friends, key=lambda friend: friend["stats"][metric_name])
        return {
            "title": title,
            "value": formatter(champ["stats"][metric_name]),
            "context": context,
            "winner": champ["displayName"],
        }

    total_activity = winner(
        "totalSightings",
        "most active",
        "total logged sightings",
        lambda value: f"{value}",
    )
    unique_champion = winner(
        "uniqueKennids",
        "sharpest scout",
        "distinct Kennzeichen IDs discovered",
        lambda value: f"{value}",
    )
    streak_champion = winner(
        "longestStreakDays",
        "longest streak",
        "consecutive active days",
        lambda value: f"{value} days",
    )
    efficiency_champion = winner(
        "discoveryEfficiency",
        "best efficiency",
        "unique IDs per logged sighting",
        lambda value: f"{value * 100:.0f}%",
    )
    return [unique_champion, total_activity, streak_champion, efficiency_champion]


def build_manifest(friends: list[dict]) -> dict:
    ranked = sorted(
        friends,
        key=lambda friend: (
            -friend["stats"]["uniqueKennids"],
            -friend["stats"]["totalSightings"],
            friend["displayName"].lower(),
        ),
    )
    for index, friend in enumerate(ranked, start=1):
        friend["rank"] = index
        friend["profilePath"] = f"profiles/{friend['friendId']}.html"

    leaderboard = [
        {
            "rank": friend["rank"],
            "friendId": friend["friendId"],
            "displayName": friend["displayName"],
            "profilePath": friend["profilePath"],
            "stats": {
                "uniqueKennids": friend["stats"]["uniqueKennids"],
                "totalSightings": friend["stats"]["totalSightings"],
                "activeDays": friend["stats"]["activeDays"],
                "lastSeenDate": friend["stats"]["lastSeenDate"],
                "newDiscoveries": friend["stats"]["newDiscoveries"],
                "repeatRate": friend["stats"]["repeatRate"],
                "discoveryEfficiency": friend["stats"]["discoveryEfficiency"],
            },
            "hoverInfo": [
                f"unique Kennzeichen IDs: {friend['stats']['uniqueKennids']}",
                f"total sightings: {friend['stats']['totalSightings']}",
                f"active days: {friend['stats']['activeDays']}",
                f"Germany: {friend['stats']['germanyUnique']} · Europe: {friend['stats']['europeUnique']} · USA: {friend['stats']['usaUnique']}",
            ],
        }
        for friend in ranked
    ]

    return {
        "generatedAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "friendCount": len(ranked),
        "leaderboard": leaderboard,
        "awards": build_awards(ranked),
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def render_index_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kennzeichensammler Scoreboard</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body data-page="leaderboard">
    <div class="container">
        <header class="page-header">
            <p class="eyebrow">kennzeichen sammler</p>
            <h1>Kennzeichensammler</h1>
            <p class="page-intro">Live rankings from the latest shared backups. Hover a collector for a quick region split.</p>
        </header>

        <div class="page-layout">
            <main class="main-panel">
                <div class="section-heading">
                    <h2>overall rankings</h2>
                    <p>Hover a collector for unique IDs, activity, and region coverage.</p>
                </div>

                <div class="leaderboard-meta" id="leaderboard-meta"></div>
                <div class="leaderboard" id="leaderboard"></div>
            </main>

            <aside class="awards-section">
                <div class="section-heading">
                    <h2>achievements</h2>
                    <p>Interesting patterns we can derive from the current backup format.</p>
                </div>

                <div class="awards-list" id="awards-list"></div>
            </aside>
        </div>
    </div>

    <script src="assets/app.js"></script>
</body>
</html>
"""


def render_profile_html(friend_id: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>collector profile</title>
    <link rel="stylesheet" href="../assets/style.css">
</head>
<body data-page="profile" data-friend-id="{friend_id}">
    <div class="container">
        <a href="../index.html" class="back-link">back to leaderboard</a>

        <header class="profile-header">
            <p class="eyebrow">collector profile</p>
            <h1 id="profile-title">Collector statistics</h1>
            <p class="page-intro" id="profile-intro">Build-time statistics derived from the latest committed backup file.</p>
        </header>

        <div class="stats-grid" id="profile-stats"></div>

        <section class="main-panel profile-wide-panel">
            <div class="section-heading">
                <h2>activity over time</h2>
                <p>Contribution-style heatmap of daily sightings. Light tiles are inactive days.</p>
            </div>
            <div class="chart-card heatmap-card">
                <div class="chart-frame heatmap-frame" id="activity-chart"></div>
            </div>
        </section>

        <div class="profile-layout">
            <section class="main-panel">
                <div class="section-heading">
                    <h2>region progress</h2>
                    <p>Subregions collected in the backup, grouped by Germany, Europe, and USA.</p>
                </div>
                <div class="region-tabs" id="region-tabs" role="tablist" aria-label="Region categories"></div>
                <div class="region-panel" id="region-panel"></div>
            </section>

            <aside class="awards-section">
                <div class="section-heading">
                    <h2>collector snapshot</h2>
                    <p>Extra metrics derived from the current backup schema.</p>
                </div>
                <div class="awards-list" id="profile-highlights"></div>
            </aside>
        </div>
    </div>

    <script src="../assets/app.js"></script>
</body>
</html>
"""


def write_static_pages(manifest: dict, friend_payloads: list[dict]) -> None:
    INDEX_PATH.write_text(render_index_html(), encoding="utf-8")
    for friend in friend_payloads:
        profile_path = PROFILES_DIR / f"{friend['friendId']}.html"
        profile_path.write_text(render_profile_html(friend["friendId"]), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static scoreboard data and pages from Kennzeichensammler backups.")
    parser.add_argument(
        "--input-root",
        default=str(ROOT / "backups"),
        help="Directory to scan recursively for backup files (default: backups/).",
    )
    args = parser.parse_args()

    input_root = Path(args.input_root).resolve()
    if not input_root.exists():
        print(f"Input root does not exist yet: {input_root}")
        return

    backups = discover_backups(input_root)
    if not backups:
        print(f"No supported backup files found under {input_root}")
        return

    catalog = RegionCatalog(CATALOG_PATH)
    if catalog.by_land_id:
        print(f"Loaded catalog with {len(catalog.by_land_id)} region entries from {CATALOG_PATH.name}")
    else:
        print(f"Warning: catalog not found or empty at {CATALOG_PATH}")

    friend_payloads = []
    for backup in backups:
        rows = fetch_rows_from_backup(backup.path)
        payload = build_friend_stats(backup.friend_id, backup.display_name, rows, catalog)
        payload["sourceBackup"] = str(backup.path.relative_to(ROOT))
        friend_payloads.append(payload)

    manifest = build_manifest(friend_payloads)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FRIENDS_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    for old_json in FRIENDS_DIR.glob("*.json"):
        old_json.unlink()
    for old_profile in PROFILES_DIR.glob("*.html"):
        old_profile.unlink()

    for friend in friend_payloads:
        write_json(FRIENDS_DIR / f"{friend['friendId']}.json", friend)
    write_json(DATA_DIR / "manifest.json", manifest)
    write_static_pages(manifest, friend_payloads)

    print(f"Generated site data for {len(friend_payloads)} collector(s).")


if __name__ == "__main__":
    main()
