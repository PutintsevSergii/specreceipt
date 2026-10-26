"""Exercise the actual readline wizard over a PTY, without changing real HOME."""
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

with tempfile.TemporaryDirectory(prefix='harness-wizard-') as directory:
    root = Path(directory).resolve()
    target = root/'project with spaces'
    env = dict(os.environ, HOME=str(root), USERPROFILE=str(root), XDG_CONFIG_HOME=str(root/'config'))
    if env.get('HARNESS_REAL_OPENSPEC'):
        env['PATH'] = str(Path(env['HARNESS_REAL_OPENSPEC']).parent)+os.pathsep+env['PATH']
    master, slave = pty.openpty()
    process = subprocess.Popen(['node',str(Path('dist/cli.js').resolve()),'init','--target',str(target)],stdin=slave,stdout=slave,stderr=slave,env=env)
    os.close(slave)
    prompts=[b'agent:',b'workflow:',b'quality:',b'skills:',b'Target directory',b'Initialize this directory?']
    answers=[b'\n']*5+[b'y\n']
    output=b''; cursor=0; deadline=time.monotonic()+30
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([master],[],[],0.2)
            if ready:
                try: chunk=os.read(master,65536)
                except OSError: break
                if not chunk: break
                output+=chunk
                if cursor<len(prompts) and prompts[cursor] in output:
                    os.write(master,answers[cursor]);cursor+=1
            if process.poll() is not None: break
        if process.poll() is None: process.kill()
        code=process.wait()
        assert code==0,output.decode(errors='replace')
        assert cursor==len(prompts),output.decode(errors='replace')
        assert (target/'.harness/installation-manifest.json').is_file()
        assert (target/'.agents/skills/openspec-propose/SKILL.md').is_file()
        print('Interactive PTY wizard: selections, target confirmation and actual installation PASS.')
    finally:
        os.close(master)
        if process.poll() is None:process.kill();process.wait()
