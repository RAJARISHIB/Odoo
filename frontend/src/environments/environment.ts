/**
 * Runtime endpoints. Both services run locally during development; point these
 * at the deployed hosts before building for production.
 */
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api/v1',
  wsUrl: 'ws://localhost:4000/ws',
  /**
   * Websocket reconnect ladder: wait 5s after the first drop, then double each
   * failed attempt up to a 30s ceiling. The connection is a nice-to-have — the
   * REST API is the source of truth — so retrying harder than this only burns
   * battery on a phone whose network is genuinely gone.
   */
  wsReconnectDelay: 5000,
  wsMaxReconnectDelay: 30000,
};
