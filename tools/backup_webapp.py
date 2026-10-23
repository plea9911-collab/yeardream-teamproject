"""Back up session SQLite data without copying an active database file directly."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def backup_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError(f'Database not found: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of a previous backup.
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup integrity check failed')
                counts = {table: dst.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                          for table in ('sessions', 'answers')}
        return counts
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / 'runtime' / 'webapp')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output or ROOT / 'runtime' / 'backups' / f'sessions-{stamp}.sqlite3'
    counts = backup_database(args.runtime / 'sessions.sqlite3', output)
    print(json.dumps({'backup': str(output.resolve()), 'integrity': 'ok', **counts,
                      'scope': 'sessions and answers only; videos require a separate backup'}))


if __name__ == '__main__':
    main()
