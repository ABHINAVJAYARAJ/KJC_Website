# test_forms_workflow.py
# Author: Abhinav Jayaraj
# Contact: jayarajabhinav@gmail.com

"""Regression tests for non-interactive consultant and departure imports."""

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent.parent
PROFILE_HEADERS = (HERE / 'templates/consultant_profile_form.example.csv').read_text().splitlines()[0].split(',')
DEPARTURE_HEADERS = ['Timestamp', 'KCL ID', 'Leaving date']


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'kjc'
        shutil.copytree(HERE, self.root, ignore=shutil.ignore_patterns('private', '__pycache__'))
        (self.root / 'private/photos').mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def row(self, identifier='90000001', first='Alex', last='Smith', bio='Original bio'):
        value = {key: '' for key in PROFILE_HEADERS}
        value.update({
            'Timestamp': '09/11/2026 12:00:00', 'KCL ID': identifier,
            'First name': first, 'Last name': last, 'Date joined': '01/09/2024',
            'Current role': 'Senior Consultant', 'Current role start date': '01/09/2025',
            'Previous role 1': 'General Consultant', 'Previous role 1 start date': '2024-09-01',
            'Previous role 1 end date': '2025-08-31', 'Focus area': 'Strategy',
            'Biography': bio, 'Expertise': 'Strategy; Research',
            'Background': 'Research background',
            'LinkedIn URL': 'https://www.linkedin.com/in/example/',
        })
        return value

    def write_csv(self, path, headers, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def profiles(self, rows):
        self.write_csv(self.root / 'private/forms_responses.csv', PROFILE_HEADERS, rows)

    def departures(self, rows):
        self.write_csv(self.root / 'private/departures.csv', DEPARTURE_HEADERS, rows)

    def call(self, script, *args):
        return subprocess.run([sys.executable, 'scripts/' + script, *args],
                              cwd=self.root, capture_output=True, text=True, timeout=25)

    def sync(self, *args):
        return self.call('sync_consultants.py', *args)

    def data(self):
        return json.loads((self.root / 'source/consultants/roster.json').read_text())['profiles']

    def photo(self, filename, color=(230, 80, 80)):
        path = self.root / 'private/photos' / filename
        img = Image.new('RGB', (240, 300), color)
        img.save(path)
        return path

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + '\n' + result.stderr)

    def test_default_import_adds_new_and_does_not_update_existing(self):
        self.profiles([self.row()])
        self.assert_success(self.sync('--publish'))
        original = self.data()[0]
        self.profiles([self.row(bio='Changed bio'), self.row('90000002', 'Jamie', 'Jones')])
        result = self.sync()
        self.assert_success(result)
        self.assertEqual(len(self.data()), 2)
        byname = {item['name']: item for item in self.data()}
        self.assertEqual(byname['Alex Smith'], original)
        self.assertIn('skipped=1', result.stdout)

    def test_explicit_update_changes_only_target_and_preserves_url(self):
        self.profiles([self.row(), self.row('90000002', 'Jamie', 'Jones')])
        self.assert_success(self.sync('--publish'))
        slug = next(p['slug'] for p in self.data() if p['name'] == 'Alex Smith')
        self.profiles([self.row(bio='Updated bio'), self.row('90000002', 'Jamie', 'Jones', 'New Jamie bio')])
        self.assert_success(self.sync('update_alex_smith_90000001'))
        people = {p['name']: p for p in self.data()}
        self.assertEqual(people['Alex Smith']['bio'], 'Updated bio')
        self.assertEqual(people['Alex Smith']['slug'], slug)
        self.assertEqual(people['Jamie Jones']['bio'], 'Original bio')

    def test_explicit_add_and_id_disambiguation(self):
        self.profiles([self.row(), self.row('90000002', 'Alex', 'Smith')])
        self.assert_success(self.sync('add_alex_smith_90000001', '--publish'))
        self.assertEqual(len(self.data()), 1)
        self.assert_success(self.sync('add_alex_smith_90000002'))
        self.assertEqual(len(self.data()), 2)
        self.assertEqual(len({p['slug'] for p in self.data()}), 2)
        self.assertNotIn('90000001', (self.root / 'dev/consultants/data.js').read_text())

    def test_remove_is_suppressed_on_default_and_explicit_add_restores(self):
        self.profiles([self.row()])
        self.assert_success(self.sync('--publish'))
        person = self.data()[0]
        self.assert_success(self.sync('remove_alex_smith_90000001'))
        self.assertEqual(self.data(), [])
        self.assertFalse((self.root / 'dev/consultants' / person['slug'] / 'index.html').exists())
        self.assert_success(self.sync())
        self.assertEqual(self.data(), [])
        self.assert_success(self.sync('add_alex_smith_90000001'))
        self.assertEqual(len(self.data()), 1)
        self.assertEqual(json.loads((self.root/'private/suppressed_kcl_ids.json').read_text()), [])

    def test_photo_asset_opaque_and_metadata_removed(self):
        self.profiles([self.row()])
        self.photo('alex_smith_90000001.jpg')
        self.assert_success(self.sync('--publish'))
        person = self.data()[0]
        self.assertRegex(person['photo'], r'^p-[0-9a-f]{32}\.webp$')
        self.assertNotIn(person['profile_key'], person['photo'])
        raw = (self.root / 'dev/assets/consultants' / person['photo']).read_bytes()
        self.assertTrue(raw.startswith(b'RIFF'))
        self.assertNotIn(b'EXIF', raw)
        self.assertNotIn(b'90000001', raw)
        page = (self.root/'dev/consultants'/person['slug']/'index.html').read_text()
        self.assertIn(person['photo'], page)
        self.assertNotIn('90000001', page)

    def test_update_image_changes_photo_not_bio_without_csv(self):
        self.profiles([self.row()])
        self.photo('alex_smith_90000001.png', (80, 90, 140))
        self.assert_success(self.sync('--publish'))
        prior = self.data()[0]
        self.photo('alex_smith_90000001.png', (140, 160, 200))
        (self.root / 'private/forms_responses.csv').unlink()
        self.assert_success(self.sync('update_image_alex_smith_90000001'))
        latest = self.data()[0]
        self.assertNotEqual(latest['photo'], prior['photo'])
        self.assertEqual(latest['bio'], prior['bio'])
        self.assertFalse((self.root/'dev/assets/consultants'/prior['photo']).exists())
        self.assert_success(self.sync('update_image_alex_smith_90000001'))
        self.assertEqual(self.data()[0]['photo'], latest['photo'])

    def test_update_with_photo_does_not_silently_change_photo(self):
        self.profiles([self.row()])
        self.photo('alex_smith_90000001.jpg', (80, 90, 140))
        self.assert_success(self.sync('--publish'))
        photo = self.data()[0]['photo']
        self.photo('alex_smith_90000001.jpg', (90, 100, 160))
        self.profiles([self.row(bio='New bio')])
        self.assert_success(self.sync('update_alex_smith_90000001'))
        self.assertEqual(self.data()[0]['photo'], photo)
        self.assertEqual(self.data()[0]['bio'], 'New bio')

    def test_departure_form_import_does_not_modify_other_fields(self):
        self.profiles([self.row()])
        self.assert_success(self.sync('--publish'))
        old = self.data()[0]
        self.departures([{'Timestamp': '09/11/2026 12:00:00', 'KCL ID': '90000001',
                          'Leaving date': '30/09/2026'}])
        self.assert_success(self.call('sync_departures.py'))
        new = self.data()[0]
        self.assertEqual(new['status'], 'former')
        self.assertEqual(new['left_on'], '2026-09-30')
        self.assertEqual(new['slug'], old['slug'])
        self.assertEqual(new['bio'], old['bio'])
        self.assert_success(self.sync())
        self.assertEqual(self.data()[0]['status'], 'former')

    def test_duplicate_form_responses_use_newest_timestamp(self):
        old = self.row(bio='Old bio')
        new = self.row(bio='New bio')
        new['Timestamp'] = '10/11/2026 12:00:00'
        self.profiles([new, old])
        self.assert_success(self.sync('--publish'))
        self.assertEqual(self.data()[0]['bio'], 'New bio')

    def test_ambiguous_duplicate_form_responses_are_skipped(self):
        a = self.row()
        b = self.row(bio='Conflicting bio')
        self.profiles([a, b])
        result = self.sync()
        self.assert_success(result)
        self.assertIn('ambiguous duplicate', result.stdout)
        self.assertEqual(self.data(), [])

    def test_private_command_file_and_dry_run(self):
        self.profiles([self.row()])
        actions = self.root/'private/actions.txt'
        actions.write_text('add_alex_smith_90000001\n')
        self.assert_success(self.sync('--dry-run', '--actions', 'private/actions.txt'))
        self.assertEqual(self.data(), [])
        self.assertFalse((self.root/'private/kcl_id_map.json').exists())
        self.assert_success(self.sync('--actions', 'private/actions.txt'))
        self.assertEqual(len(self.data()), 1)

    def test_invalid_command_name_rejected_and_duplicate_actions_rejected(self):
        self.profiles([self.row()])
        result = self.sync('update_jamie_smith_90000001')
        self.assert_success(result)
        self.assertEqual(self.data(), [])
        result = self.sync('add_alex_smith_90000001', 'remove_alex_smith_90000001')
        self.assertNotEqual(result.returncode, 0)

    def test_missing_id_map_prevents_duplicate_profiles(self):
        self.profiles([self.row()])
        self.assert_success(self.sync())
        (self.root/'private/kcl_id_map.json').unlink()
        self.assertNotEqual(self.sync().returncode, 0)

    def test_three_previous_roles_supported(self):
        r = self.row()
        r['Current role start date'] = '2026-08-01'
        r['Previous role 1 end date'] = '2025-01-31'
        r['Previous role 2'] = 'Associate'
        r['Previous role 2 start date'] = '2025-02-01'
        r['Previous role 2 end date'] = '2025-05-31'
        r['Previous role 3'] = 'Lead'
        r['Previous role 3 start date'] = '2025-06-01'
        r['Previous role 3 end date'] = '2026-07-31'
        self.profiles([r])
        self.assert_success(self.sync('--publish'))
        self.assertEqual(len(self.data()[0]['previous_roles']), 3)


if __name__ == '__main__':
    unittest.main()
