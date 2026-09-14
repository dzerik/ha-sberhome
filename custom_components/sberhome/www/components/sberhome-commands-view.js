/**
 * SberHome — outbound command confirmation tracker (DevTools #4).
 *
 * Subscribes to ``sberhome/subscribe_commands`` and renders one row
 * per outbound PUT /state with a live verdict:
 *
 *     pending          — just sent, waiting for reported_state to echo back
 *     confirmed        — every key landed; command worked
 *     partial          — some keys landed, some timed out
 *     silent_rejection — HTTP 200 but nothing changed on the device
 *
 * Sber protocol has no correlation id, so the backend matches each
 * command to subsequent reported_state snapshots on key + value.
 * Wall-clock `last_sync` is ignored — otherwise every match would fail.
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";
import { Localized } from "../i18n/index.js";
import "./sberhome-copy-button.js";

/**
 * Короткое значение атрибута Sber: ``true``, ``500``, ``h=120 s=80 v=100``.
 * Полный JSON остаётся в подсказке ячейки.
 */
export function formatValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v !== "object") return String(v);
  for (const field of ["bool_value", "integer_value", "float_value", "enum_value", "string_value"]) {
    if (field in v) return String(v[field]);
  }
  const colour = v.color_value || v.colour_value;
  if (colour && typeof colour === "object") return `h=${colour.h} s=${colour.s} v=${colour.v}`;
  return JSON.stringify(v);
}

/** Статусы трекера; у каждого есть перевод ``commands.status.*``. */
const STATUSES = ["pending", "confirmed", "partial", "silent_rejection", "send_failed"];

class SberHomeCommandsView extends Localized(LitElement) {
  static get properties() {
    return {
      hass: { type: Object },
      _commands: { type: Array },
      _error: { type: String },
      _statusFilter: { type: String },
    };
  }

  constructor() {
    super();
    this._commands = [];
    this._error = "";
    this._statusFilter = "all";
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
            this._commands = event.snapshot;
          } else if (event.command) {
            this._applyLiveUpdate(event.kind, event.command);
          }
        },
        { type: "sberhome/subscribe_commands" },
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

  _applyLiveUpdate(_kind, cmd) {
    const idx = this._commands.findIndex((c) => c.command_id === cmd.command_id);
    if (idx === -1) {
      this._commands = [...this._commands, cmd];
    } else {
      const next = [...this._commands];
      next[idx] = cmd;
      this._commands = next;
    }
  }

  async _clear() {
    try {
      await this.hass.callWS({ type: "sberhome/clear_commands" });
      this._commands = [];
      this._error = "";
    } catch (e) {
      this._error = e.message || String(e);
    }
  }

  _formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString(this.hass?.language, { hour12: false });
  }

  /** Время отклика облака (PUT) и ошибка отправки — первая строка шкалы. */
  _renderTimeline(c) {
    const parts = [];
    if (c.http_ms !== null && c.http_ms !== undefined) parts.push(this.t("commands.http_ms", { ms: c.http_ms }));
    if (c.context_id) parts.push(this.t("commands.context", { id: c.context_id.slice(-6) }));
    return html`
      ${parts.length ? html`<div class="timeline">${parts.join(" · ")}</div>` : ""}
      ${c.error ? html`<div class="send-error">${c.error}</div>` : ""}
    `;
  }

  /** «через 850 мс · WebSocket» — когда и каким каналом пришло подтверждение ключа. */
  _confirmedText(c, key) {
    const at = (c.confirmed_at || {})[key];
    if (at === undefined) return "";
    const via = (c.confirmed_via || {})[key];
    const ms = Math.max(0, Math.round((at - c.sent_at) * 1000));
    const channel = this.t(`commands.via.${via === "polling" ? "polling" : "ws_push"}`);
    if (ms < 1000) return this.t("commands.confirmed_after", { ms, via: channel });
    const seconds = (ms / 1000).toLocaleString(this.hass?.language, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return this.t("commands.confirmed_after_s", { s: seconds, via: channel });
  }

  _pendingCount(cmd) {
    const sent = Object.keys(cmd.keys_sent || {}).length;
    const confirmed = Object.keys(cmd.keys_confirmed || {}).length;
    return sent - confirmed;
  }

  render() {
    const filtered = this._statusFilter === "all"
      ? this._commands
      : this._commands.filter((c) => c.status === this._statusFilter);
    const rows = [...filtered].reverse();
    const counts = this._countByStatus();

    return html`
      <div class="section">
        <div class="header">
          <h2>${this.t("commands.title")}</h2>
          <div class="toolbar">
            <label class="filter">
              <select .value=${this._statusFilter}
                aria-label=${this.t("commands.status_label")}
                @change=${(e) => { this._statusFilter = e.target.value; }}>
                <option value="all">${this.t("commands.filter_all")}</option>
                ${STATUSES.map((st) => html`
                  <option value=${st}>${this.t(`commands.status.${st}`)}</option>`)}
              </select>
            </label>
            <button class="btn-danger"
              ?disabled=${this._commands.length === 0}
              @click=${this._clear}>
              ${this.t("commands.clear")}
            </button>
          </div>
        </div>
        <div class="hint">${this.t("commands.silent_rejection_hint")}</div>
        <div class="chips">
          <span class="chip chip-pending">${this.t("commands.chip_pending", { n: counts.pending })}</span>
          <span class="chip chip-confirmed">${this.t("commands.chip_confirmed", { n: counts.confirmed })}</span>
          <span class="chip chip-partial">${this.t("commands.chip_partial", { n: counts.partial })}</span>
          <span class="chip chip-silent_rejection">${this.t("commands.chip_silent_rejection", { n: counts.silent_rejection })}</span>
          <span class="chip chip-send_failed">${this.t("commands.chip_send_failed", { n: counts.send_failed })}</span>
        </div>
        ${this._error ? html`<div class="error">${this._error}</div>` : ""}
        <div class="rows">
          ${rows.length === 0
            ? html`<div class="empty">${this.t("commands.empty")}</div>`
            : html`${rows.map((c) => this._renderRow(c))}`}
        </div>
      </div>
    `;
  }

  _countByStatus() {
    const out = { pending: 0, confirmed: 0, partial: 0, silent_rejection: 0, send_failed: 0 };
    for (const c of this._commands) {
      if (c.status in out) out[c.status]++;
    }
    return out;
  }

  _renderRow(c) {
    const pending = this._pendingCount(c);
    const keysSent = Object.keys(c.keys_sent || {}).sort();
    return html`
      <div class="cmd cmd-${c.status}">
        <div class="cmd-head">
          <span class="badge badge-${c.status}">${STATUSES.includes(c.status) ? this.t(`commands.status.${c.status}`) : c.status}</span>
          <span class="device" title="${c.device_id}">${c.device_id}</span>
          <span class="keys">${keysSent.join(", ") || "—"}</span>
          ${pending > 0 && c.status === "pending"
            ? html`<span class="pending-count">${this.t("commands.waiting", { n: pending })}</span>`
            : ""}
          <span class="time">${this._formatTime(c.sent_at)}</span>
        </div>
        ${this._renderTimeline(c)}
        ${keysSent.length > 0 ? html`
          <table class="keys-table">
            <tbody>
              ${keysSent.map((k) => html`
                <tr class="key-row ${k in (c.keys_confirmed || {}) ? "confirmed" : "missing"}">
                  <td class="mark">${k in (c.keys_confirmed || {}) ? "✓" : "…"}</td>
                  <td class="k">${k}</td>
                  <td class="v" title=${JSON.stringify(c.keys_sent[k])}><sberhome-copy-button .hass=${this.hass} .value=${c.keys_sent[k]}></sberhome-copy-button>${formatValue(c.keys_sent[k])}</td>
                  <td class="when">${this._confirmedText(c, k)}</td>
                </tr>`)}
            </tbody>
          </table>
        ` : ""}
      </div>
    `;
  }

  static get styles() {
    return [css`
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
      h2 { margin: 0; font-size: 1.1em; font-weight: 500; color: var(--primary-text-color); }
      .toolbar { display: flex; gap: 8px; align-items: center; }
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
      .btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
      .hint { color: var(--secondary-text-color); font-size: 0.8em; margin-bottom: 10px; }
      .chips { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
      .chip {
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75em;
        font-weight: 600;
      }
      .chip-pending { background: rgba(3, 169, 244, 0.15); color: var(--primary-color, #03a9f4); }
      .chip-confirmed { background: rgba(76, 175, 80, 0.15); color: var(--success-color, #4caf50); }
      .chip-partial { background: rgba(255, 152, 0, 0.15); color: var(--warning-color, #ff9800); }
      .chip-silent_rejection { background: rgba(244, 67, 54, 0.15); color: var(--error-color, #f44336); }
      .chip-send_failed { background: rgba(244, 67, 54, 0.25); color: var(--error-color, #f44336); }
      .cmd-send_failed { border-left: 3px dashed var(--error-color, #f44336); }
      .timeline { color: var(--secondary-text-color); font-size: 0.8em; margin-top: 4px; }
      .send-error { color: var(--error-color, #f44336); font-family: monospace; font-size: 0.8em; margin-top: 4px; overflow-wrap: anywhere; }
      .when { color: var(--secondary-text-color); font-size: 0.85em; }
      .error { color: var(--error-color, #f44336); margin-bottom: 8px; font-size: 0.9em; }
      .empty { color: var(--secondary-text-color); font-style: italic; padding: 16px; text-align: center; }
      .rows { display: flex; flex-direction: column; gap: 4px; }
      .cmd {
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        padding: 8px 10px;
        background: var(--primary-background-color);
      }
      .cmd-pending { border-left: 3px solid var(--primary-color, #03a9f4); }
      .cmd-confirmed { border-left: 3px solid var(--success-color, #4caf50); }
      .cmd-partial { border-left: 3px solid var(--warning-color, #ff9800); }
      .cmd-silent_rejection { border-left: 3px solid var(--error-color, #f44336); }
      .cmd-head {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.85em;
        margin-bottom: 4px;
      }
      .badge {
        padding: 1px 8px;
        border-radius: 10px;
        font-size: 0.7em;
        font-weight: 600;
        text-transform: uppercase;
      }
      .badge-pending { background: rgba(3, 169, 244, 0.15); color: var(--primary-color, #03a9f4); }
      .badge-confirmed { background: rgba(76, 175, 80, 0.15); color: var(--success-color, #4caf50); }
      .badge-partial { background: rgba(255, 152, 0, 0.15); color: var(--warning-color, #ff9800); }
      .badge-silent_rejection { background: rgba(244, 67, 54, 0.15); color: var(--error-color, #f44336); }
      .badge-send_failed { background: rgba(244, 67, 54, 0.25); color: var(--error-color, #f44336); }
      .device { font-family: monospace; font-weight: 600; color: var(--primary-text-color); }
      .keys { font-family: monospace; color: var(--secondary-text-color); font-size: 0.85em; }
      .pending-count { color: var(--primary-color, #03a9f4); font-size: 0.75em; }
      .time {
        margin-left: auto;
        color: var(--secondary-text-color);
        font-family: monospace;
        font-size: 0.75em;
      }
      .keys-table {
        width: 100%;
        border-collapse: collapse;
        font-family: monospace;
        font-size: 0.85em;
      }
      .keys-table td { padding: 2px 6px; vertical-align: top; }
      .mark { width: 20px; text-align: center; font-weight: 700; }
      .key-row.confirmed .mark { color: var(--success-color, #4caf50); }
      .key-row.missing .mark { color: var(--secondary-text-color); }
      .k { width: 40%; color: var(--primary-text-color); overflow-wrap: anywhere; }
      .v { color: var(--secondary-text-color); overflow-wrap: anywhere; min-width: 6.5em; }
    `, mobileBase];
  }
}

customElements.define("sberhome-commands-view", SberHomeCommandsView);
