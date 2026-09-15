/**
 * i18n для панели SberHome (no-build Lit).
 *
 * localize(lang, key, vars) — берёт строку из словаря языка, fallback
 * lang → ru → en → сам ключ. Плейсхолдеры вида {name} подставляются из vars.
 *
 * backendErrorMessage(hass, err) — текст ошибки сервиса/WS-команды Home
 * Assistant на языке пользователя по её ключу перевода.
 *
 * Localized(Base) — миксин: добавляет `this.t(key, vars)`, берущий язык из
 * `this.hass.language`. hass — reactive property, поэтому смена языка
 * автоматически перерисует шаблоны.
 */

import { DICTS } from "./dicts.js";

export function localize(lang, key, vars) {
  const code = String(lang || "ru").split("-")[0];
  const dict = DICTS[code] || DICTS.ru;
  let s = dict[key] ?? DICTS.ru[key] ?? DICTS.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ""));
  return s;
}

export const Localized = (Base) =>
  class extends Base {
    t(key, vars) {
      return localize(this.hass && this.hass.language, key, vars);
    }
  };

/**
 * Текст ошибки, которую вернул бэкенд Home Assistant (hass.callService/callWS).
 *
 * Сервисы SberHome поднимают исключения с ключом перевода; в поле `message`
 * сервер кладёт английский текст. Здесь сообщение берётся из переводов
 * `exceptions` интеграции на языке пользователя, плейсхолдеры подставляются
 * из `translation_placeholders`. Без ключа или перевода — `err.message`.
 */
export async function backendErrorMessage(hass, err) {
  const domain = err && err.translation_domain;
  const key = err && err.translation_key;
  if (hass && domain && key) {
    try {
      const result = await hass.callWS({
        type: "frontend/get_translations",
        language: hass.language || "en",
        category: "exceptions",
        integration: [domain],
      });
      const template = result?.resources?.[`component.${domain}.exceptions.${key}.message`];
      if (template) {
        const vars = err.translation_placeholders || {};
        return template.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? vars[name] : match));
      }
    } catch (_) {
      // Переводы недоступны — ниже покажем текст сервера.
    }
  }
  return (err && err.message) || String(err);
}
