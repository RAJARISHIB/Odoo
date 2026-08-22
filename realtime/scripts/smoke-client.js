/**
 * End-to-end smoke test for the hub - no Django or Mongo required.
 *
 *   npm run smoke
 *
 * Mints a dev token with the configured secret, opens a socket, sends UI
 * context, publishes an event through the internal endpoint and asserts it
 * comes back over the websocket.
 */
import jwt from 'jsonwebtoken';
import { WebSocket } from 'ws';

import { config } from '../src/config.js';

const USER = {
  sub: '64f000000000000000000001',
  email: 'admin@acme.test',
  name: 'Aisha Kapoor',
  role: 'admin',
  org_id: '64f0000000000000000000ff',
};

const token = jwt.sign({ ...USER, typ: 'access' }, config.jwt.secret, {
  algorithm: config.jwt.algorithm,
  issuer: config.jwt.issuer,
  expiresIn: '10m',
  jwtid: 'smoke-test',
});

const base = `http://localhost:${config.port}`;
const url = `ws://localhost:${config.port}${config.wsPath}?token=${token}&panel=admin`;

const socket = new WebSocket(url);
let received = 0;

const timeout = setTimeout(() => {
  console.error('FAIL: timed out waiting for the published event.');
  process.exit(1);
}, 10000);

socket.on('open', () => console.log('socket open ->', url.split('?')[0]));

socket.on('message', async (raw) => {
  const message = JSON.parse(raw.toString());
  console.log('<-', message.type, JSON.stringify(message.payload ?? message.event));

  if (message.type === 'connected') {
    socket.send(JSON.stringify({
      type: 'ui.context',
      payload: { panel: 'admin', route: '/admin/attendance', view: 'attendance-board' },
    }));
    socket.send(JSON.stringify({ type: 'ping' }));

    // Django's side of the flow.
    const response = await fetch(`${base}/internal/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-internal-key': config.internalApiKey },
      body: JSON.stringify({
        event: 'attendance.checked_in',
        channels: [`org:${USER.org_id}:panel:admin`],
        payload: { user: { id: USER.sub, name: USER.name }, attendance: { status: 'present' } },
        source: 'smoke-test',
      }),
    });
    console.log('publish ->', response.status, JSON.stringify(await response.json()));
  }

  if (message.type === 'event' && message.event === 'attendance.checked_in') {
    received += 1;
    console.log('\nPASS: event delivered over the websocket.');
    clearTimeout(timeout);
    socket.close();
  }
});

socket.on('close', () => process.exit(received ? 0 : 1));
socket.on('error', (error) => {
  console.error('socket error:', error.message);
  process.exit(1);
});
