# sync_consultants.py
# Author: Abhinav Jayaraj
# Contact: jayarajabhinav@gmail.com

"""Synchronise consultant profiles using explicit batch commands or add-only mode."""

import argparse
import csv
import io
import json
import re
import secrets
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_DIR = ROOT / 'private'
IDENTITY_MAP = PRIVATE_DIR / 'kcl_id_map.json'
SUPPRESSED_IDS = PRIVATE_DIR / 'suppressed_kcl_ids.json'
ROSTER_PATH = ROOT / 'source' / 'consultants' / 'roster.json'
PUBLIC_PHOTOS = ROOT / 'dev' / 'assets' / 'consultants'
PHOTO_EXTENSIONS = ('webp', 'jpg', 'jpeg', 'png')
REQUIRED_COLUMNS = (
    'KCL ID', 'First name', 'Last name', 'Date joined', 'Current role',
    'Current role start date', 'Focus area', 'Biography', 'Expertise',
    'Background', 'LinkedIn URL',
)
PREVIOUS_COLUMNS = tuple(
    f'Previous role {number} {field}' if field else f'Previous role {number}'
    for number in range(1, 4)
    for field in ('', 'start date', 'end date')
)
COMMAND_RE = re.compile(r'^(update_image|add|update|remove)_(.+)_([0-9]{6,12})$')
PUBLIC_PHOTO_RE = re.compile(r'^(?:p-[0-9a-f]{32}\.webp|portrait-[0-9a-f]{12}\.(?:webp|jpg|jpeg|png))$')


def normalise_id(value):
    identifier = str(value or '').strip()
    if not re.fullmatch(r'\d{6,12}', identifier):
        raise ValueError('KCL ID must contain 6–12 digits; retain leading zeros')
    return identifier


def filename_part(value):
    plain = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    result = re.sub(r'[^a-z0-9]+', '_', plain).strip('_')
    if not result:
        raise ValueError('A filename component cannot be empty')
    return result


def name_token(first, last):
    return f'{filename_part(first)}_{filename_part(last)}'


def normalise_date(value, *, required=False):
    value = str(value or '').strip()
    if not value:
        if required:
            raise ValueError('Date is required')
        return ''
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f'Invalid date {value!r}; use YYYY-MM-DD or DD/MM/YYYY')


def valid_linkedin(value):
    if not value:
        return True
    url = urlparse(value)
    return (url.scheme == 'https' and url.hostname in {
        'www.linkedin.com', 'linkedin.com', 'uk.linkedin.com'
    } and url.path.startswith('/in/') and not url.username and not url.password)


def read_csv(path, columns):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{path.name}: missing columns: {", ".join(sorted(missing))}')
        return [
            {key: (value or '').strip() for key, value in row.items() if key}
            for row in reader if any((value or '').strip() for value in row.values())
        ]


def submission_timestamp(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def select_submission(identifier, candidates, description='response'):
    """
    Select the latest unambiguous Google Forms response for a KCL ID.

    Args:
        identifier: Internal ID used to group submissions.
        candidates: Submissions with that same ID.
        description: Human-readable response type for log messages.

    Returns:
        Selected response or None when the timestamps are ambiguous.
    """
    if len(candidates) == 1:
        return candidates[0]
    dated = [(submission_timestamp(row.get('Timestamp', '')), row) for row in candidates]
    if all(stamp is not None for stamp, _ in dated):
        newest = max(stamp for stamp, _ in dated)
        winners = [row for stamp, row in dated if stamp == newest]
        if len(winners) == 1:
            print(f'ID ending {identifier[-4:]}: using newest of {len(candidates)} {description}s')
            return winners[0]
    print(f'ID ending {identifier[-4:]}: ambiguous duplicate {description}s; skipped. '
          'Keep one response per ID or provide unique UK timestamps.')
    return None


def match_photo(first, last, identifier, directory):
    """
    Locate a private consultant photo using their name and KCL ID.

    Args:
        first: Consultant's first name from the form.
        last: Consultant's surname from the form.
        identifier: Internal KCL ID used only for matching.
        directory: Folder containing original photographs.

    Returns:
        Matched local image path, or None if no photo was provided.
    """
    stem = f'{name_token(first, last)}_{identifier}'
    matches = [directory / f'{stem}.{ext}' for ext in PHOTO_EXTENSIONS
               if (directory / f'{stem}.{ext}').is_file()]
    if len(matches) > 1:
        raise ValueError(f'ID ending {identifier[-4:]}: multiple photos with the same stem')
    if not matches:
        return None
    image = matches[0]
    if image.stat().st_size > 4_000_000:
        raise ValueError('Photo exceeds 4 MB')
    return image


def sanitise_photo(image_path):
    """Re-encode photos without EXIF; public filenames are assigned separately."""
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as error:
        raise ValueError('Install local photo tools: pip install -r requirements-local.txt') from error
    try:
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image)
            if image.width < 100 or image.height < 100:
                raise ValueError('Photo dimensions must be at least 100 by 100 pixels')
            if image.width * image.height > 20_000_000:
                raise ValueError('Photo dimensions are too large')
            image = image.convert('RGB')
            image.thumbnail((1200, 1500), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format='WEBP', quality=86, method=5)
            return output.getvalue()
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError('Cannot read photo; use a valid JPEG, PNG or WebP') from error


def parse_roles(row, joined, current_since):
    """
    Validate and order up to three previous KJC roles.

    Args:
        row: Imported profile form fields.
        joined: Consultant's joining date in ISO format.
        current_since: Start date of their current role.

    Returns:
        Chronologically ordered role records with start and end dates.
    """
    history = []
    for number in range(1, 4):
        title = row[f'Previous role {number}'].strip()
        start = row[f'Previous role {number} start date'].strip()
        end = row[f'Previous role {number} end date'].strip()
        if not title and not start and not end:
            continue
        if not title or not start:
            raise ValueError(f'Previous role {number}: title and start date are required together')
        start = normalise_date(start, required=True)
        end = normalise_date(end)
        if start < joined or start > current_since:
            raise ValueError(f'Previous role {number}: start date is outside membership dates')
        if end and (end < start or end > current_since):
            raise ValueError(f'Previous role {number}: invalid end date')
        history.append({'title': title, 'start': start, 'end': end})
    history.sort(key=lambda role: role['start'])
    for old, new in zip(history, history[1:]):
        if old['end'] and old['end'] > new['start']:
            raise ValueError('Previous role dates overlap')
        if not old['end'] and old['start'] == new['start']:
            raise ValueError('Previous roles need distinct start dates')
    return history


def make_profile(row, profile_key, previous):
    first, last = row['First name'], row['Last name']
    role = row['Current role']
    if not all((first, last, role, row['Biography'])):
        raise ValueError('First name, last name, current role and biography are required')
    if len(first) > 80 or len(last) > 80 or len(row['Biography']) > 1800:
        raise ValueError('Name or biography exceeds maximum length')
    if not valid_linkedin(row['LinkedIn URL']):
        raise ValueError('LinkedIn URL must be https://linkedin.com/in/...')
    joined = normalise_date(row['Date joined'], required=True)
    current_since = normalise_date(row['Current role start date'], required=True)
    if current_since < joined:
        raise ValueError('Current role starts before joining date')
    history = parse_roles(row, joined, current_since)
    slug = previous['slug'] if previous else (
        f'{filename_part(first).replace("_", "-")}-{filename_part(last).replace("_", "-")}-{profile_key}'
    )
    left_on = previous.get('left_on', '') if previous else ''
    if left_on and (current_since > left_on or joined > left_on):
        raise ValueError('Dates are later than recorded departure')
    return {
        'profile_key': profile_key, 'slug': slug, 'name': f'{first} {last}',
        'role': role, 'focus': row['Focus area'], 'bio': row['Biography'],
        'expertise': [piece.strip() for piece in re.split(r'[;,]', row['Expertise']) if piece.strip()],
        'background': row['Background'], 'linkedin': row['LinkedIn URL'],
        'joined_on': joined, 'current_since': current_since, 'previous_roles': history,
        'status': previous.get('status', 'active') if previous else 'active',
        'left_on': left_on, 'photo': previous.get('photo', '') if previous else '',
    }


def read_identity_map():
    if not IDENTITY_MAP.is_file():
        return {}
    value = json.loads(IDENTITY_MAP.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or len(set(value.values())) != len(value):
        raise ValueError('Invalid private ID mapping')
    for identifier, key in value.items():
        normalise_id(identifier)
        if not re.fullmatch(r'[0-9a-f]{12}', key):
            raise ValueError('Invalid public profile key in ID mapping')
    return value


def save_private_json(path, value):
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    # Write identity records atomically; the public roster never contains KCL IDs.
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


def read_suppressed():
    if not SUPPRESSED_IDS.exists():
        return set()
    values = json.loads(SUPPRESSED_IDS.read_text(encoding='utf-8'))
    if not isinstance(values, list):
        raise ValueError('Invalid suppressed-ID register')
    return {normalise_id(item) for item in values}


def unique_public_key(mapping, roster):
    taken = set(mapping.values()) | {person['profile_key'] for person in roster}
    while True:
        key = secrets.token_hex(6)
        if key not in taken:
            return key


def read_commands(args):
    """Read batch actions and reject conflicting operations for one KCL ID."""
    commands = list(args.commands)
    if args.actions:
        for line in args.actions.read_text(encoding='utf-8').splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                commands.append(stripped)
    parsed = []
    seen = set()
    for command in commands:
        match = COMMAND_RE.fullmatch(command)
        if not match:
            raise ValueError(f'Invalid command format: {command!r}')
        operation, label, identifier = match.groups()
        if identifier in seen:
            raise ValueError('Multiple commands for the same KCL ID. Run them separately in order.')
        seen.add(identifier)
        parsed.append((operation, label, identifier))
    return parsed


def prepare_public_photo(photo, previous_name, pending):
    payload = sanitise_photo(photo)
    if previous_name:
        old = pending.get(previous_name)
        old_path = PUBLIC_PHOTOS / previous_name
        if old is None and old_path.is_file():
            old = old_path.read_bytes()
        if old == payload:
            return previous_name, False
    filename = f'p-{secrets.token_hex(16)}.webp'
    while filename in pending or (PUBLIC_PHOTOS / filename).exists():
        filename = f'p-{secrets.token_hex(16)}.webp'
    pending[filename] = payload
    return filename, True


def plan_profile_update(operation, identifier, row, old, mapping, roster, photos, staged):
    if operation == 'add' and old:
        return None, 'already exists; use update_ or update_image_'
    if operation == 'update' and not old:
        return None, 'not found; use add_'
    key = mapping.get(identifier) or unique_public_key(mapping, roster)
    proposed = make_profile(row, key, old)
    if identifier in json.dumps(proposed, ensure_ascii=False):
        raise ValueError('KCL ID appears in public-facing form content; remove it')
    if operation == 'add':
        image = match_photo(row['First name'], row['Last name'], identifier, photos)
        if image:
            proposed['photo'], _ = prepare_public_photo(image, '', staged)
    if old == proposed:
        return None, 'unchanged'
    return proposed, None


def run(args):
    roster = json.loads(ROSTER_PATH.read_text(encoding='utf-8'))
    people = {p['profile_key']: p for p in roster.get('profiles', [])}
    if len(people) != len(roster.get('profiles', [])):
        raise ValueError('Duplicate public profile keys in roster')
    mapping = read_identity_map()
    if people and not IDENTITY_MAP.exists():
        raise ValueError('Private ID map missing; restore backup before importing')
    if set(mapping.values()) != set(people):
        raise ValueError('Private ID map and published roster differ; restore matching backup')
    suppressed = read_suppressed()
    commands = read_commands(args)

    need_csv = not commands or any(action in ('add', 'update') for action, _, _ in commands)
    grouped = defaultdict(list)
    if need_csv:
        for row in read_csv(args.responses, REQUIRED_COLUMNS + PREVIOUS_COLUMNS):
            try:
                grouped[normalise_id(row['KCL ID'])].append(row)
            except ValueError:
                print('Skipping a CSV response with an invalid student ID')

    pending_photos = {}
    actions = commands if commands else [
        ('add', '', identifier) for identifier in grouped
    ]
    counts = {'added': 0, 'updated': 0, 'image_updated': 0, 'removed': 0,
              'skipped': 0, 'unchanged': 0}
    for operation, label, identifier in actions:
        key = mapping.get(identifier)
        old = people.get(key) if key else None
        rows = grouped.get(identifier, [])
        row = select_submission(identifier, rows) if rows else None
        if not commands and (old or identifier in suppressed):
            counts['skipped'] += 1
            continue

        try:
            if operation in ('add', 'update'):
                if not row:
                    print(f'ID ending {identifier[-4:]}: no unambiguous profile form response; skipped')
                    counts['skipped'] += 1
                    continue
                actual_label = name_token(row['First name'], row['Last name'])
            elif old:
                first, last = old['name'].split(' ', 1)
                actual_label = name_token(first, last)
            else:
                print(f'ID ending {identifier[-4:]}: no existing consultant; skipped')
                counts['skipped'] += 1
                continue
            if commands and label != actual_label:
                print(f'ID ending {identifier[-4:]}: name in command does not match stored/form name; skipped')
                counts['skipped'] += 1
                continue
            if operation == 'remove':
                del people[key]
                del mapping[identifier]
                suppressed.add(identifier)
                counts['removed'] += 1
                print(f'Removed {old["name"]}; future default imports will skip this ID')
                continue
            if operation == 'update_image':
                photo = match_photo(first, last, identifier, args.photos)
                if not photo:
                    print(f'{old["name"]}: no matching private photo; skipped')
                    counts['skipped'] += 1
                    continue
                filename, changed = prepare_public_photo(photo, old.get('photo', ''), pending_photos)
                if not changed:
                    counts['unchanged'] += 1
                    continue
                people[key] = {**old, 'photo': filename}
                counts['image_updated'] += 1
                print(f'Updated portrait for {old["name"]}')
                continue
            proposed, reason = plan_profile_update(
                operation, identifier, row, old, mapping, list(people.values()), args.photos,
                pending_photos,
            )
            if not proposed:
                print(f'{row["First name"]} {row["Last name"]}: {reason}')
                counts['unchanged' if reason == 'unchanged' else 'skipped'] += 1
                continue
            people[proposed['profile_key']] = proposed
            mapping[identifier] = proposed['profile_key']
            suppressed.discard(identifier)
            counts['added' if not old else 'updated'] += 1
            print(f'{"Added" if not old else "Updated"} {proposed["name"]}')
        except (ValueError, OSError) as error:
            print(f'ID ending {identifier[-4:]}: {error}; skipped')
            counts['skipped'] += 1

    records = sorted(people.values(), key=lambda p: (p['name'].split()[-1].casefold(), p['name'].casefold()))
    if len({p['slug'] for p in records}) != len(records):
        raise ValueError('Duplicate public profile URLs; changes not saved')
    print('Summary: ' + ', '.join(f'{key}={count}' for key, count in counts.items()))
    if args.dry_run:
        print('Dry run: no files written')
        return 0

    roster['profiles'] = records
    if args.publish:
        roster['publish'] = True
    PUBLIC_PHOTOS.mkdir(parents=True, exist_ok=True)
    for filename, data in pending_photos.items():
        (PUBLIC_PHOTOS / filename).write_bytes(data)
    ROSTER_PATH.write_text(json.dumps(roster, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    save_private_json(IDENTITY_MAP, mapping)
    save_private_json(SUPPRESSED_IDS, sorted(suppressed))

    # Only managed public portraits are deleted; original private uploads are never changed.
    referenced = {p.get('photo') for p in records}
    for path in PUBLIC_PHOTOS.iterdir():
        if path.is_file() and PUBLIC_PHOTO_RE.fullmatch(path.name) and path.name not in referenced:
            path.unlink()
    from build_consultants import main as build_pages
    from check_site import main as check_pages
    build_pages()
    check_pages()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commands', nargs='*', help='Explicit add_, update_, remove_, update_image_ commands')
    parser.add_argument('--actions', type=Path, help='Optional private UTF-8 batch command file')
    parser.add_argument('--responses', type=Path, default=PRIVATE_DIR / 'forms_responses.csv')
    parser.add_argument('--photos', type=Path, default=PRIVATE_DIR / 'photos')
    parser.add_argument('--publish', action='store_true', help='Enable published consultant directory')
    parser.add_argument('--dry-run', action='store_true', help='Preview operations without changing files')
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
