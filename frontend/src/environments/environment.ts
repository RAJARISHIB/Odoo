/**
 * Runtime endpoints. Both services run locally during development; point these
 * at the deployed hosts before building for production.
 */
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api/v1',
  wsUrl: 'ws://localhost:4000/ws',
  /** Milliseconds between websocket reconnect attempts (doubles up to a cap). */
  wsReconnectDelay: 2000,
  wsMaxReconnectDelay: 30000,
};
