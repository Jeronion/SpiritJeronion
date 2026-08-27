import fs from 'node:fs';

const source = 'C:\\SpiritJeronion\\Личное\\SpiritJeronion-MESH.json';
const target = 'C:\\SpiritJeronion\\Личное\\SpiritJeronion-MESH-Calendar.json';
const workflow = JSON.parse(fs.readFileSync(source, 'utf8'));

function node(name) {
  const found = workflow.nodes.find((candidate) => candidate.name === name);
  if (!found) throw new Error(`Node not found: ${name}`);
  return found;
}

function booleanIf(name, expression, id, position) {
  return {
    parameters: {
      conditions: {
        options: {caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2},
        combinator: 'and',
        conditions: [{
          id: `${id.slice(0, 8)}-0000-4000-8000-000000000001`,
          leftValue: expression,
          rightValue: '',
          operator: {type: 'boolean', operation: 'true', singleValue: true},
        }],
      },
      options: {},
    },
    name,
    type: 'n8n-nodes-base.if',
    typeVersion: 2.2,
    position,
    id,
  };
}

function codeNode(name, jsCode, id, position) {
  return {
    parameters: {jsCode},
    name,
    type: 'n8n-nodes-base.code',
    typeVersion: 2,
    position,
    id,
  };
}

workflow.name = 'SpiritJeronion — MESH Calendar';
workflow.active = false;
delete workflow.id;
delete workflow.versionId;
delete workflow.meta;

node('README on canvas').parameters.content = `# SpiritJeronion — MESH + Calendar

Команда /mesh получает расписание и домашние задания из МЭШ, затем добавляет отсутствующие уроки в Google Calendar.

- повторный запуск не создаёт дубликаты: каждому уроку добавляется скрытый MESH-ID в description
- отменённые уроки не добавляются
- если Google Calendar недоступен, синхронизация останавливается без создания событий
- workflow импортируется выключенным: проверьте credentials и затем активируйте его

Следующие интеграции по плану: ГДЗ, затем дополнительный решатель ChatGPT.`;

node('SETUP — optional integrations').parameters.content = `# Integrations

MESH parser: http://127.0.0.1:8787/mesh

/mesh синхронизирует расписание на неделю. Запрос «расписание МЭШ на завтра» синхронизирует только завтра.

GDZ и OpenAI/ChatGPT пока требуют реальные endpoints. Не храните токены в Code nodes.`;

node('Format MESH Reply').parameters.jsCode = `const req=$('Prepare MESH Parser').first().json;
const error=$json.error;
const details=typeof error==='string'?error:(error?.message||JSON.stringify(error||{}));
return [{json:{chat_id:req.chat_id,text:'Не удалось получить данные МЭШ. Проверь, что локальный MESH parser запущен и cookie aupd_token ещё действует.\\n\\n'+details}}];`;

const calendarTemplate = node('Calendar — list period');
const listMesh = structuredClone(calendarTemplate);
listMesh.name = 'Calendar — list MESH period';
listMesh.id = '0a8ad310-0d21-4fbd-8a8b-dff1dc94e100';
listMesh.position = [3312, 2304];
listMesh.parameters.limit = 250;
listMesh.parameters.timeMin = "={{ $json.from + 'T00:00:00+03:00' }}";
listMesh.parameters.timeMax = "={{ $json.to + 'T23:59:59+03:00' }}";
listMesh.parameters.options.timeZone.value = "={{ $('Prepare MESH Parser').first().json.config.timezone }}";

const prepareCode = `const mesh=$('MESH parser endpoint').first().json;
const req=$('Prepare MESH Parser').first().json;
const calendarItems=$input.all().map(item=>item.json);
if(calendarItems.some(item=>item.error)){
  return [{json:{chat_id:req.chat_id,has_missing:false,sync_error:true,mesh_reply:mesh.text||'Данные МЭШ получены.'}}];
}
const existing=calendarItems.filter(item=>item.id);
const desired=[];
for(const day of (Array.isArray(mesh.schedule)?mesh.schedule:[])){
  for(const lesson of (Array.isArray(day.lessons)?day.lessons:[])){
    if(!day.date||!lesson.begin||!lesson.end) continue;
    const identity=String(lesson.sourceId||[day.date,lesson.begin,lesson.end,lesson.subject].join('|')).replace(/[\\]\\r\\n]/g,'_');
    const marker='[MESH-ID:'+identity+']';
    const start=day.date+'T'+lesson.begin+':00+03:00';
    const end=day.date+'T'+lesson.end+':00+03:00';
    const title='МЭШ • '+(lesson.subject||'Урок');
    const duplicate=existing.some(event=>{
      if(String(event.description||'').includes(marker)) return true;
      const eventStart=String(event.start?.dateTime||event.start||'');
      return String(event.summary||'')===title && eventStart.slice(0,16)===start.slice(0,16);
    });
    if(duplicate) continue;
    const details=[marker,'Синхронизировано из МЭШ.',lesson.topic?('Тема: '+lesson.topic):'',lesson.location?('Кабинет: '+lesson.location):'',lesson.remote?'Онлайн-урок':''].filter(Boolean).join('\\n');
    desired.push({chat_id:req.chat_id,has_missing:true,title,start,end,description:details,mesh_reply:mesh.text||'Данные МЭШ получены.'});
  }
}
if(!desired.length) return [{json:{chat_id:req.chat_id,has_missing:false,sync_error:false,mesh_reply:mesh.text||'Данные МЭШ получены.'}}];
return desired.map((item)=>({json:{...item,missing_count:desired.length}}));`;

const responseOk = booleanIf('MESH response OK?', '={{ $json.ok === true }}', 'e489cc1a-27d5-40db-8526-0fe53d824101', [3072, 2336]);
const prepare = codeNode('Prepare MESH Calendar Events', prepareCode, '950b2afd-8eb3-4143-9693-35967b1c0102', [3552, 2304]);
const hasMissing = booleanIf('MESH Calendar events missing?', '={{ $json.has_missing }}', '3d2ca49d-d438-4c9e-a05d-a32d8eb4b103', [3792, 2304]);

const createTemplate = node('Calendar — CREATE confirmed');
const createMesh = structuredClone(createTemplate);
createMesh.name = 'Calendar — CREATE MESH lesson';
createMesh.id = 'a6d7c699-7e56-4e92-82a8-c841426b0104';
createMesh.position = [4032, 2224];
createMesh.parameters.start = '={{ $json.start }}';
createMesh.parameters.end = '={{ $json.end }}';
createMesh.parameters.additionalFields = {
  description: '={{ $json.description }}',
  summary: '={{ $json.title }}',
};
createMesh.retryOnFail = true;
createMesh.maxTries = 2;
createMesh.waitBetweenTries = 1000;
createMesh.onError = 'continueRegularOutput';

const synced = codeNode('Format MESH Calendar Sync', `const req=$('Prepare MESH Parser').first().json;
const mesh=$('MESH parser endpoint').first().json;
const total=$('Prepare MESH Calendar Events').all().filter(item=>item.json.has_missing).length;
const failed=$input.all().filter(item=>item.json.error).length;
const added=Math.max(0,total-failed);
const status=failed?('📆 Google Calendar: добавлено '+added+', ошибок '+failed+'.'):('📆 Google Calendar: добавлено событий — '+added+'.');
return [{json:{chat_id:req.chat_id,text:String(mesh.text||'Данные МЭШ получены.')+'\\n\\n'+status}}];`, 'bb6a715a-05b1-450c-bc7c-1d03a0912105', [4272, 2224]);

const noChanges = codeNode('Format MESH Calendar No Changes', `const req=$('Prepare MESH Parser').first().json;
const mesh=$('MESH parser endpoint').first().json;
const prepared=$input.first().json;
const status=prepared.sync_error?'📆 Google Calendar недоступен: расписание не изменено.':'📆 Google Calendar: все уроки уже добавлены, новых событий нет.';
return [{json:{chat_id:req.chat_id,text:String(mesh.text||'Данные МЭШ получены.')+'\\n\\n'+status}}];`, '86c4db4d-f66d-49ab-87f3-56c5d8d5c106', [4032, 2416]);

workflow.nodes.push(responseOk, listMesh, prepare, hasMissing, createMesh, synced, noChanges);

workflow.connections['MESH parser endpoint'] = {main: [[{node: responseOk.name, type: 'main', index: 0}]]};
workflow.connections[responseOk.name] = {main: [
  [{node: listMesh.name, type: 'main', index: 0}],
  [{node: 'Format MESH Reply', type: 'main', index: 0}],
]};
workflow.connections[listMesh.name] = {main: [[{node: prepare.name, type: 'main', index: 0}]]};
workflow.connections[prepare.name] = {main: [[{node: hasMissing.name, type: 'main', index: 0}]]};
workflow.connections[hasMissing.name] = {main: [
  [{node: createMesh.name, type: 'main', index: 0}],
  [{node: noChanges.name, type: 'main', index: 0}],
]};
workflow.connections[createMesh.name] = {main: [[{node: synced.name, type: 'main', index: 0}]]};
workflow.connections[synced.name] = {main: [[{node: 'Split Telegram Reply', type: 'main', index: 0}]]};
workflow.connections[noChanges.name] = {main: [[{node: 'Split Telegram Reply', type: 'main', index: 0}]]};

fs.writeFileSync(target, `${JSON.stringify(workflow, null, 2)}\n`, 'utf8');
console.log(target);
