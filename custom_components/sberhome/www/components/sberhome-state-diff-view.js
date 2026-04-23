/**
 * SberHome — per-device state-diff view (DevTools #1).
 *
 * Subscribes to ``sberhome/subscribe_state_diffs`` and renders each
 * delta as a compact row — Sber's ``reported_state`` re-sends every
 * attribute on every update, so a raw log buries the real change in
 * noise.  This view surfaces just the delta:
 *
 *     dev-abc-123  (ws_push · DEVICE_STATE)
 *       ~ temperature: 200 → 225
 *       ~ humidity:    45 → 46
 *       + light_colour: hsv(0, 100, 100)
 *       − on_off
 *
 * Identical-to-prior snapshots never reach the UI — dropped by the
 * backend collector.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

class SberHomeStateDiffView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _diffs: { type: Array },
      _error: { type: String },
      _sourceFilter: { type: String },
    };
  }

  constructor() {
    super();
    this._diffs = [];
    this._error = "";
    this._sourceFilter = "all";
    this._hassReady = false;
    this._unsub = null;
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubscribe();
  }

  updated(changedProps) {
    if (changedProps.has("hass") && this.hass && !this._hassReady) {
      this._hassReady = true;
      this._subscribe();
    }
  }

  async _subscribe() {
    if (this._unsub) return;
    try {
      this._unsub = await this.hass.connection.subscribeMessage(
        (event) => {
          if (event.snapshot) {
            this._diffs = event.snapshot;
          } else if (event.diff) {
            this._diffs = [...this._diffs, event.diff];
          }
        },
        { type: "sberhome/subscribe_state_diffs" },
      );
    } catch (e) {
      this._error = e.message || String(e);
    }
  }

  _unsubscribe() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  async _clear() {
    try {
      await this.hass.callWS({ type: "sberhome/clear_state_diffs" });
      this._diffs = [];
      this._error = "";
    } catch (e) {
      this._error = e.message || String(e);
    }
  }

  _formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString("ru-RU", { hour12: false }) +
      "." + String(d.getMilliseconds()).padStart(3, "0");
  }

  /** Extract a short human-friendly representation of a Sber value dict. */
  _formatValue(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v !== "object") return String(v);
    const type = v.type;
    if (type === "BOOL" && "bool_value" in v) return String(v.bool_value);
    if (type === "INTEGER" && "integer_value" in v) return String(v.integer_value);
    if (type === "FLOAT" && "float_value" in v) return String(v.float_value);
    if (type === "STRING" && "string_value" in v) return JSON.stringify(v.string_value);
    if (type === "ENUM" && "enum_value" in v) return String(v.enum_value);
    if (type === "COLOR" && "color_value" in v) {
      const c = v.color_value;
      if (c && typeof c === "object") {
        const h = c.h ?? c.hue;
        const s = c.s ?? c.saturation;
        const val = c.v ?? c.brightness;
        return `hsv(${h}, ${s}, ${val})`;
      }
    }
    return JSON.stringify(v);
  }

  render() {
    const filtered = this._sourceFilter === "all"
      ? this._diffs
      : this._diffs.filter((d) => d.source === this._sourceFilter);
    const rows = [...filtered].reverse(); // newest first

    return html`
      <div class="section">
        <div class="header">
          <h2>State Diffs</h2>
          <div class="toolbar">
            <label class="filter">
              <select .value=${this._sourceFilter}
                @change=${(e) => { this._sourceFilter = e.target.value; }}>
                <option value="all">all sources</option>
                <option value="ws_push">ws_push</option>
                <option value="polling">polling</option>
                <option value="inject">inject</option>
              </select>
            </label>
            <button class="btn-danger"
              ?disabled=${this._diffs.length === 0}
              @click=${this._clear}>
              Clear
            </button>
          </div>
        </div>
        <div class="hint">
          Дельта между двумя последовательными reported_state snapshot'ами для устройства. Идентичные snapshot'ы не записываются.
        </div>
        ${this._error ? html`<div class="error">${this._error}</div>` : ""}
        <div class="rows">
          ${rows.length === 0
            ? html`<div class="empty">Пока ни одно устройство не меняло state после подписки.</div>`
            : html`${rows.map((d) => this._renderDiff(d))}`}
        </div>
      </div>
    `;
  }

  _renderDiff(d) {
    const changedKeys = Object.keys(d.changed || {}).sort();
    const addedKeys = Object.keys(d.added || {}).sort();
    const removedKeys = Object.keys(d.removed || {}).sort();
    return html`
      <div class="diff ${d.is_initial ? "initial" : ""}">
        <div class="diff-head">
          <span class="device" title="${d.device_id}">${d.device_id}</span>
          <span class="source source-${d.source}">${d.source}</span>
          ${d.topic ? html`<span class="topic">${d.topic}</span>` : ""}
          ${d.is_initial ? html`<span class="initial-badge">initial</span>` : ""}
          <span class="time">${this._formatTime(d.ts)}</span>
        </div>
        <table class="delta">
          <tbody>
            ${changedKeys.map((k) => html`
              <tr class="row-changed">
                <td class="op">~</td>
                <td class="key">${k}</td>
                <td class="from">${this._formatValue(d.changed[k].before)}</td>
                <td class="arrow">→</td>
                <td class="to">${this._formatValue(d.changed[k].after)}</td>
              </tr>`)}
            ${addedKeys.map((k) => html`
              <tr class="row-added">
                <td class="op">+</td>
                <td class="key">${k}</td>
                <td class="from"></td>
                <td class="arrow"></td>
                <td class="to">${this._formatValue(d.added[k])}</td>
              </tr>`)}
            ${removedKeys.map((k) => html`
              <tr class="row-removed">
                <td class="op">−</td>
                <td class="key">${k}</td>
                <td class="from">${this._formatValue(d.removed[k])}</td>
                <td class="arrow"></td>
                <td class="to"></td>
              </tr>`)}
          </tbody>
        </table>
      </div>
    `;
  }

  static get styles() {
    return css`
      :host { display: block; }
      .section {
        background: var(--card-background-color, #fff);
        border-radius: var(--ha-card-border-radius, 12px);
        box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0, 0, 0, 0.1));
        padding: 16px;
        margin-bottom: 16px;
      }
      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 6px;
      }
      h2 {
        margin: 0;
        font-size: 1.1em;
        font-weight: 500;
        color: var(--primary-text-color);
      }
      .toolbar {
        display: flex;
        gap: 8px;
        align-items: center;
      }
      select {
        padding: 4px 8px;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        font-size: 0.85em;
      }
      .btn-danger {
        background: var(--error-color, #f44336);
        color: white;
        border: none;
        border-radius: 4px;
        padding: 4px 12px;
        cursor: pointer;
        font-size: 0.85em;
      }
      .btn-danger:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .hint {
        color: var(--secondary-text-color);
        font-size: 0.8em;
        margin-bottom: 8px;
      }
      .error {
        color: var(--error-color, #f44336);
        margin-bottom: 8px;
        font-size: 0.9em;
      }
      .empty {
        color: var(--secondary-text-color);
        font-style: italic;
        padding: 16px;
        text-align: center;
      }
      .rows {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .diff {
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        padding: 8px 10px;
        background: var(--primary-background-color);
      }
      .diff.initial {
        border-left: 3px solid var(--secondary-text-color);
      }
      .diff-head {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.85em;
        margin-bottom: 4px;
      }
      .device {
        font-family: monospace;
        font-weight: 600;
        color: var(--primary-text-color);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 260px;
      }
      .source {
        padding: 1px 8px;
        border-radius: 10px;
        font-size: 0.7em;
        font-weight: 600;
        text-transform: uppercase;
      }
      .source-ws_push {
        background: rgba(3, 169, 244, 0.15);
        color: var(--primary-color, #03a9f4);
      }
      .source-polling {
        background: rgba(255, 152, 0, 0.15);
        color: var(--warning-color, #ff9800);
      }
      .source-inject {
        background: rgba(156, 39, 176, 0.15);
        color: #9c27b0;
      }
      .topic {
        font-family: monospace;
        color: var(--secondary-text-color);
        font-size: 0.75em;
      }
      .initial-badge {
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
        padding: 1px 8px;
        border-radius: 10px;
        font-size: 0.7em;
        text-transform: uppercase;
        font-weight: 600;
      }
      .time {
        margin-left: auto;
        color: var(--secondary-text-color);
        font-family: monospace;
        font-size: 0.75em;
      }
      .delta {
        width: 100%;
        /* fixed layout — без этого колонки каждой таблицы подстраиваются
         * под свои данные, и когда в одном блоке есть only added (from/arrow
         * пустые), а в другом — changed+removed (from/arrow заполнены),
         * value-колонка прыгает по горизонтали между блоками. */
        table-layout: fixed;
        border-collapse: collapse;
        font-family: monospace;
        font-size: 0.85em;
      }
      .delta td {
        padding: 2px 6px;
        vertical-align: top;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .op {
        width: 22px;
        font-weight: 700;
        text-align: center;
      }
      .key {
        width: 240px;
        color: var(--primary-text-color);
        white-space: nowrap;
      }
      .from {
        width: 160px;
        color: var(--secondary-text-color);
        word-break: break-all;
      }
      .arrow {
        width: 24px;
        text-align: center;
        color: var(--secondary-text-color);
      }
      .to {
        /* remaining space — auto-computed */
        color: var(--primary-text-color);
        word-break: break-all;
      }
      .row-changed .op { color: var(--warning-color, #ff9800); }
      .row-added .op { color: var(--success-color, #4caf50); }
      .row-removed .op { color: var(--error-color, #f44336); }
      .row-removed .from { text-decoration: line-through; }
    `;
  }
}

customElements.define("sberhome-state-diff-view", SberHomeStateDiffView);
