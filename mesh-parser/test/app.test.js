import assert from 'node:assert/strict';
import test from 'node:test';
import {DateTime} from 'luxon';
import {createMeshService, normalizeHomeworks, normalizeSchedule} from '../src/app.js';

test('normalizes schedule and Moscow time', () => {
  const result = normalizeSchedule([{date: '2026-08-28', lessons: [{begin_time: '08:30', end_time: '09:15', subject_name: 'Алгебра'}]}]);
  assert.deepEqual(result, [{date: '2026-08-28', lessons: [{sourceId: '', begin: '08:30', end: '09:15', subject: 'Алгебра', topic: '', remote: false, location: ''}]}]);
});

test('normalizes current event calendar timestamps', () => {
  const result = normalizeSchedule([{date: '2026-08-28', lessons: [{id: 42, start_at: '2026-08-28T05:30:00Z', finish_at: '2026-08-28T06:15:00Z', subject_name: 'Геометрия'}]}]);
  assert.equal(result[0].lessons[0].sourceId, '42');
  assert.equal(result[0].lessons[0].begin, '08:30');
  assert.equal(result[0].lessons[0].end, '09:15');
});

test('normalizes homework without exposing unrelated profile data', () => {
  const result = normalizeHomeworks([{homework_entry_student_id: 7, subject_name: 'Физика', description: '§ 12', date: '2026-08-29', is_done: false, private_profile: {phone: 'secret'}}]);
  assert.equal(result.length, 1);
  assert.equal(result[0].subject, 'Физика');
  assert.equal(result[0].due, '2026-08-29');
  assert.equal('private_profile' in result[0], false);
});

test('builds overview for a week and returns structured data plus Telegram text', async () => {
  const calls = [];
  const client = {
    async getSchedule(dates) {
      calls.push(['schedule', dates.length]);
      return [{date: '2026-08-27', lessons: [{begin_time: '09:00', end_time: '09:45', subject_name: 'Русский язык'}]}];
    },
    async getHomeworks(from, to) {
      calls.push(['homework', from.toISODate(), to.toISODate()]);
      return [{subject_name: 'Русский язык', description: 'Упражнение 10', date: '2026-08-28', is_done: false}];
    },
  };
  const execute = createMeshService({client, now: () => DateTime.fromISO('2026-08-27T14:00:00+03:00'), cacheTtlMs: 0});
  const result = await execute({request: '/mesh'});
  assert.equal(result.ok, true);
  assert.equal(result.from, '2026-08-27');
  assert.equal(result.to, '2026-09-02');
  assert.match(result.text, /Русский язык/);
  assert.deepEqual(calls, [['schedule', 7], ['homework', '2026-08-27', '2026-09-02']]);
});

test('routes a homework request for tomorrow without loading schedule', async () => {
  let scheduleCalled = false;
  const client = {
    async getSchedule() { scheduleCalled = true; return []; },
    async getHomeworks() { return []; },
  };
  const execute = createMeshService({client, now: () => DateTime.fromISO('2026-08-27T10:00:00+03:00'), cacheTtlMs: 0});
  const result = await execute({request: 'Покажи домашнее задание на завтра'});
  assert.equal(result.action, 'homework');
  assert.equal(result.from, '2026-08-28');
  assert.equal(result.to, '2026-08-28');
  assert.equal(scheduleCalled, false);
});
