"""Pre-implementation navigation evidence from the two local graph tools."""
from . import codegraph_tool, graphify_tool
from .storage import HarnessError, atomic, digest, now, redact, safe_path


def ensure(root):
    codegraph = codegraph_tool.ensure(root)
    graphify = graphify_tool.ensure(root)
    if codegraph['freshness'] != 'fresh' or graphify['freshness'] != 'fresh':
        raise HarnessError('Both CodeGraph and Graphify indexes must be fresh.')
    return {'result':'PASS','codegraph':codegraph,'graphify':graphify}


def collect(h, feature, task):
    indexes = ensure(h.root)
    question = ' '.join([task['outcome'], *task['scope']])[:500]
    codegraph = codegraph_tool.query(h.root, question, 10)
    graphify = graphify_tool.query(h.root, question, 800)
    if codegraph['result'] != 'PASS' or graphify['result'] != 'PASS':
        raise HarnessError('CodeGraph and Graphify context must be available before implementation.')
    record = redact({'task_id':task['id'],'feature_id':feature['feature_id'],
                     'created_at':now(),'input_fingerprint':h.binding(),
                     'question':question,'indexes':indexes,
                     'codegraph_context':codegraph,'graphify_context':graphify,
                     'limitations':['Graph results are navigation leads; inspect referenced source and requirements before implementation.']})
    ref = f'.harness/graph/task-context-{digest(task["id"])}.json'
    atomic(safe_path(h.root,ref),record)
    return {'result':'PASS','reference':ref,'codegraph':codegraph['result'],'graphify':graphify['result']}
