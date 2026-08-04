#!/usr/bin/env python3
"""Generate distinct sample Kennzeichensammler backups under example/<Name>/."""

from __future__ import annotations

import argparse
import random
import sqlite3
import zlib
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data" / "catalog.db"
DEFAULT_OUT = ROOT / "example"


def load_ids(catalog: Path, table: str) -> list[int]:
    conn = sqlite3.connect(catalog)
    rows = [
        int(row[0])
        for row in conn.execute(
            f'''
            SELECT DISTINCT id FROM "{table}"
            WHERE id > 1
              AND (besonderes IS NULL OR besonderes != "Diplomatenkennzeichen")
            ORDER BY id
            '''
        )
    ]
    conn.close()
    return rows


def assign_dates(
    n: int, start: date, end: date, rng: random.Random, streak_bias: bool
) -> list[str]:
    if n == 0:
        return []
    if streak_bias:
        days: list[date] = []
        cursor = start + timedelta(days=rng.randint(0, 20))
        while len(days) < min(n, 40):
            streak = rng.randint(3, 8)
            for i in range(streak):
                days.append(cursor + timedelta(days=i))
            cursor = days[-1] + timedelta(days=rng.randint(2, 12))
            if cursor > end:
                cursor = start + timedelta(days=rng.randint(0, 10))
        while len(days) < n:
            days.append(start + timedelta(days=rng.randint(0, (end - start).days)))
        days = days[:n]
        rng.shuffle(days)
        return [d.strftime("%d.%m.%Y") for d in days]
    span = max(1, (end - start).days)
    return [
        (start + timedelta(days=rng.randint(0, span))).strftime("%d.%m.%Y")
        for _ in range(n)
    ]


def write_backup(path: Path, rows: list[tuple[int, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.sqlite")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE android_metadata (locale TEXT)")
    conn.execute("INSERT INTO android_metadata VALUES ('en_DE')")
    conn.execute("CREATE TABLE gesehen (kennid INTEGER, datum TEXT, land TEXT)")
    conn.executemany("INSERT INTO gesehen VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    payload = b"KX1" + tmp.read_bytes()
    tmp.unlink()
    path.write_bytes(zlib.compress(payload, level=9))


PROFILES = [
    {
        "name": "Alex",
        "filename": "KennzeichensammlerBackupX-04.08.2026",
        "seed": 101,
        "de": 180,
        "eu": 12,
        "usa": 3,
        "streak": True,
        "start": date(2025, 11, 1),
    },
    {
        "name": "Mia",
        "filename": "KennzeichensammlerBackupX-03.08.2026",
        "seed": 202,
        "de": 45,
        "eu": 35,
        "usa": 8,
        "streak": False,
        "start": date(2026, 1, 15),
    },
    {
        "name": "Tom",
        "filename": "KennzeichensammlerBackupX-02.08.2026",
        "seed": 303,
        "de": 25,
        "eu": 5,
        "usa": 40,
        "streak": True,
        "start": date(2026, 3, 1),
    },
    {
        "name": "Sam",
        "filename": "KennzeichensammlerBackupX-01.08.2026",
        "seed": 404,
        "de": 90,
        "eu": 20,
        "usa": 15,
        "streak": False,
        "start": date(2025, 9, 1),
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    de_ids = load_ids(args.catalog, "deutschland")
    eu_ids = load_ids(args.catalog, "laender")
    usa_ids = load_ids(args.catalog, "usa")
    end = date.today()

    for profile in PROFILES:
        rng = random.Random(profile["seed"])
        rows: list[tuple[int, str, str]] = []
        for land, pool, count in (
            ("deutschland", de_ids, profile["de"]),
            ("laender", eu_ids, profile["eu"]),
            ("usa", usa_ids, profile["usa"]),
        ):
            pick = rng.sample(pool, min(count, len(pool)))
            dates = assign_dates(
                len(pick), profile["start"], end, rng, streak_bias=profile["streak"]
            )
            rows.extend((kid, datum, land) for kid, datum in zip(pick, dates))
        rows.sort(key=lambda row: (row[1][6:], row[1][3:5], row[1][:2], row[0]))
        out_path = args.out / profile["name"] / profile["filename"]
        write_backup(out_path, rows)
        print(f"{out_path.relative_to(ROOT)} — {len(rows)} plates")


if __name__ == "__main__":
    main()
