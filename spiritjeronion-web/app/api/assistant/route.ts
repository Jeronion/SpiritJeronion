export async function POST(request: Request) {
  const body = await request.json().catch(() => ({})) as { message?: string };
  const message = String(body.message || '').trim();
  if (!message) return Response.json({ reply: 'Напиши вопрос или задание.' }, { status: 400 });
  const webhookUrl = process.env.N8N_WEBHOOK_URL;
  if (!webhookUrl) return Response.json({ reply: 'Интерфейс уже работает. Теперь нужно добавить отдельный Webhook в n8n и указать его адрес в настройках сайта.' });
  try {
    const upstream = await fetch(webhookUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Spirit-Key': process.env.SPIRIT_API_KEY || '' }, body: JSON.stringify({ source: 'web', text: message }) });
    const data = await upstream.json().catch(() => ({})) as { reply?: string; text?: string };
    if (!upstream.ok) throw new Error(`n8n returned ${upstream.status}`);
    return Response.json({ reply: data.reply || data.text || 'Готово.' });
  } catch { return Response.json({ reply: 'Не удалось связаться с n8n. Проверь, что workflow активен и туннель запущен.' }, { status: 502 }); }
}
