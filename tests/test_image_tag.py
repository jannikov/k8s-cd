import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image_tags', ROOT / 'scripts/set-image-tag.py')
tags = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tags)


class ImageTagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'onpremise', self.root / 'onpremise')

    def test_each_project_updates_only_its_tag_and_is_idempotent(self):
        for project, app in tags.PROJECTS.items():
            path = self.root / 'onpremise/live' / app / 'kustomization.yaml'
            before = path.read_text()
            target = '192.168.88.237:31081/ci-docker/' + project
            old_tag = before.split('- name: ' + target + '\n')[1].split('newTag: ')[1].splitlines()[0]
            tags.set_tag(self.root, project, 'test-123')
            expected = before.replace('- name: ' + target + '\n  newTag: ' + old_tag,
                                      '- name: ' + target + '\n  newTag: test-123')
            self.assertEqual(path.read_text(), expected)
            tags.set_tag(self.root, project, 'test-123')
            self.assertEqual(path.read_text(), expected)

    def test_rejects_unknown_project_and_invalid_tag(self):
        for project, tag in [('other', 'v1'), ('../eudris', 'v1'), ('eudris-app', 'bad\nvalue'), ('reporter-ui', '')]:
            with self.assertRaises(ValueError):
                tags.set_tag(self.root, project, tag)

    def test_missing_image_fails_instead_of_succeeding_silently(self):
        path = self.root / 'onpremise/live/eudris/kustomization.yaml'
        path.write_text('resources: []\n')
        with self.assertRaises(ValueError):
            tags.set_tag(self.root, 'eudris-app', 'v1')
