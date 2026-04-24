/**
 * SberHome — Diagnostics tab.
 *
 * Выбираем устройство, показываем:
 * - Распарсенный DTO (name, category, reported_state, ha_entities) — удобно читать.
 * - Raw payload от Sber Gateway — как есть, для приложения к багрепортам.
 * Каждая секция с кнопкой "Copy JSON" (через Clipboard API).
 */

import { LitElement, html, css } from "../lit-base.js";

async function copyJson(obj) {
  const text = JSON.stringify(obj, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback для браузеров без Clipboard API (редко в 2026, но на всякий).
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  }
}

class SberHomeDiagnostics extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      devices: { type: Array },
      _selectedId: { type: String },
      _detail: { type: Object },
      _toast: { type: String },
    };
  }

  constructor() {
    super();
    this.devices = [];
    this._selectedId = "";
    this._detail = null;
    this._toast = "";
  }

  async _onSelect(e) {
    this._selectedId = e.target.value;
    if (!this._selectedId) {
      this._detail = null;
      return;
    }
    this._detail = await this.hass.callWS({
      type: "sberhome/device_detail",
      device_id: this._selectedId,
    });
  }

  async _copy(label, payload) {
    await copyJson(payload);
    this._toast = `${label} скопирован`;
    setTimeout(() => {
      this._toast = "";
    }, 2000);
  }

  _parsedView() {
    // Всё кроме raw_payload — удобный view для чтения.
    if (!this._detail) return null;
    const { raw_payload, ...parsed } = this._detail;
    return parsed;
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      select {
        padding: 8px 12px;
        border-radius: 6px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        min-width: 320px;
        margin-bottom: 16px;
      }
      .section {
        margin-top: 16px;
      }
      .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }
      .section-header h3 {
        margin: 0;
        font-size: 14px;
        font-weight: 600;
        color: var(--primary-text-color);
      }
      button {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        cursor: pointer;
        color: var(--primary-text-color);
        font-size: 12px;
      }
      button:hover {
        background: var(--secondary-background-color);
      }
      pre {
        background: var(--code-editor-background-color, #1e1e1e);
        color: var(--code-editor-text-color, #d4d4d4);
        padding: 12px;
        border-radius: 6px;
        max-height: 500px;
        overflow: auto;
        font-size: 12px;
        white-space: pre-wrap;
        margin: 0;
      }
      .toast {
        position: fixed;
        top: 24px;
        right: 24px;
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        padding: 10px 16px;
        border-radius: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,.2);
        z-index: 10;
        font-size: 13px;
      }
      .hint {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
    `;
  }

  render() {
    const parsed = this._parsedView();
    const raw = this._detail?.raw_payload;
    return html`
      <select @change=${this._onSelect}>
        <option value="">— выберите устройство —</option>
        ${this.devices.map(
          (d) =>
            html`<option value=${d.device_id}>
              ${d.name} (${d.category || "?"})
            </option>`
        )}
      </select>

      ${this._detail
        ? html`
            <div class="section">
              <div class="section-header">
                <h3>Распарсенный DTO</h3>
                <button @click=${() => this._copy("Parsed JSON", parsed)}>
                  Copy JSON
                </button>
              </div>
              <div class="hint">Обработанное представление (category, ha_entities, reported_state).</div>
              <pre>${JSON.stringify(parsed, null, 2)}</pre>
            </div>

            <div class="section">
              <div class="section-header">
                <h3>Raw payload от Sber Gateway</h3>
                <button
                  @click=${() => this._copy("Raw JSON", raw)}
                  ?disabled=${raw == null}
                >
                  Copy JSON
                </button>
              </div>
              <div class="hint">
                Как приходит в ответе /device_groups/tree, до нашей пост-обработки.
                Приложите к багрепорту при нестандартном поведении.
              </div>
              <pre>${raw != null
                ? JSON.stringify(raw, null, 2)
                : "(raw payload недоступен — coordinator ещё не делал polling)"}</pre>
            </div>
          `
        : ""}

      ${this._toast ? html`<div class="toast">${this._toast}</div>` : ""}
    `;
  }
}

customElements.define("sberhome-diagnostics", SberHomeDiagnostics);
