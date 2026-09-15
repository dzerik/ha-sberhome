/**
 * SberHome — Debug tab (Diagnostics + Raw command combined).
 *
 * Один селектор устройства сверху, внизу — подвкладки:
 *  - Payload: parsed DTO + raw JSON от Sber (sberhome-json-block)
 *  - Send command: presets + JSON editor + отправка через
 *    sberhome.send_raw_command + показ response
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";
import { Localized, backendErrorMessage } from "../i18n/index.js";
import "./sberhome-json-block.js";

// Форма по возможностям устройства (device_write_schema) — та же, что в
// редакторе сценариев. Генерирует desired_state из виджетов.
const _v = new URL(import.meta.url).searchParams.get("v") || "";
await import(`./sberhome-attr-form.js${_v ? `?v=${_v}` : ""}`);

/** Подвкладки: id → ключ перевода подписи. */
const SUBTABS = [
  ["payload", "debug.tab_payload"],
  ["send", "debug.tab_send"],
];

class SberHomeDebugView extends Localized(LitElement) {
  static get properties() {
    return {
      hass: { type: Object },
      devices: { type: Array },
      _selectedId: { type: String },
      _detail: { type: Object },
      _subtab: { type: String },
      _payload: { type: String },
      _formAttrs: { state: true },
      _response: { type: Object },
      _sending: { type: Boolean },
      _error: { type: String },
      _toast: { type: String },
    };
  }

  constructor() {
    super();
    this.devices = [];
    this._selectedId = "";
    this._detail = null;
    this._subtab = "payload";
    this._payload = "[]";
    this._formAttrs = [];
    this._response = null;
    this._sending = false;
    this._error = "";
    this._toast = "";
  }

  async _onSelect(e) {
    this._selectedId = e.target.value;
    this._detail = null;
    this._response = null;
    this._error = "";
    this._formAttrs = [];
    if (!this._selectedId) return;
    try {
      this._detail = await this.hass.callWS({
        type: "sberhome/device_detail",
        device_id: this._selectedId,
      });
    } catch (err) {
      this._error = err.message || String(err);
    }
  }

  _parsedView() {
    if (!this._detail) return null;
    const { raw_payload, ...parsed } = this._detail;
    return parsed;
  }

  // Форма по возможностям устройства → генерируем desired_state JSON.
  // attr-form отдаёт голый список [{key,type,value}] — ровно формат
  // sberhome.send_raw_command, обёртка не нужна.
  _onFormAttrs(e) {
    this._formAttrs = e.detail.attributes || [];
    this._payload = JSON.stringify(this._formAttrs, null, 2);
  }

  async _send() {
    if (!this._selectedId) {
      this._error = this.t("debug.err_select_device");
      return;
    }
    let state;
    try {
      state = JSON.parse(this._payload);
    } catch (err) {
      this._error = this.t("debug.err_invalid_json", { msg: err.message });
      return;
    }
    if (!Array.isArray(state)) {
      this._error = this.t("debug.err_state_array");
      return;
    }
    this._sending = true;
    this._error = "";
    this._response = null;
    try {
      const resp = await this.hass.callService(
        "sberhome",
        "send_raw_command",
        { device_id: this._selectedId, state },
        undefined,
        false,
        true,
      );
      this._response = resp?.response ?? resp ?? { ok: true };
      this._toast = this.t("common.sent");
    } catch (err) {
      // Сервис при ошибке поднимает исключение с ключом перевода: сервер
      // кладёт в message английский текст, перевод берём у Home Assistant.
      this._error = await backendErrorMessage(this.hass, err);
    } finally {
      this._sending = false;
      setTimeout(() => (this._toast = ""), 3000);
    }
  }

  static get styles() {
    return [css`
      :host { display: block; padding: 16px; }
      .top-selector {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
      }
      select, textarea {
        font-family: var(--code-font-family, ui-monospace, SFMono-Regular, monospace);
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 13px;
        box-sizing: border-box;
      }
      select.device {
        flex: 1;
        min-width: 280px;
      }
      textarea {
        width: 100%;
        min-height: 180px;
        resize: vertical;
        white-space: pre;
      }
      nav {
        display: flex;
        border-bottom: 1px solid var(--divider-color);
        margin-bottom: 16px;
      }
      nav .tab {
        padding: 10px 16px;
        cursor: pointer;
        border-bottom: 3px solid transparent;
        font-size: 13px;
        text-transform: uppercase;
        font-weight: 500;
        opacity: 0.7;
      }
      nav .tab.active {
        border-color: var(--primary-color);
        opacity: 1;
      }
      nav .tab:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
      }
      .section { margin-top: 12px; }
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
      }
      button {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        color: var(--primary-text-color);
        cursor: pointer;
        font-size: 12px;
      }
      button:hover:not([disabled]) {
        background: var(--secondary-background-color);
      }
      button.send-btn {
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        border-color: var(--primary-color);
        padding: 10px 24px;
        font-size: 14px;
        font-weight: 600;
        margin-top: 12px;
      }
      button[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .hint {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 8px;
      }
      .error {
        background: var(--error-color);
        color: #fff;
        padding: 10px 14px;
        border-radius: 6px;
        margin-top: 12px;
        font-size: 13px;
      }
      .empty {
        padding: 48px;
        text-align: center;
        color: var(--secondary-text-color);
      }
      .toast {
        position: fixed;
        top: 24px;
        right: 24px;
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        padding: 10px 16px;
        border-radius: 6px;
        z-index: 20;
        font-size: 13px;
      }
    `, mobileBase];
  }

  _renderPayload() {
    if (!this._detail) {
      return html`<div class="empty">${this.t("debug.empty_payload")}</div>`;
    }
    const parsed = this._parsedView();
    const raw = this._detail?.raw_payload;
    return html`
      <div class="section">
        <div class="section-header">
          <h3>${this.t("debug.section_parsed_dto")}</h3>
        </div>
        <div class="hint">${this.t("debug.parsed_hint")}</div>
        <sberhome-json-block .hass=${this.hass} .value=${parsed}
          label=${this.t("debug.section_parsed_dto")}></sberhome-json-block>
      </div>
      <div class="section">
        <div class="section-header">
          <h3>${this.t("debug.section_raw_payload")}</h3>
        </div>
        <div class="hint">${this.t("debug.raw_hint")}</div>
        ${raw != null
          ? html`<sberhome-json-block .hass=${this.hass} .value=${raw}
              label=${this.t("debug.section_raw_payload")}></sberhome-json-block>`
          : html`<div class="hint">${this.t("debug.raw_unavailable")}</div>`}
      </div>
    `;
  }

  _renderSend() {
    if (!this._selectedId) {
      return html`<div class="empty">${this.t("debug.empty_command")}</div>`;
    }
    return html`
      <div class="hint">${this.t("debug.send_hint")}</div>
      <div class="section-header" style="margin-top:4px;">
        <h3>${this.t("debug.section_form")}</h3>
      </div>
      <sberhome-attr-form
        .hass=${this.hass}
        .deviceId=${this._selectedId}
        .value=${this._formAttrs}
        @attributes-change=${this._onFormAttrs}
      ></sberhome-attr-form>
      <textarea
        .value=${this._payload}
        @input=${(e) => (this._payload = e.target.value)}
        aria-label=${this.t("debug.payload_editor_label")}
        spellcheck="false"
      ></textarea>
      <button
        class="send-btn"
        @click=${this._send}
        ?disabled=${this._sending}
      >
        ${this._sending ? this.t("common.sending") : this.t("common.send")}
      </button>
      ${this._error ? html`<div class="error">${this._error}</div>` : ""}
      ${this._response
        ? html`
            <div class="section">
              <div class="section-header">
                <h3>${this.t("debug.section_response")}</h3>
              </div>
              <sberhome-json-block .hass=${this.hass} .value=${this._response}
                label=${this.t("debug.section_response")}></sberhome-json-block>
            </div>
          `
        : ""}
    `;
  }

  render() {
    const sorted = [...(this.devices || [])].sort((a, b) =>
      (a.name || "").localeCompare(b.name || "")
    );
    return html`
      <div class="top-selector">
        <select class="device" aria-label=${this.t("debug.device_label")} @change=${this._onSelect}>
          <option value="" ?selected=${!this._selectedId}>${this.t("common.device_select_option")}</option>
          ${sorted.map(
            (d) => html`
              <option value=${d.device_id} ?selected=${d.device_id === this._selectedId}>
                ${d.name} · ${d.category || "?"}
              </option>
            `
          )}
        </select>
      </div>

      <nav role="tablist" aria-label=${this.t("debug.tabs_label")}>
        ${SUBTABS.map(([id, key]) => html`
          <div
            class="tab ${this._subtab === id ? "active" : ""}"
            role="tab"
            tabindex="0"
            aria-selected=${this._subtab === id ? "true" : "false"}
            @click=${() => (this._subtab = id)}
            @keydown=${(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                this._subtab = id;
              }
            }}
          >
            ${this.t(key)}
          </div>
        `)}
      </nav>

      ${this._subtab === "payload" ? this._renderPayload() : this._renderSend()}
      ${this._toast ? html`<div class="toast">${this._toast}</div>` : ""}
    `;
  }
}

customElements.define("sberhome-debug-view", SberHomeDebugView);
