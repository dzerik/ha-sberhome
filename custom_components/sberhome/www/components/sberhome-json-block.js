/**
 * SberHome — collapsible JSON block with "copy all".
 *
 * Перенесено из Sber MQTT Bridge (issue #44 там). Длинный JSON в блоке с
 * `max-height` и прокруткой на телефоне выглядит оборванным: мобильные
 * браузеры рисуют полосу прокрутки только во время прокрутки, и объект
 * кажется незакрытым. Здесь свёрнутый вид действительно содержит только
 * первые COLLAPSED_LINES строк, об остальных сказано явно, а «Копировать»
 * всегда копирует весь JSON — для баг-репорта с телефона.
 */

import { LitElement, html, css } from "../lit-base.js";
import { Localized } from "../i18n/index.js";

/** Строк в свёрнутом виде. */
export const COLLAPSED_LINES = 14;

/** Сколько миллисекунд показывать результат копирования. */
const COPY_FEEDBACK_MS = 2500;

/**
 * Скопировать текст: Clipboard API, а без него (HTTP без TLS в локальной
 * сети) — через временный textarea.
 *
 * @param {string} text
 * @returns {Promise<boolean>} Удалось ли.
 */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the textarea path */
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}

export class SberhomeJsonBlock extends Localized(LitElement) {
  static get properties() {
    return {
      hass: { type: Object },
      /** Объект (форматируется здесь) или готовая строка. */
      value: { attribute: false },
      /** Доступное имя блока. */
      label: { type: String },
      _expanded: { state: true },
      _copyState: { state: true },
    };
  }

  constructor() {
    super();
    this.value = null;
    this.label = "JSON";
    this._expanded = false;
    this._copyState = "";
    this._copyTimer = null;
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this._copyTimer);
  }

  /** Весь JSON текстом. */
  get text() {
    const value = this.value;
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  /** Число строк во всём JSON. */
  get lineCount() {
    const text = this.text;
    return text ? text.split("\n").length : 0;
  }

  /** Текст, который сейчас рисуется: срез в свёрнутом виде, иначе всё. */
  visibleText() {
    const text = this.text;
    if (this._expanded || this.lineCount <= COLLAPSED_LINES) return text;
    return `${text.split("\n").slice(0, COLLAPSED_LINES).join("\n")}\n…`;
  }

  async _copy() {
    const ok = await copyText(this.text);
    this._copyState = this.t(ok ? "json.copied" : "json.copy_failed");
    clearTimeout(this._copyTimer);
    this._copyTimer = setTimeout(() => {
      this._copyState = "";
    }, COPY_FEEDBACK_MS);
  }

  render() {
    const total = this.lineCount;
    const truncatable = total > COLLAPSED_LINES;
    const hidden = truncatable && !this._expanded ? total - COLLAPSED_LINES : 0;
    return html`
      <div class="toolbar">
        <button class="btn" @click=${this._copy} ?disabled=${total === 0}>${this.t("json.copy")}</button>
        ${truncatable
          ? html`<button class="btn" aria-expanded=${this._expanded ? "true" : "false"} aria-controls="code"
              @click=${() => { this._expanded = !this._expanded; }}>
              ${this._expanded ? this.t("json.collapse") : this.t("json.show_all", { n: total })}
            </button>`
          : ""}
        <span class="status" role="status">${this._copyState}</span>
      </div>
      <pre id="code" aria-label=${this.label}>${this.visibleText()}</pre>
      ${hidden ? html`<div class="hidden-note">${this.t("json.lines_hidden", { n: hidden })}</div>` : ""}
    `;
  }

  static get styles() {
    return css`
      :host { display: block; }
      .toolbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 4px; }
      .btn {
        padding: 3px 10px;
        border-radius: 4px;
        border: 1px solid var(--divider-color);
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        font-size: 12px;
        cursor: pointer;
      }
      .btn:disabled { opacity: 0.5; cursor: default; }
      .btn:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
      .status { font-size: 12px; color: var(--secondary-text-color); }
      pre {
        margin: 0;
        padding: 8px 10px;
        border-radius: 6px;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        font-size: 12px;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }
      .hidden-note { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
    `;
  }
}

customElements.define("sberhome-json-block", SberhomeJsonBlock);
