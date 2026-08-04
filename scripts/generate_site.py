#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
import zlib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable


DATE_FORMAT = "%d.%m.%Y"
SITE_DIRS_TO_SKIP = {"assets", "data", "example", "profiles", "scripts", ".git", "__pycache__"}
ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "index.html"
PROFILES_DIR = ROOT / "profiles"
DATA_DIR = ROOT / "data"
FRIENDS_DIR = DATA_DIR / "friends"


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


def display_name_from_slug(value: str) -> str:
    pieces = [part for part in value.replace("_", "-").split("-") if part]
    if not pieces:
        return "Collector"
    return " ".join(piece.capitalize() for piece in pieces)


def parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, DATE_FORMAT).date()


def format_date_iso(date_obj) -> str:
    return date_obj.isoformat()


def format_date_label(date_obj) -> str:
    return date_obj.strftime("%d.%m.%Y")


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
    backups: list[BackupSource] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SITE_DIRS_TO_SKIP for part in path.parts if part != root.name):
            continue
        sqlite_bytes = detect_backup_bytes(path)
        if sqlite_bytes is None:
            continue
        relative = path.relative_to(root)
        if len(relative.parts) > 1:
            friend_token = relative.parts[0]
        else:
            friend_token = path.name
        friend_id = slugify(friend_token)
        backups.append(
            BackupSource(
                friend_id=friend_id,
                display_name=display_name_from_slug(friend_token),
                path=path,
            )
        )
    deduped: dict[str, BackupSource] = {}
    for backup in backups:
        existing = deduped.get(backup.friend_id)
        if existing is None or backup.path.name > existing.path.name:
            deduped[backup.friend_id] = backup
    return sorted(deduped.values(), key=lambda item: item.friend_id)


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


def build_friend_stats(friend_id: str, display_name: str, rows: list[dict[str, str | int]]) -> dict:
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
            first_seen_rows.append(
                {
                    "kennid": row["kennid"],
                    "firstSeenDate": format_date_iso(row_date),
                    "land": row["land"],
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
        },
        "landBreakdown": [
            {"land": land, "count": count, "share": round(count / total_sightings, 4)}
            for land, count in sorted(land_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "series": {
            "dailyActivity": daily_series,
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
            <p class="page-intro">A cleaner snapshot of the current season with room to compare the top collectors at a glance.</p>
        </header>

        <div class="page-layout">
            <main class="main-panel">
                <div class="section-heading">
                    <h2>overall rankings</h2>
                    <p>Hover a collector to compare the current backup snapshot.</p>
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

        <div class="profile-layout">
            <section class="main-panel">
                <div class="section-heading">
                    <h2>activity over time</h2>
                    <p>Cumulative progress and daily discovery momentum.</p>
                </div>
                <div class="chart-card">
                    <div class="chart-frame" id="activity-chart"></div>
                </div>
                <div class="chart-card">
                    <div class="section-heading compact-heading">
                        <h2>daily breakdown</h2>
                        <p>New discoveries vs repeat sightings for each active day.</p>
                    </div>
                    <div class="daily-breakdown" id="daily-breakdown"></div>
                </div>
            </section>

            <aside class="awards-section">
                <div class="section-heading">
                    <h2>collector snapshot</h2>
                    <p>Derived metrics and land coverage available in the current backup schema.</p>
                </div>
                <div class="awards-list" id="profile-highlights"></div>
                <div class="chart-card">
                    <div class="section-heading compact-heading">
                        <h2>land breakdown</h2>
                        <p>Share of sightings by the available `land` field.</p>
                    </div>
                    <div class="bar-list" id="land-breakdown"></div>
                </div>
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
        default=str(ROOT),
        help="Directory to scan recursively for backup files.",
    )
    args = parser.parse_args()

    input_root = Path(args.input_root).resolve()
    backups = discover_backups(input_root)
    if not backups:
        raise SystemExit("No supported backup files found.")

    friend_payloads = []
    for backup in backups:
        rows = fetch_rows_from_backup(backup.path)
        payload = build_friend_stats(backup.friend_id, backup.display_name, rows)
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
