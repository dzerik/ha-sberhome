/**
 * SberHome — Debug tab (Diagnostics + Raw command combined).
 *
 * Один селектор устройства сверху, внизу — подвкладки:
 *  - Payload: parsed DTO + raw JSON от Sber (copy buttons)
 *  - Send command: presets + JSON editor + отправка через
 *    sberhome.send_raw_command + показ response
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

const PRESETS = [
  {
    label: "Зелёный (s/v = 1000)",
    state: [{ key: "light_colour", type: "COLOR", color_value: { h: 120, s: 1000, v: 500 } }],
  },
  {
    label: "Красный (s/v = 1000)",
    state: [{ key: "light_colour", type: "COLOR", color_value: { h: 0, s: 1000, v: 500 } }],
  },
  {
    label: "Синий (s/v = 1000)",
    state: [{ key: "light_colour", type: "COLOR", color_value: { h: 240, s: 1000, v: 500 } }],
  },
  {
    label: "Цвет + light_mode=colour",
    state: [
      { key: "light_mode", type: "ENUM", enum_value: "colour" },
      { key: "light_colour", type: "COLOR", color_value: { h: 60, s: 1000, v: 500 } },
    ],
  },
  {
    label: "light_brightness=500",
    state: [{ key: "light_brightness", type: "INTEGER", integer_value: 500 }],
  },
  { label: "Power ON", state: [{ key: "on_off", type: "BOOL", bool_value: true }] },
  { label: "Power OFF", state: [{ key: "on_off", type: "BOOL", bool_value: false }] },
];

async function copyJson(obj) {
  const text = JSON.stringify(obj, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  }
}

class SberHomeDebugView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      devices: { type: Array },
      _selectedId: { type: String },
      _detail: { type: Object },
      _subtab: { type: String },
      _payload: { type: String },
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
    this._payload = JSON.stringify(PRESETS[0].state, null, 2);
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

  async _copy(label, payload) {
    await copyJson(payload);
    this._toast = `${label} скопирован`;
    setTimeout(() => (this._toast = ""), 2000);
  }

  _applyPreset(preset) {
    this._payload = JSON.stringify(preset.state, null, 2);
    this._response = null;
    this._error = "";
  }

  async _send() {
    if (!this._selectedId) {
      this._error = "Выбери устройство";
      return;
    }
    let state;
    try {
      state = JSON.parse(this._payload);
    } catch (err) {
      this._error = `Невалидный JSON: ${err.message}`;
      return;
    }
    if (!Array.isArray(state)) {
      this._error = "state должен быть массивом";
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
      this._toast =
        this._response?.ok === false
          ? `Ошибка: ${this._response.error || "?"}`
          : "Отправлено";
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._sending = false;
      setTimeout(() => (this._toast = ""), 3000);
    }
  }

  static get styles() {
    return css`
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
      .presets {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 12px;
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
    `;
  }

  _renderPayload() {
    if (!this._detail) {
      return html`<div class="empty">Выбери устройство выше, чтобы увидеть payload.</div>`;
    }
    const parsed = this._parsedView();
    const raw = this._detail?.raw_payload;
    return html`
      <div class="section">
        <div class="section-header">
          <h3>Распарсенный DTO</h3>
          <button @click=${() => this._copy("Parsed", parsed)}>Copy JSON</button>
        </div>
        <div class="hint">
          Обработанное представление (category, ha_entities, reported_state).
        </div>
        <pre>${JSON.stringify(parsed, null, 2)}</pre>
      </div>
      <div class="section">
        <div class="section-header">
          <h3>Raw payload от Sber Gateway</h3>
          <button @click=${() => this._copy("Raw", raw)} ?disabled=${raw == null}>
            Copy JSON
          </button>
        </div>
        <div class="hint">
          Как приходит в ответе /device_groups/tree. Приложи к багрепорту
          если видишь странное.
        </div>
        <pre>${raw != null
          ? JSON.stringify(raw, null, 2)
          : "(raw payload недоступен — coordinator ещё не делал polling)"}</pre>
      </div>
    `;
  }

  _renderSend() {
    if (!this._selectedId) {
      return html`<div class="empty">Выбери устройство выше, чтобы отправить команду.</div>`;
    }
    return html`
      <div class="hint">
        Дебаг-инструмент: отправляем произвольный <code>desired_state</code>
        в Sber API через <code>sberhome.send_raw_command</code>.
        Используй пресеты или правь JSON вручную.
      </div>
      <div class="presets">
        ${PRESETS.map(
          (p) => html`
            <button @click=${() => this._applyPreset(p)}>${p.label}</button>
          `
        )}
      </div>
      <textarea
        .value=${this._payload}
        @input=${(e) => (this._payload = e.target.value)}
        spellcheck="false"
      ></textarea>
      <button
        class="send-btn"
        @click=${this._send}
        ?disabled=${this._sending}
      >
        ${this._sending ? "Отправка…" : "Отправить"}
      </button>
      ${this._error ? html`<div class="error">${this._error}</div>` : ""}
      ${this._response
        ? html`
            <div class="section">
              <div class="section-header">
                <h3>Response</h3>
                <button @click=${() => this._copy("Response", this._response)}>
                  Copy JSON
                </button>
              </div>
              <pre>${JSON.stringify(this._response, null, 2)}</pre>
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
        <select class="device" @change=${this._onSelect}>
          <option value="" ?selected=${!this._selectedId}>— выберите устройство —</option>
          ${sorted.map(
            (d) => html`
              <option value=${d.device_id} ?selected=${d.device_id === this._selectedId}>
                ${d.name} · ${d.category || "?"}
              </option>
            `
          )}
        </select>
      </div>

      <nav>
        <div
          class="tab ${this._subtab === "payload" ? "active" : ""}"
          @click=${() => (this._subtab = "payload")}
        >
          Payload
        </div>
        <div
          class="tab ${this._subtab === "send" ? "active" : ""}"
          @click=${() => (this._subtab = "send")}
        >
          Send command
        </div>
      </nav>

      ${this._subtab === "payload" ? this._renderPayload() : this._renderSend()}
      ${this._toast ? html`<div class="toast">${this._toast}</div>` : ""}
    `;
  }
}

customElements.define("sberhome-debug-view", SberHomeDebugView);
