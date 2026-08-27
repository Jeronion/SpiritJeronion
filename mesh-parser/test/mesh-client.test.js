import assert from 'node:assert/strict';
import test from 'node:test';
import {DateTime} from 'luxon';
import {createMeshClient} from '../src/mesh-client.js';

test('loads profile and uses the current event calendar endpoint', async () => {
  const requests = [];
  const fetchImpl = async (url, options) => {
    requests.push({url: String(url), options});
    const body = String(url).includes('/profile')
      ? {children: [{id: 123456, contingent_guid: 'person-guid'}]}
      : {response: [{start_at: '2026-08-28T08:30:00+03:00', subject_name: 'Алгебра'}]};
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: {'content-type': 'application/json'},
    });
  };
  const client = createMeshClient({
    studentId: '123456',
    token: 'access-token',
    timeoutMs: 1000,
  }, fetchImpl);

  await client.getSchedule([DateTime.fromISO('2026-08-28')]);

  assert.equal(requests.length, 2);
  assert.match(requests[0].url, /\/api\/family\/web\/v1\/profile/);
  assert.match(requests[1].url, /\/api\/eventcalendar\/v1\/api\/events/);
  assert.match(requests[1].url, /person_ids=person-guid/);
  assert.equal(requests[1].options.headers.authorization, 'Bearer access-token');
  assert.equal(requests[1].options.headers['profile-id'], '123456');
  assert.equal(requests[1].options.headers['x-mes-subsystem'], 'familyweb');
  assert.equal(requests[1].options.headers['x-mes-role'], 'student');
});

test('uses the current family web homework endpoint', async () => {
  let request;
  const fetchImpl = async (url, options) => {
    request = {url: String(url), options};
    return new Response(JSON.stringify({payload: []}), {status: 200});
  };
  const client = createMeshClient({studentId: '123456', token: 'access-token', timeoutMs: 1000}, fetchImpl);
  await client.getHomeworks(DateTime.fromISO('2026-08-28'), DateTime.fromISO('2026-08-29'));
  assert.match(request.url, /\/api\/family\/web\/v1\/homeworks/);
  assert.match(request.url, /student_id=123456/);
  assert.equal(request.options.headers.authorization, 'Bearer access-token');
});
