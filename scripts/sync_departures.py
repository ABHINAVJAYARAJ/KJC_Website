# sync_departures.py
# Author: Abhinav Jayaraj
# Contact: jayarajabhinav@gmail.com

"""Synchronise former-consultant status from the separate departure Google Form."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from sync_consultants import (
    PRIVATE_DIR, ROSTER_PATH, normalise_date, normalise_id,
    read_csv, read_identity_map, select_submission,
)

REQUIRED_COLUMNS = ('KCL ID', 'Leaving date')


def run(args):
    """Apply leaving dates from the departure form to existing profiles."""
    roster = json.loads(ROSTER_PATH.read_text(encoding='utf-8'))
    people = {entry['profile_key']: entry for entry in roster.get('profiles', [])}
    mapping = read_identity_map()
    if people and not (PRIVATE_DIR / 'kcl_id_map.json').exists():
        raise ValueError('Private KCL ID map missing; restore backup')
    if set(people) != set(mapping.values()):
        raise ValueError('KCL ID map and public roster do not match')

    grouped = defaultdict(list)
    for row in read_csv(args.departures, REQUIRED_COLUMNS):
        try:
            grouped[normalise_id(row['KCL ID'])].append(row)
        except ValueError:
            print('Skipped departure response with invalid student ID')

    updated = skipped = unchanged = 0
    for identifier, responses in grouped.items():
        key = mapping.get(identifier)
        if not key or key not in people:
            print(f'ID ending {identifier[-4:]}: no matching consultant; skipped')
            skipped += 1
            continue
        row = select_submission(identifier, responses, 'departure response')
        if row is None:
            skipped += 1
            continue
        person = people[key]
        try:
            left_on = normalise_date(row['Leaving date'], required=True)
            if left_on < person['joined_on'] or left_on < person['current_since']:
                raise ValueError('Departure date precedes joining/current-role date')
        except ValueError as error:
            print(f'{person["name"]}: {error}; skipped')
            skipped += 1
            continue
        if person.get('status') == 'former' and person.get('left_on') == left_on:
            unchanged += 1
            continue
        people[key] = {**person, 'status': 'former', 'left_on': left_on}
        print(f'{person["name"]}: set former consultant from {left_on}')
        updated += 1

    print(f'Departures: {updated} updated, {skipped} skipped, {unchanged} unchanged')
    if args.dry_run:
        print('Dry run: no files written')
        return 0
    roster['profiles'] = list(people.values())
    ROSTER_PATH.write_text(json.dumps(roster, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    from build_consultants import main as build_pages
    from check_site import main as check_pages
    build_pages()
    check_pages()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--departures', type=Path, default=PRIVATE_DIR / 'departures.csv')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
