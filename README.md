Author: Abhinav Jayaraj  
Contact: jayarajabhinav@gmail.com

# King's Junior Consulting Website

Static website with a searchable consultant directory, individual profiles and two local data import scripts. The website itself uses HTML, CSS and JavaScript. Python is used offline to maintain consultant pages.

## Project structure

```text
KJC_Website_Source/
├── dev/                       Website files (open dev/index.html)
│   ├── index.html
│   ├── styles.css
│   ├── script.js
│   ├── assets/                Official KJC and JEE logos, favicon, public consultant photos
│   └── consultants/           Directory, individual profiles and directory styling
├── source/consultants/        Public roster and shared HTML profile templates
├── scripts/                   Consultant import, departure update, builder, link checker
├── templates/                 Google Forms CSV layouts, batch command examples, privacy draft
├── tests/                     Local regression tests
├── private/                   Local form exports and original images (DO NOT PUBLISH)
├── requirements-local.txt
└── .gitignore
```

## Getting started

1. Install Python 3.10 or later.
2. Install the local photo library: `python -m pip install -r requirements-local.txt`.
3. Open `dev/index.html` in your browser, or serve the `dev` folder with `python -m http.server 8000 --directory dev`.
4. To enable client enquiries, insert the published Google Forms URL into `GOOGLE_FORM_URL` in `dev/script.js`.

## Google Forms setup

Use **two separate forms** and export their responses as CSV:

- **Consultant Profile Form**: KCL ID, first/last name, date joined, current role and its start date, up to three previous roles and their date ranges, focus, biography, expertise, background, LinkedIn URL.
- **Consultant Departure Form**: KCL ID and leaving date.

Use the exact column headings in `templates/consultant_profile_form.example.csv` and `templates/consultant_departure_form.example.csv`. The script accepts dates in `YYYY-MM-DD` and `DD/MM/YYYY` format. If several responses share a KCL ID, the newest unambiguous form timestamp is selected; otherwise that record is skipped.

Put the exports into `private/forms_responses.csv` and `private/departures.csv`. The KCL ID is an **internal matching key** and is not included in public profile URLs, published image filenames or website HTML. Store the original form files and the generated mapping files in restricted administrative storage.

## Consultant photographs

Place original photos in `private/photos/` using `firstname_lastname_KCLID.webp` (JPEG/PNG also accepted). For example:

```text
private/photos/alex_smith_90000001.webp
```

Keep the filename lowercase, with underscores and no spaces. Use clear head-and-shoulders portraits, preferably 4:5, and up to 4 MB per file. Different people with identical names are distinguished by their KCL IDs.

The import script creates a WebP copy with a random public name and removes embedded image metadata. If a photo is not supplied, the original text-only profile appears. Images on a public website can still be saved by visitors: obfuscated filenames protect the original filename and student ID, **not the image itself**.

## Import new consultants

```bash
python scripts/sync_consultants.py --dry-run
python scripts/sync_consultants.py --publish
```

The default import adds new consultants and skips existing ones. The publish flag opens the directory once the team is ready.

For specific changes, provide a command or a batch file. Commands use the form `action_firstname_lastname_KCLID`:

```text
add_alex_smith_90000001
update_alex_smith_90000001
update_image_alex_smith_90000001
remove_alex_smith_90000001
```

`add` creates a missing profile, `update` changes CSV-derived text and dates (not the photo), `update_image` replaces only the photograph, and `remove` unpublishes a profile and remembers it so a later default import does not recreate it. The file `templates/commands.example.txt` shows the format.

```bash
python scripts/sync_consultants.py --actions private/actions.txt --dry-run
python scripts/sync_consultants.py --actions private/actions.txt
```

Keep the command file private because it contains student IDs. A profile update keeps the existing public URL, including after a name change.

## Process departure forms

```bash
python scripts/sync_departures.py --dry-run
python scripts/sync_departures.py
```

Only the separate departure form supplies leaving dates. The script marks existing profiles as former consultants, closes their current-role period and preserves their history, biography, photograph and link. It does not scrape LinkedIn or treat missing responses as departures.

## Rebuild and validate

```bash
python scripts/build_consultants.py
python scripts/check_site.py
python -m unittest discover -s tests -v
```

The directory and profile pages live under `dev/consultants/`. Only approved, public-facing consultant fields are written to `source/consultants/roster.json`. The `private/` directory is excluded by `.gitignore` and must stay outside any public upload.

## Code conventions

Source files carry the project author and contact header. Python uses short descriptive function names, docstrings for non-trivial behaviour and comments for decisions that are not obvious from the code. HTML remains semantic, with styles and scripts maintained in separate files. No external JavaScript framework or backend is required.

For compatibility, CSV header rows and generated JSON arrays do not contain comments: changing those formats would break the importers. Binary files retain their original metadata and format, with trademark ownership unaffected by the source-code header convention.

## Notes before publication

The consultants directory begins in its unpublished state. The client enquiry form URL is not configured by default. The privacy-notice text in `templates/` is a working draft for KJC to review independently of the import scripts. The website files have `noindex` metadata suitable for a development version; change indexing settings only when the public site is ready.
