# build_consultants.py
# Author: Abhinav Jayaraj
# Contact: jayarajabhinav@gmail.com

from pathlib import Path
from urllib.parse import urlparse
from html import escape
import json
import re
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'source' / 'consultants'
OUTPUT = ROOT / 'dev' / 'consultants'


def clean(value):
    return escape(str(value or ''), quote=True)


def valid_linkedin(url):
    parsed = urlparse(str(url or ''))
    return parsed.scheme == 'https' and parsed.netloc.lower() in {
        'linkedin.com', 'www.linkedin.com', 'uk.linkedin.com'
    } and parsed.path.startswith('/in/') and not parsed.username and not parsed.password


def format_date(value):
    if not value:
        return ''
    return date.fromisoformat(value).strftime('%B %Y')


def render_timeline(person):
    """
    Build the consultant's KJC role history in reverse chronological order.

    Args:
        person: Public profile record containing membership and role dates.

    Returns:
        HTML for the progression section, or an empty string when unavailable.
    """
    joined = person.get('joined_on', '')
    since = person.get('current_since', '')
    history = person.get('previous_roles', [])
    if not joined and not history and not since:
        return ''
    former = person.get('status') == 'former'
    left_on = person.get('left_on', '') if former else ''
    entries = [(person['role'], since, left_on or '', True)]
    entries.extend((item['title'], item['start'], item.get('end', ''), False)
                   for item in sorted(history, key=lambda role: role['start'], reverse=True))
    pieces = []
    for title, start, end, is_current in entries:
        period = f'{format_date(start)} – {format_date(end) if end else "Present" if is_current else "End date not supplied"}'
        if not is_current and not end:
            period = f'From {format_date(start)}'
        pieces.append(f'<li><strong>{clean(title)}</strong><span>{clean(period)}</span></li>')
    membership = f'Joined KJC in {format_date(joined)}'
    if left_on:
        membership += f' · Left KJC in {format_date(left_on)}'
    return ('<section class="profile-section profile-career">'
            '<span class="eyebrow">02 / KJC JOURNEY</span>'
            '<h2>Progression at KJC</h2>'
            f'<p class="profile-membership">{clean(membership)}</p>'
            f'<ol class="profile-timeline">{"".join(pieces)}</ol></section>')


def render_profile(person, is_example=False):
    """
    Render an individual profile using the shared HTML template.

    Args:
        person: Consultant data already validated for public use.
        is_example: Whether to display the demonstration profile notice.

    Returns:
        Complete HTML for the consultant's public page.
    """
    template = (SOURCE / 'profile.template.html').read_text(encoding='utf-8')
    name = person['name']
    bio = person.get('bio') or 'Details will be added when the consultant profile is approved.'
    expertise = person.get('expertise', [])
    background = person.get('background', '')

    expertise_section = ''
    if expertise:
        tags = ''.join(f'<li>{clean(area)}</li>' for area in expertise)
        expertise_section = f'<section class="profile-section"><span class="eyebrow">03 / EXPERTISE</span><h2>Areas of expertise</h2><ul class="profile-expertise">{tags}</ul></section>'

    background_section = ''
    if background:
        background_section = f'<section class="profile-section"><span class="eyebrow">04 / BACKGROUND</span><h2>Background</h2><p>{clean(background)}</p></section>'

    linkedin = ''
    if valid_linkedin(person.get('linkedin', '')):
        linkedin = f'<a href="{clean(person["linkedin"])}" target="_blank" rel="noopener noreferrer">View LinkedIn profile ↗</a>'

    # The original text-only profile remains unchanged when there is no photo.
    photo = ''
    if person.get('photo'):
        photo = f'<div class="profile-portrait"><img src="../../assets/consultants/{clean(person["photo"])}" alt="Portrait of {clean(name)}" width="420" height="525" loading="lazy"></div>'

    fields = {
        '__TITLE__': clean(name + " | King's Junior Consulting"),
        '__DESCRIPTION__': clean(name + " — " + person["role"] + " at King's Junior Consulting."),
        '__NAME__': clean(name),
        '__NAME_HEADING__': clean(name),
        '__ROLE__': clean(person['role']),
        '__FOCUS__': clean(person.get('focus', '')),
        '__BIO__': clean(bio),
        '__EXPERTISE_SECTION__': expertise_section,
        '__BACKGROUND_SECTION__': background_section,
        '__EXAMPLE_FLAG__': '<span class="profile-example-flag">Layout example · not a real KJC consultant</span>' if is_example else '',
        '__LINKEDIN__': linkedin,
        '__CONNECT_DESCRIPTION__': 'A consultant LinkedIn link will appear here after approval.' if is_example else 'Connect with this consultant on LinkedIn or enquire about working with KJC.',
        '__PHOTO__': photo,
        '__TIMELINE_SECTION__': render_timeline(person),
        '__MEMBER_STATUS__': 'Former Consultant' if person.get('status') == 'former' else '',
        '__HEADER__': (SOURCE / 'header.html').read_text(encoding='utf-8'),
        '__FOOTER__': (SOURCE / 'footer.html').read_text(encoding='utf-8'),
    }
    for key, value in fields.items():
        template = template.replace(key, value)
    return template


def write_if_changed(path, content):
    if not path.exists() or path.read_text(encoding='utf-8') != content:
        path.write_text(content, encoding='utf-8')


def main():
    """Validate the public roster and write the consultant directory pages."""
    roster = json.loads((SOURCE / 'roster.json').read_text(encoding='utf-8'))
    people = roster.get('profiles', [])
    published = bool(roster.get('publish', False))
    slugs = set()
    ids = set()

    # Validate all records before generating public pages.
    for person in people:
        slug = person.get('slug', '')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
            raise ValueError(f'Invalid slug: {slug!r}')
        if slug in slugs or slug == 'profile-example':
            raise ValueError(f'Duplicate/reserved slug: {slug}')
        slugs.add(slug)
        identifier = person.get('profile_key', '')
        if not re.fullmatch(r'[0-9a-f]{12}', identifier) or identifier in ids:
            raise ValueError(f'Missing or duplicate public profile key for {slug}')
        ids.add(identifier)
        if any(field in person for field in ('kcl_id', 'KCL ID', 'kjc_id')):
            raise ValueError(f'Internal identifier found in public profile data for {slug}')
        if person.get('status', 'active') not in ('active', 'former'):
            raise ValueError(f'Invalid membership status for {slug}')
        if person.get('status') == 'former' and not person.get('left_on'):
            raise ValueError(f'Former consultant is missing leaving date for {slug}')
        if len(person.get('previous_roles', [])) > 3:
            raise ValueError(f'More than three previous roles for {slug}')
        for field in ('joined_on', 'current_since'):
            if not person.get(field):
                raise ValueError(f'Missing {field} for {slug}')
            date.fromisoformat(person[field])
        if person.get('left_on'):
            date.fromisoformat(person['left_on'])
        for role in person.get('previous_roles', []):
            if not role.get('title') or not role.get('start'):
                raise ValueError(f'Invalid previous role for {slug}')
            date.fromisoformat(role['start'])
            if role.get('end'):
                date.fromisoformat(role['end'])
        if not person.get('name') or not person.get('role'):
            raise ValueError(f'Name and role required for {slug}')
        if person.get('linkedin') and not valid_linkedin(person['linkedin']):
            raise ValueError(f'LinkedIn URL invalid for {slug}')
        if not isinstance(person.get('expertise', []), list):
            raise ValueError(f'Expertise must be a list for {slug}')
        photo = person.get('photo', '')
        if photo:
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)', photo):
                raise ValueError(f'Invalid portrait filename for {slug}')
            if not (ROOT / 'dev' / 'assets' / 'consultants' / photo).is_file():
                raise ValueError(f'Portrait missing from dev/assets/consultants for {slug}')

    # Only publish approved profiles after the directory is enabled.
    public_people = people if published else []
    data = (f'// data.js\n// Author: Abhinav Jayaraj\n'
            f'// Contact: jayarajabhinav@gmail.com\n\n'
            f'const PUBLISH_CONSULTANTS = {str(bool(public_people)).lower()};\n'
            f'const CONSULTANTS = {json.dumps(public_people, ensure_ascii=False, indent=2)};\n')
    write_if_changed(OUTPUT / 'data.js', data)

    generated = OUTPUT / '.generated-profiles.json'
    previous = json.loads(generated.read_text(encoding='utf-8')) if generated.exists() else []
    slugs_created = [person['slug'] for person in public_people]
    for slug in set(previous) - set(slugs_created):
        path = OUTPUT / slug / 'index.html'
        if path.exists():
            path.unlink()
        folder = OUTPUT / slug
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()

    # Unchanged pages retain their bytes and modification timestamps.
    for person in public_people:
        page = OUTPUT / person['slug']
        page.mkdir(exist_ok=True)
        write_if_changed(page / 'index.html', render_profile(person))
    write_if_changed(generated, json.dumps(slugs_created, indent=2) + '\n')

    # Keep the example route valid while the directory is unpublished.
    example = {
        'name': 'Example profile',
        'role': 'Consultant profile layout',
        'focus': 'Illustrative layout, not a real consultant',
        'bio': 'This page demonstrates how an individual consultant profile will be presented. Once the approved directory is published, each consultant will have a page with their introduction, specialist interests, and LinkedIn link.',
        'expertise': ['Strategy', 'Market research', 'Business analysis'],
        'background': 'Academic and professional background will appear here when supplied and approved by the consultant.',
        'linkedin': '',
    }
    page = OUTPUT / 'profile-example'
    page.mkdir(exist_ok=True)
    write_if_changed(page / 'index.html', render_profile(example, is_example=True))
    print(f'Generated {len(slugs_created)} consultant pages. Directory published: {bool(public_people)}')


if __name__ == '__main__':
    main()
