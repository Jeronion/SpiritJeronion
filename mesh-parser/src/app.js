import {DateTime} from 'luxon';

const ZONE = 'Europe/Moscow';

function textOf(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function toIsoDate(value) {
  if (!value) return '';
  if (typeof value?.toISODate === 'function') return value.toISODate();
  if (typeof value === 'string') {
    const iso = DateTime.fromISO(value, {zone: ZONE});
    if (iso.isValid) return iso.toISODate();
    const russian = DateTime.fromFormat(value, 'dd.MM.yyyy', {zone: ZONE});
    if (russian.isValid) return russian.toISODate();
  }
  return '';
}

function timeOf(lesson, key) {
  const direct = textOf(lesson?.[`${key}_time`] ?? lesson?.[key]);
  if (/^\d{1,2}:\d{2}/.test(direct)) return direct.slice(0, 5).padStart(5, '0');
  const eventTimestamp = key === 'begin' ? lesson?.start_at : lesson?.finish_at;
  if (eventTimestamp) {
    const parsed = DateTime.fromISO(String(eventTimestamp), {setZone: true});
    if (parsed.isValid) return parsed.setZone(ZONE).toFormat('HH:mm');
  }
  const seconds = lesson?.[`${key}_utc`];
  if (Number.isFinite(Number(seconds))) return DateTime.fromSeconds(Number(seconds), {zone: 'utc'}).setZone(ZONE).toFormat('HH:mm');
  return '';
}

export function normalizeSchedule(rawDays) {
  return (Array.isArray(rawDays) ? rawDays : []).map((day) => {
    const rawLessons = Array.isArray(day?.lessons) ? day.lessons : Array.isArray(day?.activities) ? day.activities : [];
    const lessons = rawLessons
      .filter((lesson) => (!lesson?.type || lesson.type === 'LESSON') && !lesson?.cancelled)
      .map((lesson) => ({
        sourceId: textOf(lesson.id ?? lesson.source_id),
        begin: timeOf(lesson, 'begin'),
        end: timeOf(lesson, 'end'),
        subject: textOf(lesson.subject_name ?? lesson.title ?? lesson.lesson?.subject_name ?? lesson.subject?.name),
        topic: textOf(lesson.lesson_theme ?? lesson.lesson_name ?? lesson.lesson?.lesson_name ?? lesson.topic),
        remote: lesson.lesson_type === 'REMOTE' || lesson.lesson?.lesson_type === 'REMOTE',
        location: textOf(lesson.room_name ?? lesson.room_number),
      }))
      .filter((lesson) => lesson.subject || lesson.begin);
    return {date: toIsoDate(day?.date), lessons};
  }).filter((day) => day.date || day.lessons.length);
}

export function normalizeHomeworks(rawItems) {
  return (Array.isArray(rawItems) ? rawItems : []).map((entry) => {
    const homework = entry?.homework_entry?.homework ?? entry?.homework ?? entry;
    const attachments = homework.attachments ?? entry.attachments ?? [];
    return {
      id: entry.homework_entry_student_id ?? entry.id ?? homework.id ?? null,
      subject: textOf(entry.subject_name ?? homework.subject_name ?? homework.subject?.name),
      description: textOf(entry.description ?? homework.description),
      due: toIsoDate(entry.date ?? entry.date_prepared_for ?? homework.date_prepared_for),
      assigned: toIsoDate(entry.date_assigned_on ?? homework.date_assigned_on),
      done: Boolean(entry.is_done ?? entry.id_done ?? entry.done),
      attachments: (Array.isArray(attachments) ? attachments : []).slice(0, 10).map((item) => ({
        name: textOf(item.name ?? item.file_name ?? item.title),
        url: textOf(item.url ?? item.download_url ?? item.link),
      })).filter((item) => item.name || /^https:\/\//i.test(item.url)),
    };
  }).filter((item) => item.subject || item.description);
}

function parseRequest(body, now) {
  const request = textOf(body?.request).toLowerCase();
  const explicitAction = textOf(body?.action).toLowerCase();
  let action = ['schedule', 'homework', 'overview'].includes(explicitAction) ? explicitAction : 'overview';
  if (/расписан|урок|schedule/.test(request)) action = 'schedule';
  else if (/домаш|\bдз\b|homework/.test(request)) action = 'homework';

  let period = textOf(body?.period).toLowerCase();
  if (!['today', 'tomorrow', 'week'].includes(period)) {
    period = /завтра|tomorrow/.test(request) ? 'tomorrow' : /недел|week/.test(request) ? 'week' : 'week';
  }

  const base = now.setZone(ZONE).startOf('day');
  const from = period === 'tomorrow' ? base.plus({days: 1}) : base;
  const to = period === 'week' ? from.plus({days: 6}) : from;
  return {action, period, from, to};
}

function dateLabel(date) {
  const parsed = DateTime.fromISO(date, {zone: ZONE});
  return parsed.isValid ? parsed.setLocale('ru').toFormat('ccc, dd.LL') : date;
}

function formatText({schedule, homeworks, action, from, to}) {
  const lines = ['🏫 МЭШ'];
  if (action !== 'homework') {
    lines.push('', '📅 Расписание:');
    const lessonLines = [];
    for (const day of schedule) {
      if (!day.lessons.length) continue;
      lessonLines.push(dateLabel(day.date));
      for (const lesson of day.lessons) {
        const time = [lesson.begin, lesson.end].filter(Boolean).join('–');
        lessonLines.push(`• ${time}${time ? ' — ' : ''}${lesson.subject || 'Урок'}${lesson.topic ? `: ${lesson.topic}` : ''}${lesson.remote ? ' (онлайн)' : ''}`);
      }
    }
    lines.push(...(lessonLines.length ? lessonLines : ['На выбранный период уроков нет.']));
  }
  if (action !== 'schedule') {
    lines.push('', '📚 Домашние задания:');
    const active = homeworks.filter((item) => !item.done);
    lines.push(...(active.length ? active.map((item) => `• ${item.due ? `${dateLabel(item.due)} — ` : ''}${item.subject || 'Предмет'}: ${item.description || 'Описание отсутствует'}`) : ['Невыполненных заданий на выбранный период нет.']));
  }
  lines.push('', `Период: ${from.toISODate()} — ${to.toISODate()}`);
  return lines.join('\n');
}

export function createMeshService({client, now = () => DateTime.now(), cacheTtlMs = 120000}) {
  const cache = new Map();
  return async function execute(body = {}) {
    const parsed = parseRequest(body, now());
    const cacheKey = `${parsed.action}:${parsed.from.toISODate()}:${parsed.to.toISODate()}`;
    const cached = cache.get(cacheKey);
    if (cached && cached.expires > Date.now()) return cached.value;

    const dates = [];
    for (let cursor = parsed.from; cursor <= parsed.to; cursor = cursor.plus({days: 1})) dates.push(cursor);
    const [rawSchedule, rawHomeworks] = await Promise.all([
      parsed.action === 'homework' ? Promise.resolve([]) : client.getSchedule(dates),
      parsed.action === 'schedule' ? Promise.resolve([]) : client.getHomeworks(parsed.from, parsed.to),
    ]);
    const schedule = normalizeSchedule(rawSchedule);
    const homeworks = normalizeHomeworks(rawHomeworks);
    const value = {
      ok: true,
      source: 'MESH',
      action: parsed.action,
      period: parsed.period,
      from: parsed.from.toISODate(),
      to: parsed.to.toISODate(),
      schedule,
      homeworks,
      text: formatText({...parsed, schedule, homeworks}),
    };
    if (cacheTtlMs > 0) cache.set(cacheKey, {expires: Date.now() + cacheTtlMs, value});
    return value;
  };
}
