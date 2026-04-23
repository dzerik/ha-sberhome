/**
 * SberHome — Raw command tab.
 *
 * Debug-инструмент: отправить произвольный `desired_state` list прямо
 * в Sber API через service `sberhome.send_raw_command`. Полезно для
 * экспериментов с serialized format (какие ranges принимает лампа, нужен ли
 * light_mode, и т.д.).
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

// Sber serialized format: color_value использует короткие ключи {h, s, v}.
// Диапазон — per-device: для dt_bulb_e27_m (Beken cb2l) s/v идут в 0..1000,
// для большинства других ламп 0..100. Если не уверен — попробуй сначала
// ~половину диапазона (500 или 50).
const PRESETS = [
  {
    label: "Зелёный (s/v = 1000)",
    state: [
      { key: "light_colour", type: "COLOR", color_value: { h: 120, s: 1000, v: 500 } },
    ],
  },
  {
    label: "Красный (s/v = 1000)",
    state: [
      { key: "light_colour", type: "COLOR", color_value: { h: 0, s: 1000, v: 500 } },
    ],
  },
  {
    label: "Синий (s/v = 1000)",
    state: [
      { key: "light_colour", type: "COLOR", color_value: { h: 240, s: 1000, v: 500 } },
    ],
  },
  {
    label: "Цвет + light_mode=colour",
    state: [
      { key: "light_mode", type: "ENUM", enum_value: "colour" },
      { key: "light_colour", type: "COLOR", color_value: { h: 60, s: 1000, v: 500 } },
    ],
  },
  {
    label: "Brightness only (light_brightness=500)",
    state: [
      { key: "light_brightness", type: "INTEGER", integer_value: 500 },
    ],
  },
  {
    label: "Power ON",
    state: [{ key: "on_off", type: "BOOL", bool_value: true }],
  },
  {
    label: "Power OFF",
    state: [{ key: "on_off", type: "BOOL", bool_value: false }],
  },
];

class SberHomeRawCommand extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      devices: { type: Array },
      _selectedId: { type: String },
      _payload: { type: String },
      _response: { type: Object },
      _sending: { type: Boolean },
      _toast: { type: String },
      _error: { type: String },
    };
  }

  constructor() {
    super();
    this.devices = [];
    this._selectedId = "";
    this._payload = JSON.stringify(PRESETS[0].state, null, 2);
    this._response = null;
    this._sending = false;
    this._toast = "";
    this._error = "";
  }

  _onSelectDevice(e) {
    this._selectedId = e.target.value;
    this._response = null;
    this._error = "";
  }

  _onPayloadChange(e) {
    this._payload = e.target.value;
    this._error = "";
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
      this._error = "State должен быть массивом (list of AttributeValueDto)";
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
      if (this._response?.ok === false) {
        this._toast = `Ошибка: ${this._response.error || "?"}`;
      } else {
        this._toast = "Отправлено";
      }
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._sending = false;
      setTimeout(() => {
        this._toast = "";
      }, 3000);
    }
  }

  async _copyResponse() {
    if (!this._response) return;
    const text = JSON.stringify(this._response, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      this._toast = "Response скопирован";
      setTimeout(() => {
        this._toast = "";
      }, 2000);
    } catch {
      /* ignore */
    }
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      .hint {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 16px;
        line-height: 1.5;
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
      select { min-width: 320px; margin-bottom: 16px; }
      textarea {
        width: 100%;
        min-height: 220px;
        resize: vertical;
        white-space: pre;
      }
      .presets {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 12px;
      }
      .preset-btn, .send-btn, .copy-btn {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        color: var(--primary-text-color);
        cursor: pointer;
        font-size: 12px;
      }
      .preset-btn:hover, .copy-btn:hover {
        background: var(--secondary-background-color);
      }
      .send-btn {
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        border-color: var(--primary-color);
        padding: 10px 24px;
        font-size: 14px;
        font-weight: 600;
        margin-top: 12px;
      }
      .send-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .section {
        margin-top: 20px;
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
      }
      pre {
        background: var(--code-editor-background-color, #1e1e1e);
        color: var(--code-editor-text-color, #d4d4d4);
        padding: 12px;
        border-radius: 6px;
        max-height: 400px;
        overflow: auto;
        font-size: 12px;
        white-space: pre-wrap;
        margin: 0;
      }
      .error {
        background: var(--error-color);
        color: #fff;
        padding: 10px 14px;
        border-radius: 6px;
        margin-top: 12px;
        font-size: 13px;
      }
      .ok {
        background: var(--success-color, #2e7d32);
        color: #fff;
        padding: 10px 14px;
        border-radius: 6px;
        margin-top: 12px;
        font-size: 13px;
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
    `;
  }

  render() {
    return html`
      <div class="hint">
        Отправка произвольного <code>desired_state</code> в Sber API через
        <code>sberhome.send_raw_command</code>. Debug-инструмент: выбери
        пресет или правь JSON вручную, чтобы экспериментально определить
        корректный serialized format (диапазоны saturation / brightness,
        нужен ли <code>light_mode</code>, порядок ключей и т.д.).
      </div>

      <select @change=${this._onSelectDevice}>
        <option value="">— выберите устройство —</option>
        ${this.devices.map(
          (d) => html`
            <option value=${d.device_id}>
              ${d.name} (${d.category || "?"})
            </option>
          `
        )}
      </select>

      <div class="presets">
        ${PRESETS.map(
          (p) => html`
            <button class="preset-btn" @click=${() => this._applyPreset(p)}>
              ${p.label}
            </button>
          `
        )}
      </div>

      <textarea
        .value=${this._payload}
        @input=${this._onPayloadChange}
        spellcheck="false"
      ></textarea>

      <button
        class="send-btn"
        @click=${this._send}
        ?disabled=${this._sending || !this._selectedId}
      >
        ${this._sending ? "Отправка…" : "Отправить"}
      </button>

      ${this._error ? html`<div class="error">${this._error}</div>` : ""}

      ${this._response
        ? html`
            <div class="section">
              <div class="section-header">
                <h3>Response</h3>
                <button class="copy-btn" @click=${this._copyResponse}>
                  Copy JSON
                </button>
              </div>
              <pre>${JSON.stringify(this._response, null, 2)}</pre>
            </div>
          `
        : ""}

      ${this._toast ? html`<div class="toast">${this._toast}</div>` : ""}
    `;
  }
}

customElements.define("sberhome-raw-command", SberHomeRawCommand);
