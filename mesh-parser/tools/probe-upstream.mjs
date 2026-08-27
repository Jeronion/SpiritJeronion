import {readConfig} from '../src/config.js';

const config = readConfig();
const headers = {
  accept: 'application/json',
  'auth-token': config.token,
  'x-mes-subsystem': 'familymp',
};
const webHeaders = {
  accept: 'application/json, text/plain, */*',
  authorization: `Bearer ${config.token}`,
  'profile-id': config.studentId,
  'profile-type': 'student',
  'x-mes-subsystem': 'familyweb',
};
const student = encodeURIComponent(config.studentId);
const probes = [
  ['schedule-short', `/api/family/mobile/v1/schedule/short/?student_id=${student}&dates=2026-08-27,2026-08-28`],
  ['schedule-day', `/api/family/mobile/v1/schedule/?student_id=${student}&date=2026-08-27`],
  ['homeworks', `/api/family/mobile/v1/homeworks/?student_id=${student}&from=2026-08-27&to=2026-08-28`],
  ['homeworks-short', `/api/family/mobile/v1/homeworks/short?student_id=${student}&from=2026-08-27&to=2026-08-28`],
];

for (const [name, path] of probes) {
  try {
    const response = await fetch(`https://school.mos.ru${path}`, {headers});
    let shape = 'non-json';
    try {
      const body = await response.json();
      shape = Array.isArray(body) ? 'array' : Object.keys(body ?? {}).sort().join(',');
    } catch {}
    console.log(`${name}: HTTP ${response.status}; shape=${shape}`);
  } catch (error) {
    console.log(`${name}: network error ${error?.cause?.code ?? error?.code ?? error?.name}`);
  }
}

let personId = '';
try {
  const profileResponse = await fetch('https://school.mos.ru/api/family/web/v1/profile', {headers: webHeaders});
  const profile = await profileResponse.json();
  const child = profile?.children?.find((item) => String(item?.id) === config.studentId) ?? profile?.children?.[0];
  personId = String(child?.contingent_guid ?? '');
  console.log(`profile-web: HTTP ${profileResponse.status}; person-id=${personId ? 'found' : 'missing'}`);
} catch (error) {
  console.log(`profile-web: network error ${error?.cause?.code ?? error?.code ?? error?.name}`);
}

for (const [name, path, extraHeaders] of [
  ['homeworks-web', `/api/family/web/v1/homeworks?student_id=${student}&from=2026-08-27&to=2026-08-28`, {}],
  ['events', `/api/eventcalendar/v1/api/events?begin_date=2026-08-27&end_date=2026-08-28&person_ids=${encodeURIComponent(personId)}&expand=marks,homework,absence_reason_id,health_status,nonattendance_reason_id&source_types=PLAN,AE,EC,EVENTS,AFISHA,ORGANIZER,OLYMPIAD,PROF`, {'x-mes-role': 'student'}],
]) {
  try {
    const response = await fetch(`https://school.mos.ru${path}`, {headers: {...webHeaders, ...extraHeaders}});
    let shape = 'non-json';
    try {
      const body = await response.json();
      shape = Array.isArray(body) ? 'array' : Object.keys(body ?? {}).sort().join(',');
    } catch {}
    console.log(`${name}: HTTP ${response.status}; shape=${shape}`);
  } catch (error) {
    console.log(`${name}: network error ${error?.cause?.code ?? error?.code ?? error?.name}`);
  }
}
