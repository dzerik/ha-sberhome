/**
 * i18n для панели SberHome (no-build Lit).
 *
 * localize(lang, key, vars) — берёт строку из словаря языка, fallback
 * lang → ru → en → сам ключ. Плейсхолдеры вида {name} подставляются из vars.
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
