/** Cross-service integration check: Django API + Express hub + JWT auth. */
import { WebSocket } from 'ws';

const API = 'http://localhost:8000/api/v1';
let pass = 0;
let fail = 0;

function check(name, ok, extra = '') {
  if (ok) { pass++; console.log(`  PASS  ${name}`); }
  else { fail++; console.log(`  FAIL  ${name} ${extra}`); }
}

async function call(path, { method = 'GET', token, body } = {}) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: response.status, json: await response.json().catch(() => ({})) };
}

console.log('\n1. Authentication');
const adminLogin = await call('/auth/login', {
  method: 'POST', body: { email: 'admin@acme.test', password: 'Password123' },
});
check('admin login returns 200', adminLogin.status === 200, adminLogin.status);
check('access token issued', !!adminLogin.json.data?.tokens?.access_token);
check('panel resolves to admin', adminLogin.json.data?.user?.panel === 'admin');
const adminToken = adminLogin.json.data?.tokens?.access_token;
const adminRefresh = adminLogin.json.data?.tokens?.refresh_token;

const badLogin = await call('/auth/login', {
  method: 'POST', body: { email: 'admin@acme.test', password: 'wrong-password' },
});
check('wrong password rejected with 401', badLogin.status === 401, badLogin.status);
check('error envelope has a code', badLogin.json.error?.code === 'invalid_credentials');

const empLogin = await call('/auth/login', {
  method: 'POST', body: { email: 'dev@acme.test', password: 'Password123' },
});
check('employee login returns 200', empLogin.status === 200, empLogin.status);
check('employee panel resolves to user', empLogin.json.data?.user?.panel === 'user');
const empToken = empLogin.json.data?.tokens?.access_token;

console.log('\n2. Authorization');
const noToken = await call('/auth/me');
check('unauthenticated /me is 401', noToken.status === 401, noToken.status);

const empListsUsers = await call('/users', { token: empToken });
check('employee blocked from user directory (403)', empListsUsers.status === 403, empListsUsers.status);

const adminListsUsers = await call('/users', { token: adminToken });
check('admin can list users', adminListsUsers.status === 200 && Array.isArray(adminListsUsers.json.data));
check('list carries pagination meta', typeof adminListsUsers.json.meta?.total === 'number');

const badToken = await call('/auth/me', { token: 'not-a-real-token' });
check('garbage token is 401', badToken.status === 401, badToken.status);

console.log('\n3. Websocket delivery (Django -> hub -> browser)');
const socket = new WebSocket(`ws://localhost:4000/ws?token=${adminToken}&panel=admin`);
const received = [];
let connectedPayload = null;

await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('ws connect timeout')), 8000);
  socket.on('message', (raw) => {
    const message = JSON.parse(raw.toString());
    if (message.type === 'connected') {
      connectedPayload = message.payload;
      clearTimeout(timer);
      resolve();
    }
    if (message.type === 'event') received.push(message);
  });
  socket.on('error', reject);
});

check('socket authenticated with the Django token', !!connectedPayload?.connectionId);
check('auto-subscribed to the admin panel channel',
  connectedPayload.channels.some((channel) => channel.endsWith(':panel:admin')));

socket.send(JSON.stringify({
  type: 'ui.context',
  payload: { panel: 'admin', route: '/admin/attendance', view: 'attendance-board' },
}));

// A cross-tenant channel must be refused.
socket.send(JSON.stringify({ type: 'subscribe', channels: ['org:000000000000000000000000'] }));
const subscribeReply = await new Promise((resolve) => {
  socket.on('message', function handler(raw) {
    const message = JSON.parse(raw.toString());
    if (message.type === 'subscribed') { socket.off('message', handler); resolve(message); }
  });
});
check('foreign org channel rejected', subscribeReply.payload.rejected.length === 1);

console.log('\n4. Attendance flow');
const checkIn = await call('/attendance/check-in', { method: 'POST', token: empToken, body: { note: 'e2e' } });
check('employee check-in returns 201', checkIn.status === 201, JSON.stringify(checkIn.json).slice(0, 120));
check('a work session was opened', checkIn.json.data?.is_checked_in === true);

const duplicate = await call('/attendance/check-in', { method: 'POST', token: empToken });
check('double check-in rejected with 409', duplicate.status === 409, duplicate.status);

await new Promise((resolve) => setTimeout(resolve, 700));
const pushed = received.find((message) => message.event === 'attendance.checked_in');
check('admin socket received attendance.checked_in', !!pushed);
check('event payload names the employee', pushed?.payload?.user?.name === 'Vikram Rao', pushed?.payload?.user?.name);

const checkOut = await call('/attendance/check-out', { method: 'POST', token: empToken });
check('check-out returns 200', checkOut.status === 200, checkOut.status);
check('session closed', checkOut.json.data?.is_checked_in === false);

await new Promise((resolve) => setTimeout(resolve, 700));
check('admin socket received attendance.checked_out',
  received.some((message) => message.event === 'attendance.checked_out'));

const overview = await call('/admin/attendance/overview', { token: adminToken });
check('admin overview returns headcount', typeof overview.json.data?.headcount === 'number');

const mySummary = await call('/attendance/me/summary', { token: empToken });
check('employee summary computes hours', typeof mySummary.json.data?.total_hours === 'number');

console.log('\n5. Token refresh + logout');
const refreshed = await call('/auth/refresh', { method: 'POST', body: { refresh_token: adminRefresh } });
check('refresh issues a new pair', refreshed.status === 200 && !!refreshed.json.data?.tokens?.access_token);

const reuse = await call('/auth/refresh', { method: 'POST', body: { refresh_token: adminRefresh } });
check('used refresh token is revoked (401)', reuse.status === 401, reuse.status);

const newAccess = refreshed.json.data.tokens.access_token;
const meAfter = await call('/auth/me', { token: newAccess });
check('new access token works', meAfter.status === 200 && !!meAfter.json.data?.permissions);

const orgUpdate = await call('/organization', {
  method: 'PATCH', token: newAccess, body: { late_grace_minutes: 20 },
});
check('admin can update org policy', orgUpdate.status === 200 && orgUpdate.json.data?.late_grace_minutes === 20);

const badPatch = await call('/organization', {
  method: 'PATCH', token: newAccess, body: { work_start_time: '99:99' },
});
check('invalid time returns 422 with field details',
  badPatch.status === 422 && !!badPatch.json.error?.details?.work_start_time, badPatch.status);

socket.close();
console.log(`\n${pass} passed, ${fail} failed\n`);
process.exit(fail ? 1 : 0);
