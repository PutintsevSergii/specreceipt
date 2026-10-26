"""CLI contract and freshness tests without downloading an external package."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from harnesslib import codegraph_tool, index_context
from harnesslib.storage import read


class CodeGraphToolTests(unittest.TestCase):
    def test_task_context_is_saved_before_implementation_with_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            class HarnessFixture:
                root = Path(directory)
                def binding(self): return 'fixture-binding'
            with patch.object(index_context,'ensure',return_value={'result':'PASS'}), \
                 patch.object(index_context.codegraph_tool,'query',return_value={'result':'PASS','answer':'token=fixture-secret'}), \
                 patch.object(index_context.graphify_tool,'query',return_value={'result':'PASS','answer':'app.py'}):
                result = index_context.collect(HarnessFixture(),{'feature_id':'feature'},
                                               {'id':'TASK-1','outcome':'Implement app','scope':['app.py']})
            record = read(Path(directory)/result['reference'])
            self.assertEqual(record['input_fingerprint'],'fixture-binding')
            self.assertNotIn('fixture-secret',str(record))
            self.assertEqual(result['codegraph'],'PASS')

    def test_init_sync_and_query_use_bounded_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'app.py'
            source.write_text('def first(): return 1\n')
            binary = root/'fake-codegraph'
            binary.write_text('#!/usr/bin/env python3\n'
                              'import json, pathlib, sys\n'
                              'root=pathlib.Path.cwd()\n'
                              'cmd=sys.argv[1]\n'
                              'if cmd in ("init", "sync"):\n'
                              '    (root/".codegraph").mkdir(exist_ok=True)\n'
                              '    print(cmd)\n'
                              'elif cmd=="version": print("codegraph 1.6.2")\n'
                              'elif cmd=="status": print(json.dumps({"files":1}))\n'
                              'elif cmd=="query": print(json.dumps({"matches":["app.py"]}))\n')
            binary.chmod(0o755)
            original = shutil.which
            with patch.object(codegraph_tool.shutil,'which',side_effect=lambda name: str(binary) if name=='codegraph' else original(name)):
                self.assertTrue(codegraph_tool.ensure(root)['changed'])
                self.assertEqual(codegraph_tool.status(root)['freshness'],'fresh')
                self.assertFalse(codegraph_tool.ensure(root)['changed'])
                self.assertEqual(codegraph_tool.query(root,'first')['result'],'PASS')
                source.write_text('def second(): return 2\n')
                self.assertEqual(codegraph_tool.status(root)['freshness'],'stale')
                self.assertTrue(codegraph_tool.ensure(root)['changed'])
                self.assertEqual(codegraph_tool.status(root)['freshness'],'fresh')


if __name__ == '__main__':
    unittest.main()
