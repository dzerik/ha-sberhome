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

const STATUS_LABEL = {
  pending: "Pending",
  confirmed: "Confirmed",
  partial: "Partial",
  silent_rejection: "Silent rejection",
};

class SberHomeCommandsView extends LitElement {
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
    return d.toLocaleTimeString("ru-RU", { hour12: false });
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
          <h2>Command Confirmation</h2>
          <div class="toolbar">
            <label class="filter">
              <select .value=${this._statusFilter}
                @change=${(e) => { this._statusFilter = e.target.value; }}>
                <option value="all">all</option>
                <option value="pending">pending</option>
                <option value="confirmed">confirmed</option>
                <option value="partial">partial</option>
                <option value="silent_rejection">silent_rejection</option>
              </select>
            </label>
            <button class="btn-danger"
              ?disabled=${this._commands.length === 0}
              @click=${this._clear}>
              Clear
            </button>
          </div>
        </div>
        <div class="hint">
          Sber проходит HTTP 200 и без применения команды.  Этот трекер ждёт подтверждения в reported_state — если не пришло в 10 секунд, помечает <strong>silent_rejection</strong>.
        </div>
        <div class="chips">
          <span class="chip chip-pending">${counts.pending} pending</span>
          <span class="chip chip-confirmed">${counts.confirmed} confirmed</span>
          <span class="chip chip-partial">${counts.partial} partial</span>
          <span class="chip chip-silent_rejection">${counts.silent_rejection} silent</span>
        </div>
        ${this._error ? html`<div class="error">${this._error}</div>` : ""}
        <div class="rows">
          ${rows.length === 0
            ? html`<div class="empty">No outbound commands yet — send a command from HA.</div>`
            : html`${rows.map((c) => this._renderRow(c))}`}
        </div>
      </div>
    `;
  }

  _countByStatus() {
    const out = { pending: 0, confirmed: 0, partial: 0, silent_rejection: 0 };
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
          <span class="badge badge-${c.status}">${STATUS_LABEL[c.status] || c.status}</span>
          <span class="device" title="${c.device_id}">${c.device_id}</span>
          <span class="keys">${keysSent.join(", ") || "—"}</span>
          ${pending > 0 && c.status === "pending"
            ? html`<span class="pending-count">${pending} waiting</span>`
            : ""}
          <span class="time">${this._formatTime(c.sent_at)}</span>
        </div>
        ${keysSent.length > 0 ? html`
          <table class="keys-table">
            <tbody>
              ${keysSent.map((k) => html`
                <tr class="key-row ${k in (c.keys_confirmed || {}) ? "confirmed" : "missing"}">
                  <td class="mark">${k in (c.keys_confirmed || {}) ? "✓" : "…"}</td>
                  <td class="k">${k}</td>
                  <td class="v">${JSON.stringify(c.keys_sent[k])}</td>
                </tr>`)}
            </tbody>
          </table>
        ` : ""}
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
      .k { width: 200px; color: var(--primary-text-color); }
      .v { color: var(--secondary-text-color); word-break: break-all; }
    `;
  }
}

customElements.define("sberhome-commands-view", SberHomeCommandsView);
