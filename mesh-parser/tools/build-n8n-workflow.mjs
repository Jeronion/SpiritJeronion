import fs from 'node:fs';

const source = 'C:\\SpiritJeronion\\Личное\\SpiritJeronion-v2-patched-v3.json';
const target = 'C:\\SpiritJeronion\\Личное\\SpiritJeronion-MESH.json';
const workflow = JSON.parse(fs.readFileSync(source, 'utf8'));

function node(name) {
  const found = workflow.nodes.find((candidate) => candidate.name === name);
  if (!found) throw new Error(`Node not found: ${name}`);
  return found;
}

workflow.name = 'SpiritJeronion — MESH';
workflow.active = false;
delete workflow.id;
delete workflow.versionId;
delete workflow.meta;

const configNode = node('CONFIG — EDIT ME');
configNode.parameters.jsCode = configNode.parameters.jsCode.replace(
  "meshParserUrl: 'TODO_MESH_PARSER_ENDPOINT'",
  "meshParserUrl: 'http://127.0.0.1:8787/mesh'",
);

const classifier = node('Build Ollama Intent Request');
classifier.parameters.jsCode = classifier.parameters.jsCode.replace(
  '/help=help, /today=schedule_view, /news=news, /mesh=mesh_sync.',
  '/help=help, /today=schedule_view, /news=news, /mesh=mesh_sync. Любой запрос, где явно упомянуто МЭШ, классифицируй как mesh_sync.',
);

const setup = node('SETUP — optional integrations');
setup.parameters.content = `# Integrations

MESH подключён к локальному сервису:

- URL: http://127.0.0.1:8787/mesh
- перед активацией workflow запустите сервис в C:\\SpiritJeronion\\mesh-parser
- если задан MESH_SERVICE_KEY, добавьте credential Header Auth с заголовком X-Mesh-Key

GDZ и OpenAI/ChatGPT пока требуют реальные endpoints. Не храните токены в Code nodes.`;

const meshNode = node('TODO MESH parser endpoint');
const oldName = meshNode.name;
meshNode.name = 'MESH parser endpoint';
meshNode.alwaysOutputData = true;
meshNode.retryOnFail = true;
meshNode.maxTries = 2;
meshNode.waitBetweenTries = 1000;
meshNode.onError = 'continueRegularOutput';

workflow.connections[meshNode.name] = workflow.connections[oldName];
delete workflow.connections[oldName];
for (const connection of Object.values(workflow.connections)) {
  for (const groups of Object.values(connection)) {
    for (const group of groups) {
      for (const edge of group) {
        if (edge.node === oldName) edge.node = meshNode.name;
      }
    }
  }
}

node('Format MESH Reply').parameters.jsCode = `const req=$('Prepare MESH Parser').first().json;
const error=$json.error;
if(error){
  const details=typeof error==='string'?error:(error.message||JSON.stringify(error));
  return [{json:{chat_id:req.chat_id,text:'Не удалось получить данные МЭШ. Проверь, что локальный MESH parser запущен и токен auth_token ещё действует.\\n\\n'+details}}];
}
const value=$json.text||$json.summary||$json.result||'МЭШ вернул пустой ответ.';
return [{json:{chat_id:req.chat_id,text:String(value)}}];`;

fs.writeFileSync(target, `${JSON.stringify(workflow, null, 2)}\n`, 'utf8');
console.log(target);
