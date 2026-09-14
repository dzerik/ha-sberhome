/**
 * SberHome — компактная кнопка «копировать» перед показанным JSON.
 *
 * Перенесено из Sber MQTT Bridge. Таблицы показывают JSON обрезанным до
 * строки, а полный текст жил только во всплывающей подсказке, которую на
 * телефоне не открыть. Кнопка стоит в начале такой строки и копирует
 * значение целиком.
 *
 * ``value`` — строка (копируется как есть) или любое JSON-значение
 * (копируется отформатированным). Результат на мгновение виден на кнопке.
 */

import { LitElement, html, css } from "../lit-base.js";
import { Localized } from "../i18n/index.js";
import { copyText } from "./sberhome-json-block.js";

/** Сколько миллисекунд на кнопке виден ✓ / ✗. */
const FEEDBACK_MS = 1500;

/**
 * Текст, в виде которого копируется значение.
 *
 * @param {*} value Строка, объект или любое JSON-значение.
 * @returns {string}
 */
export function copyableText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export class SberhomeCopyButton extends Localized(LitElement) {
  static get properties() {
    return {
      hass: { type: Object },
      /** Что копировать — строка или JSON-значение. */
      value: { attribute: false },
      _state: { state: true },
    };
  }

  constructor() {
    super();
    this.value = null;
    this._state = "";
    this._timer = null;
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this._timer);
  }

  async _copy(event) {
    /* Строки и заголовки вокруг кнопки часто сами кликабельны. */
    event.stopPropagation();
    const ok = await copyText(copyableText(this.value));
    this._state = ok ? "ok" : "failed";
    clearTimeout(this._timer);
    this._timer = setTimeout(() => {
      this._state = "";
    }, FEEDBACK_MS);
  }

  render() {
    const key = this._state === "ok" ? "json.copied" : this._state === "failed" ? "json.copy_failed" : "json.copy";
    const icon = this._state === "ok" ? "✓" : this._state === "failed" ? "✗" : "\u{1F4CB}";
    return html`<button type="button" class="copy ${this._state}" title=${this.t(key)} aria-label=${this.t(key)}
      @click=${this._copy} @keydown=${(e) => e.stopPropagation()}>${icon}</button>`;
  }

  static get styles() {
    return css`
      :host { display: inline-block; vertical-align: middle; margin-right: 6px; }
      .copy {
        min-width: 26px;
        height: 22px;
        padding: 0 4px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        font-size: 12px;
        line-height: 1;
        cursor: pointer;
      }
      .copy:hover { border-color: var(--primary-color); }
      .copy:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
      .copy.ok { color: var(--success-color, #4caf50); }
      .copy.failed { color: var(--error-color, #f44336); }
    `;
  }
}

customElements.define("sberhome-copy-button", SberhomeCopyButton);
