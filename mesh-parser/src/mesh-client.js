const BASE_URL = 'https://school.mos.ru';

export class MeshUpstreamError extends Error {
  constructor(message, {status = 502, code = 'MESH_UPSTREAM_ERROR', cause} = {}) {
    super(message, {cause});
    this.name = 'MeshUpstreamError';
    this.status = status;
    this.code = code;
  }
}

async function readResponse(response) {
  const text = await response.text();
  if (!text) return null;
  try { return JSON.parse(text); }
  catch { return text; }
}

function payloadOf(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.payload)) return value.payload;
  if (Array.isArray(value?.response)) return value.response;
  return [];
}

export function createMeshClient(config, fetchImpl = fetch) {
  let currentToken = config.token;
  let currentPersonId = '';

  if (!config.studentId || !currentToken) {
    throw new MeshUpstreamError('MESH_STUDENT_ID and MESH_TOKEN are required', {
      status: 503,
      code: 'MESH_NOT_CONFIGURED',
    });
  }

  function webHeaders(extra = {}) {
    return {
      accept: 'application/json, text/plain, */*',
      authorization: `Bearer ${currentToken}`,
      'profile-id': config.studentId,
      'profile-type': 'student',
      'x-mes-subsystem': 'familyweb',
      ...extra,
    };
  }

  async function request(path, {allowRefresh = true, headers = {}} = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), config.timeoutMs);
    let response;
    try {
      response = await fetchImpl(`${BASE_URL}${path}`, {
        headers: webHeaders(headers),
        signal: controller.signal,
      });
    } catch (error) {
      const timedOut = error?.name === 'AbortError';
      throw new MeshUpstreamError(timedOut ? 'MESH request timed out' : 'MESH is unavailable', {
        status: 502,
        code: timedOut ? 'MESH_TIMEOUT' : 'MESH_NETWORK_ERROR',
        cause: error,
      });
    } finally {
      clearTimeout(timeout);
    }

    if (response.status === 401 || response.status === 403) {
      if (allowRefresh && await refreshToken(fetchImpl)) return request(path, {allowRefresh: false, headers});
      throw new MeshUpstreamError('MESH token is expired or access was denied', {
        status: 401,
        code: 'MESH_AUTH_FAILED',
      });
    }
    const body = await readResponse(response);
    if (!response.ok) {
      throw new MeshUpstreamError(`MESH returned HTTP ${response.status}`, {
        status: 502,
        code: 'MESH_UPSTREAM_ERROR',
      });
    }
    return body;
  }

  async function getPersonId() {
    if (currentPersonId) return currentPersonId;
    const profile = await request('/api/family/web/v1/profile');
    const children = Array.isArray(profile?.children) ? profile.children : [];
    const child = children.find((item) => String(item?.id) === config.studentId) ?? children[0];
    currentPersonId = String(child?.contingent_guid ?? '').trim();
    if (!currentPersonId) {
      throw new MeshUpstreamError('MESH profile does not contain a student contingent GUID', {
        status: 502,
        code: 'MESH_PROFILE_ERROR',
      });
    }
    return currentPersonId;
  }

  async function refreshToken(fetcher = fetchImpl) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), config.timeoutMs);
    try {
      const response = await fetcher(`${BASE_URL}/v2/token/refresh`, {
        headers: {
          accept: 'application/json',
          authorization: `Bearer ${currentToken}`,
          cookie: 'cluster=0; aupd_current_role=2%3A1',
        },
        signal: controller.signal,
      });
      if (!response.ok) return false;
      const body = await readResponse(response);
      const nextToken = typeof body === 'string' ? body : body?.token ?? body?.auth_token ?? body?.authentication_token;
      if (!nextToken || typeof nextToken !== 'string') return false;
      currentToken = nextToken;
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timeout);
    }
  }

  return {
    async getSchedule(dates) {
      if (!dates.length) return [];
      const query = new URLSearchParams({
        begin_date: dates[0].toISODate(),
        end_date: dates.at(-1).toISODate(),
        person_ids: await getPersonId(),
        expand: 'marks,homework,absence_reason_id,health_status,nonattendance_reason_id',
        source_types: 'PLAN,AE,EC,EVENTS,AFISHA,ORGANIZER,OLYMPIAD,PROF',
      });
      const events = payloadOf(await request(`/api/eventcalendar/v1/api/events?${query}`, {
        headers: {'x-mes-role': 'student'},
      }));
      const days = new Map();
      for (const event of events) {
        const date = String(event?.start_at ?? '').slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
        if (!days.has(date)) days.set(date, []);
        days.get(date).push(event);
      }
      return [...days.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([date, lessons]) => ({date, lessons}));
    },

    async getHomeworks(from, to) {
      const query = new URLSearchParams({
        student_id: config.studentId,
        from: from.toISODate(),
        to: to.toISODate(),
      });
      return payloadOf(await request(`/api/family/web/v1/homeworks?${query}`));
    },
  };
}
