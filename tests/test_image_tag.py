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
        reporter = self.root / 'onpremise/live/reporter/kustomization.yaml'
        reporter.write_text(
            'apiVersion: kustomize.config.k8s.io/v1beta1\n'
            'kind: Kustomization\nimages:\n'
            + ''.join(
                '- name: 192.168.88.237:31081/ci-docker/' + project
                + '\n  newTag: old-tag\n'
                for project, app in tags.PROJECTS.items() if app == 'reporter'
            )
        )
        for project, app in tags.PROJECTS.items():
            path = self.root / 'onpremise/live' / app / 'kustomization.yaml'
            before = path.read_text()
            target = '192.168.88.237:31081/ci-docker/' + project
            old_tag = before.split('- name: ' + target + '\n')[1].split('newTag: ')[1].splitlines()[0]
            tags.set_tag(self.root, project, 'test-123')
            expected = before.replace('- name: ' + target + '\n  newTag: ' + old_tag,
                                      '- name: ' + target + '\n  newTag: "test-123"')
            self.assertEqual(path.read_text(), expected)
            tags.set_tag(self.root, project, 'test-123')
            self.assertEqual(path.read_text(), expected)

    def test_numeric_and_boolean_like_tags_stay_quoted(self):
        path = self.root / 'onpremise/live/eudris/kustomization.yaml'
        for tag in ['123', '1.0', 'true', 'null']:
            with self.subTest(tag=tag):
                tags.set_tag(self.root, 'eudris-app', tag)
                self.assertIn('  newTag: "' + tag + '"\n', path.read_text())

    def test_rejects_unknown_project_and_invalid_tag(self):
        for project, tag in [('other', 'v1'), ('../eudris', 'v1'), ('eudris-app', 'bad\nvalue'), ('reporter-ui', '')]:
            with self.assertRaises(ValueError):
                tags.set_tag(self.root, project, tag)

    def test_missing_image_fails_instead_of_succeeding_silently(self):
        path = self.root / 'onpremise/live/eudris/kustomization.yaml'
        path.write_text('resources: []\n')
        with self.assertRaises(ValueError):
            tags.set_tag(self.root, 'eudris-app', 'v1')
