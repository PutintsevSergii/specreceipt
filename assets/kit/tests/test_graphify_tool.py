"""Exercise the installed Graphify CLI against an isolated repository."""
from pathlib import Path
import shutil
import tempfile
import unittest

from harnesslib import graphify_tool


@unittest.skipUnless(shutil.which('graphify'), 'Graphify CLI is not installed')
class GraphifyToolTests(unittest.TestCase):
    def test_index_refresh_and_bounded_query(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'app.py'
            source.write_text('def first():\n    return 1\n')
            self.assertNotEqual(graphify_tool.status(root)['freshness'], 'fresh')
            first = graphify_tool.ensure(root)
            self.assertTrue(first['changed'])
            self.assertEqual(graphify_tool.status(root)['freshness'], 'fresh')
            self.assertFalse(graphify_tool.ensure(root)['changed'])
            answer = graphify_tool.query(root, 'first', 200)
            self.assertEqual(answer['result'], 'PASS')
            self.assertLessEqual(len(answer['answer']), 16000)
            source.write_text('def second():\n    return 2\n')
            self.assertEqual(graphify_tool.status(root)['freshness'], 'stale')
            graphify_tool.ensure(root)
            self.assertEqual(graphify_tool.status(root)['freshness'], 'fresh')
            self.assertIn('second', (root/'graphify-out/graph.json').read_text())

    def test_empty_project_then_source_added(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=graphify_tool.ensure(root)
            self.assertEqual(result['coverage'],'empty')
            self.assertEqual(result['freshness'],'fresh')
            self.assertEqual(graphify_tool.query(root,'entry',200)['coverage'],'empty')
            (root/'app.py').write_text('def hello():\n    return 1\n')
            self.assertEqual(graphify_tool.status(root)['freshness'],'stale')
            result=graphify_tool.ensure(root)
            self.assertEqual(result['coverage'],'code')
            self.assertGreater(result['nodes'],0)


if __name__ == '__main__':
    unittest.main()
