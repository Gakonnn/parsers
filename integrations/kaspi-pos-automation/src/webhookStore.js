import fs from 'fs';
import path from 'path';
import { STATE_DIR } from './config.js';

const WEBHOOKS_FILE = process.env.KASPI_POS_WEBHOOKS_FILE
  ? path.resolve(process.env.KASPI_POS_WEBHOOKS_FILE)
  : path.join(STATE_DIR, 'webhooks.json');

/**
 * Читает webhooks.json и возвращает массив вебхуков.
 * При ошибке чтения/парсинга возвращает [].
 */
export const loadWebhooks = () => {
  try {
    const raw = fs.readFileSync(WEBHOOKS_FILE, 'utf8');
    const hooks = JSON.parse(raw);
    if (!Array.isArray(hooks)) return [];
    return hooks;
  } catch (err) {
    if (err.code !== 'ENOENT') {
      console.error('[WEBHOOK STORE] Error reading webhooks.json:', err.message);
    }
    if (process.env.KASPI_POS_DEFAULT_WEBHOOK_URL && process.env.KASPI_POS_DEFAULT_WEBHOOK_SECRET) {
      return [
        {
          url: process.env.KASPI_POS_DEFAULT_WEBHOOK_URL,
          events: ['payment.success', 'payment.failed', 'payment.expired'],
          secret: process.env.KASPI_POS_DEFAULT_WEBHOOK_SECRET,
        },
      ];
    }
    return [];
  }
};

/**
 * Возвращает вебхуки, подписанные на указанное событие.
 */
export const getWebhooksByEvent = (event) => {
  return loadWebhooks().filter((hook) => hook.url && Array.isArray(hook.events) && hook.events.includes(event));
};
