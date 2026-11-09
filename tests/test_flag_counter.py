# test_flag_counter.py
# Author: Abhinav Jayaraj
# Contact: jayarajabhinav@gmail.com

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class FlagCounterTests(unittest.TestCase):
    """Check that the visitor counter uses one shared configuration."""

    def test_counter_present_in_each_footer(self):
        pages = (
            'index.html',
            'dev/index.html',
            'dev/consultants/index.html',
            'dev/consultants/profile-example/index.html',
        )
        for page in pages:
            with self.subTest(page=page):
                markup = (ROOT / page).read_text(encoding='utf-8')
                self.assertEqual(markup.count('data-flag-counter'), 1)
                self.assertIn('data-flag-counter hidden', markup)

    def test_counter_not_enabled_without_an_id(self):
        script = (ROOT / 'dev/script.js').read_text(encoding='utf-8')
        self.assertIn('const FLAG_COUNTER_IMAGE_URL', script)
        self.assertIn('const FLAG_COUNTER_STATS_URL', script)
        self.assertIn('function initialiseFlagCounter()', script)
        self.assertIn('!FLAG_COUNTER_IMAGE_URL || !FLAG_COUNTER_STATS_URL', script)

    def test_profile_template_has_counter(self):
        footer = (ROOT / 'source/consultants/footer.html').read_text(encoding='utf-8')
        self.assertIn('data-flag-counter hidden', footer)
        self.assertIn('__FOOTER__', (ROOT / 'source/consultants/profile.template.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
