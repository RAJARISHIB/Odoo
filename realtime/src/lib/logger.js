/** Minimal levelled logger - no dependency, structured enough to grep. */
import { config } from '../config.js';

const LEVELS = { error: 0, warn: 1, info: 2, debug: 3 };
const threshold = LEVELS[config.logLevel] ?? LEVELS.info;

function emit(level, message, meta) {
  if (LEVELS[level] > threshold) return;
  const line = `[${new Date().toISOString()}] ${level.toUpperCase()} ${message}`;
  const payload = meta && Object.keys(meta).length ? ` ${JSON.stringify(meta)}` : '';
  const sink = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
  sink(line + payload);
}

export const logger = {
  error: (message, meta) => emit('error', message, meta),
  warn: (message, meta) => emit('warn', message, meta),
  info: (message, meta) => emit('info', message, meta),
  debug: (message, meta) => emit('debug', message, meta),
};

export default logger;
