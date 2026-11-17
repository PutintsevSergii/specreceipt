/** Isolated design preview: synthetic tasks, never a project's execution evidence. */
import { mkdtempSync, rmSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startUI, askQuestion } from '../dist/ui.js';
const root = realpathSync(mkdtempSync(join(tmpdir(), 'specreceipt-ui-demo-')));
const rows = [
  ['UI-001','Единое рабочее пространство','IN_PROGRESS','Codex'],
  ['CLI-024','Понятные сообщения об ошибках','IN_PROGRESS','Codex'],
  ['NAV-012','Быстрый поиск по задачам','TODO','—'],
  ['CORE-018','Экспорт отчёта о выполнении','TODO','—'],
  ['FIX-031','Проверка окружения Windows','BLOCKED','Copilot'],
  ['REV-009','Улучшить пакет согласования','VERIFIED','Codex'],
  ['DOC-016','Обновить руководство запуска','DONE','Codex'],
  ['TEST-022','Покрыть сценарий восстановления','DONE','Copilot'],
];
const tasks = rows.map(([task_id,title,status,agent])=>({task_id,title,status,effective_status:status,agent,workflow:'STANDARD',documentation:'formal',paths:{project:root},changed_files:status==='TODO'?[]:[{path:'src/example.ts',change:'modified'}],verification:{status:status==='DONE'||status==='VERIFIED'?'PASS':'MISSING',checks:status==='VERIFIED'?[{check:'unit-tests',result:'PASS',summary:'Демонстрационные данные · 24 теста пройдено'}]:[]},approvals:{review:{required:true,status:status==='VERIFIED'?'CURRENT':'NOT_RECORDED'},developer:{required:true,status:status==='DONE'?'CURRENT':'NOT_RECORDED'}},warnings:status==='BLOCKED'?['Не найден необходимый runtime для native Windows. Требуется проверка окружения.']:[],implementation_summary:'Демонстрационные данные для предварительного просмотра интерфейса.',next_action:{action:status==='VERIFIED'?'approval':'progress',message:status==='BLOCKED'?'Отсутствует Windows runtime':status==='VERIFIED'?'Результат готов к проверке разработчиком.':'Продолжить работу по плану.'}}));
const engine=(_root,argv)=>({exitCode:0,data:argv[0]==='status'?{project:'Демо · SpecReceipt',demo:true,tasks,generated_at:new Date().toISOString()}: {result:'BLOCKED',reason:'Это демонстрационный просмотр. Реальные согласования доступны в установленном проекте.'}});
askQuestion(root,'UI-001','Как показывать завершённые задачи: оставлять на доске или скрывать по умолчанию?',engine);
const { server, url } = await startUI(root,Number(process.env.PORT||4317),engine);
console.log('DEMO ONLY — synthetic tasks, temporary answers\n'+url);
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>server.close(()=>{rmSync(root,{recursive:true,force:true});}));
