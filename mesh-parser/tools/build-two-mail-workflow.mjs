import fs from 'node:fs';

const source = 'C:\\SpiritJeronion\\Личное\\SpiritJeronion-MESH-Calendar.json';
const target = 'C:\\SpiritJeronion\\Личное\\SpiritJeronion-MESH-Calendar-2Mail.json';
const workflow = JSON.parse(fs.readFileSync(source, 'utf8'));

function node(name) {
  const found = workflow.nodes.find((candidate) => candidate.name === name);
  if (!found) throw new Error(`Node not found: ${name}`);
  return found;
}

function tagNode(name, mailbox, id, position) {
  return {
    parameters: {
      jsCode: `return $input.all().map(item=>({json:{...item.json,mailbox:${JSON.stringify(mailbox)}}}));`,
    },
    name,
    type: 'n8n-nodes-base.code',
    typeVersion: 2,
    position,
    id,
  };
}

workflow.name = 'SpiritJeronion — MESH Calendar + 2 Mail';
workflow.active = false;
delete workflow.id;
delete workflow.versionId;
delete workflow.meta;

const personal = node('Gmail — recent mail');
const oldPersonalName = personal.name;
personal.name = 'Gmail — Личная почта';
personal.position = [2352, 1776];

const school = structuredClone(personal);
school.name = 'Gmail — Почта лицея';
school.id = '2c44650e-dcf7-46e6-96fd-f270658f0201';
school.webhookId = 'd31c322a-64bd-4de9-b1aa-218bc71f0202';
school.position = [2352, 1936];
delete school.credentials;

const tagPersonal = tagNode('Пометить письма — Личная', 'Личная', '43aa8d98-585d-4f7b-9322-a922a6850203', [2592, 1776]);
const tagSchool = tagNode('Пометить письма — Лицей', 'Лицей', '25da0b69-4a79-481d-914b-236a92f00204', [2592, 1936]);
const merge = {
  parameters: {mode: 'append', numberInputs: 2},
  name: 'Объединить две почты',
  type: 'n8n-nodes-base.merge',
  typeVersion: 3.2,
  position: [2832, 1840],
  id: 'f31ddba8-c34b-4f58-858e-fe352d0d0205',
};

workflow.nodes.push(school, tagPersonal, tagSchool, merge);

if (workflow.connections[oldPersonalName] && oldPersonalName !== personal.name) {
  workflow.connections[personal.name] = workflow.connections[oldPersonalName];
  delete workflow.connections[oldPersonalName];
}
workflow.connections[personal.name] = {main: [[{node: tagPersonal.name, type: 'main', index: 0}]]};
workflow.connections[school.name] = {main: [[{node: tagSchool.name, type: 'main', index: 0}]]};
workflow.connections[tagPersonal.name] = {main: [[{node: merge.name, type: 'main', index: 0}]]};
workflow.connections[tagSchool.name] = {main: [[{node: merge.name, type: 'main', index: 1}]]};
workflow.connections[merge.name] = {main: [[{node: 'Build News Summary Request', type: 'main', index: 0}]]};

const route = workflow.connections['Route Intent'];
const newsOutput = route?.main?.[5];
if (!newsOutput) throw new Error('Route Intent news output not found');
for (const edge of newsOutput) {
  if (edge.node === oldPersonalName) edge.node = personal.name;
}
if (!newsOutput.some((edge) => edge.node === school.name)) {
  newsOutput.push({node: school.name, type: 'main', index: 0});
}

const summary = node('Build News Summary Request');
summary.position = [3072, 1840];
summary.parameters.jsCode = summary.parameters.jsCode
  .replace(
    "const mail=$input.all().map(i=>i.json).filter(m=>m.id).slice(0,30).map(m=>({from:m.from||m.From||'',subject:m.subject||m.Subject||'',snippet:m.snippet||m.textPlain||m.text||''}))",
    "const mail=$input.all().map(i=>i.json).filter(m=>m.id).slice(0,40).map(m=>({mailbox:m.mailbox||'Почта',from:m.from||m.From||'',subject:m.subject||m.Subject||'',snippet:m.snippet||m.textPlain||m.text||''}))",
  )
  .replace(
    "const mail=$input.all().map(i=>i.json).filter(m=>m.id).slice(0,40).map(m=>({mailbox:m.mailbox||'Почта',from:m.from||m.From||'',subject:m.subject||m.Subject||'',snippet:m.snippet||m.textPlain||m.text||''})).filter(m=>!sensitive.test(m.subject+' '+m.snippet)).slice(0,20).map(m=>({from:redact(m.from),subject:redact(m.subject),snippet:redact(m.snippet)}));",
    "const safeMail=$input.all().map(i=>i.json).filter(m=>m.id).map(m=>({mailbox:m.mailbox||'Почта',from:m.from||m.From||'',subject:m.subject||m.Subject||'',snippet:m.snippet||m.textPlain||m.text||''})).filter(m=>!sensitive.test(m.subject+' '+m.snippet)); const mail=['Личная','Лицей'].flatMap(label=>safeMail.filter(m=>m.mailbox===label).slice(0,10)).map(m=>({mailbox:m.mailbox,from:redact(m.from),subject:redact(m.subject),snippet:redact(m.snippet)}));",
  );

node('Ollama — summarize news').position = [3312, 1840];
node('Format Ollama Reply').position = [3552, 1840];

node('SETUP — optional integrations').parameters.content += `\n\n## Две почты\n\n- Личная почта уже использует существующий Gmail credential.\n- В узле «Gmail — Почта лицея» выберите новый Gmail OAuth2 credential для второго аккаунта.\n- Команда /news объединяет письма из обеих почт и помечает их как «Личная» или «Лицей».`;

fs.writeFileSync(target, `${JSON.stringify(workflow, null, 2)}\n`, 'utf8');
console.log(target);
