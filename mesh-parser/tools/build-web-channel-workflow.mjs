import { readFile, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

const [inputPath, outputPath, webSecret] = process.argv.slice(2);
if (!inputPath || !outputPath || !webSecret) throw new Error('Usage: node build-web-channel-workflow.mjs INPUT OUTPUT WEB_SECRET');

const workflow = JSON.parse(await readFile(inputPath, 'utf8'));
const byName = (name) => {
  const node = workflow.nodes.find((entry) => entry.name === name);
  if (!node) throw new Error(`Missing node: ${name}`);
  return node;
};

const configNode = byName('CONFIG — EDIT ME');
let configCode = configNode.parameters.jsCode;
configCode = configCode.replace('// TODO: edit only the CONFIG object below.', `// TODO: edit only the CONFIG object below.\nconst WEB_SECRET = '${webSecret}';`);
const parseStart = configCode.indexOf('const update = $input.first().json;');
const parseEnd = configCode.indexOf('\n\nreturn [{ json:');
if (parseStart < 0 || parseEnd < 0) throw new Error('CONFIG parser block not found');

const webAwareParser = `const update = $input.first().json;
const webBody = update.body && typeof update.body === 'object' ? update.body : {};
const isWeb = webBody.source === 'web';
const msg = update.message || update.channel_post || update.callback_query?.message || {};
const actor = update.callback_query?.from || msg.from || {};
const userId = isWeb ? 'web' : String(actor.id || '');
const chatId = isWeb ? null : msg.chat?.id;
const text = String(isWeb ? webBody.text : (update.callback_query?.data || msg.text || msg.caption || '')).trim();
const doc = isWeb ? null : msg.document;
const isPdf = Boolean(doc && (doc.mime_type === 'application/pdf' || String(doc.file_name || '').toLowerCase().endsWith('.pdf')));
const isForwarded = !isWeb && Boolean(msg.forward_origin || msg.forward_from_chat || msg.forward_from || msg.forward_date);
const isConfirm = /^\\/(confirm|cancel)\\s+[a-z0-9_-]+$/i.test(text);
const suppliedWebSecret = String(update.headers?.['x-spirit-key'] || update.headers?.['X-Spirit-Key'] || '');
const authorized = isWeb ? suppliedWebSecret === WEB_SECRET : userId === String(CONFIG.allowedTelegramUserId);
const source = isWeb ? 'web' : 'telegram';`;

configCode = configCode.slice(0, parseStart) + webAwareParser + configCode.slice(parseEnd);
configCode = configCode.replace('  config: CONFIG,\n', '  config: CONFIG,\n  source,\n');
configNode.parameters.jsCode = configCode;
byName('Split Telegram Reply').parameters.jsCode = `const out=[]; const source=$('CONFIG — EDIT ME').first().json.source||'telegram'; for(const item of $input.all()){const chat_id=item.json.chat_id; let rest=String(item.json.text??''); if(!rest) rest='Пустой ответ.'; while(rest.length>3900){let cut=rest.lastIndexOf('\\n',3900); if(cut<2500) cut=rest.lastIndexOf(' ',3900); if(cut<2500) cut=3900; out.push({json:{...item.json,source,chat_id,text:rest.slice(0,cut).trim()}}); rest=rest.slice(cut).trim();} if(rest) out.push({json:{...item.json,source,chat_id,text:rest}});} return out;`;

const splitPosition = byName('Split Telegram Reply').position;
const webhookName = 'Web App Webhook', routeName = 'Web Request?', prepareName = 'Prepare Web Response', respondName = 'Respond to Web App';
workflow.nodes.push(
  { parameters: { httpMethod: 'POST', path: 'spiritjeronion-web', responseMode: 'responseNode', options: {} }, type: 'n8n-nodes-base.webhook', typeVersion: 2, position: [-1080, -180], id: randomUUID(), name: webhookName, webhookId: randomUUID() },
  { parameters: { conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 }, combinator: 'and', conditions: [{ id: randomUUID(), leftValue: '={{ $json.source }}', rightValue: 'web', operator: { type: 'string', operation: 'equals' } }] }, options: {} }, type: 'n8n-nodes-base.if', typeVersion: 2.2, position: [splitPosition[0] + 230, splitPosition[1]], id: randomUUID(), name: routeName },
  { parameters: { jsCode: "return [{json:{reply:String($json.text||'Пустой ответ.')}}];" }, type: 'n8n-nodes-base.code', typeVersion: 2, position: [splitPosition[0] + 460, splitPosition[1] - 100], id: randomUUID(), name: prepareName },
  { parameters: { respondWith: 'json', responseBody: '={{ $json }}', options: {} }, type: 'n8n-nodes-base.respondToWebhook', typeVersion: 1.4, position: [splitPosition[0] + 690, splitPosition[1] - 100], id: randomUUID(), name: respondName },
);

workflow.connections[webhookName] = { main: [[{ node: 'CONFIG — EDIT ME', type: 'main', index: 0 }]] };
workflow.connections['Split Telegram Reply'] = { main: [[{ node: routeName, type: 'main', index: 0 }]] };
workflow.connections[routeName] = { main: [[{ node: prepareName, type: 'main', index: 0 }], [{ node: 'Send Reply', type: 'main', index: 0 }]] };
workflow.connections[prepareName] = { main: [[{ node: respondName, type: 'main', index: 0 }]] };
workflow.name = 'SpiritJeronion — Web + Telegram';
workflow.active = false;
await writeFile(outputPath, JSON.stringify(workflow, null, 2) + '\n', 'utf8');
