/** Disposable E2E permission boundary, not a lifecycle engine. */
import fs from "node:fs";
import path from "node:path";
export function planningCommands(root, cli, openspec) {
  const bin = path.join(root, ".harness/e2e-bin");
  fs.mkdirSync(bin, { recursive: true });
  const common = `const a=process.argv.slice(2);const cwd=${JSON.stringify(root)};`;
  const harnessGuard = `const reads=['resume','status','next','skills','validate','readiness','codegraph','graphify','graph'];
const imports=a[0]==='openspec'&&['import','validate','context'].includes(a[1])&&a.slice(2).every(v=>['parse-port','--mapping','.harness/openspec-mapping.json','--help','--json'].includes(v));
if((!reads.includes(a[0])&&!imports)||a.some(v=>v.startsWith('--target')||v.startsWith('--output')))process.exit(64);`;
  const openspecGuard = `const allowed=(a.length===3&&a.join(' ')==='new change parse-port') || (a[0]==='validate'&&a.slice(1).every(v=>['parse-port','--strict','--json','--no-interactive'].includes(v))) || (['status','instructions'].includes(a[0])&&a.slice(1).every(v=>['proposal','design','specs','tasks','--change','parse-port','--json','--help'].includes(v)));
if(!allowed)process.exit(64);`;
  for (const [name, guard, file, prefix] of [
    ["harness-e2e-plan", harnessGuard, process.execPath, [cli]],
    ["openspec-e2e-plan", openspecGuard, openspec, []],
  ]) {
    fs.writeFileSync(
      path.join(bin, name),
      `#!${process.execPath}\n(async()=>{const {spawnSync}=await import('node:child_process');${common}\n${guard}\nconst r=spawnSync(${JSON.stringify(file)},[...${JSON.stringify(prefix)},...a],{cwd,env:process.env,stdio:'inherit',shell:false});process.exit(r.status??1);})();\n`,
      { mode: 0o755 },
    );
  }
  return {
    bin,
    permissions: ["shell(harness-e2e-plan)", "shell(openspec-e2e-plan)"],
  };
}
