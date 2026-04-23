/**
 * SberHome — replay / inject WS messages (DevTools #3).
 *
 * Two modes, one component:
 *
 *  1. Manual inject — textarea with a SocketMessageDto-shaped JSON
 *     template + button.  Power users paste whatever they want —
 *     backend routes by the top-level field (state / event /
 *     group_state / ...).
 *  2. Replay from log — subscribes to the WS message log, shows the
 *     last N inbound messages with a "Replay" button on each.  Click
 *     it and the coordinator feeds that exact payload back into its
 *     own dispatcher — no network round-trip, works offline.
 *
 * Synthetic traffic is tagged with ``direction="replay"`` in the
 * message log (see :meth:`SberHomeCoordinator.async_inject_ws_message`)
 * so replays don't feed themselves in a loop.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

const DEFAULT_PAYLOAD = JSON.stringify(
  {
    state: {
      device_id: "paste-device-id-here",
      reported_state: [
        { key: "on_off", type: "BOOL", bool_value: true },
      ],
    },
  },
  null,
  2,
);

class SberHomeReplayView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _messages: { type: Array },
      _payload: { type: String },
      _busy: { type: Boolean },
      _status: { type: String },
      _statusKind: { type: String },
    };
  }

  constructor() {
    super();
    this._messages = [];
    this._payload = DEFAULT_PAYLOAD;
    this._busy = false;
    this._status = "";
    this._statusKind = "";
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
            this._messages = event.snapshot;
          } else if (event.message) {
            this._messages = [...this._messages, event.message];
          }
        },
        { type: "sberhome/subscribe_messages" },
      );
    } catch (e) {
      this._setStatus(`Subscribe failed: ${e.message || e}`, "error");
    }
  }

  _unsubscribe() {
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  _setStatus(text, kind = "info") {
    this._status = text;
    this._statusKind = kind;
  }

  async _inject() {
    if (this._busy) return;
    this._busy = true;
    this._setStatus("Injecting...", "info");
    let payload;
    try {
      payload = JSON.parse(this._payload);
    } catch (e) {
      this._setStatus(`Invalid JSON: ${e.message || e}`, "error");
      this._busy = false;
      return;
    }
    try {
      const result = await this.hass.callWS({
        type: "sberhome/inject_ws_message",
        payload,
        mark_replay: true,
      });
      this._setStatus(
        result.handled
          ? `Injected → ${result.topic} (device=${result.device_id || "—"})`
          : "Unrecognised payload shape — no topic resolved.",
        result.handled ? "success" : "warning",
      );
    } catch (e) {
      this._setStatus(`Inject failed: ${e.message || e}`, "error");
    } finally {
      this._busy = false;
    }
  }

  async _replayOne(payload) {
    if (this._busy) return;
    this._busy = true;
    this._setStatus("Replaying...", "info");
    try {
      const result = await this.hass.callWS({
        type: "sberhome/replay_ws_message",
        payload,
      });
      this._setStatus(
        result.handled
          ? `Replayed → ${result.topic} (device=${result.device_id || "—"})`
          : "Unrecognised payload.",
        result.handled ? "success" : "warning",
      );
    } catch (e) {
      this._setStatus(`Replay failed: ${e.message || e}`, "error");
    } finally {
      this._busy = false;
    }
  }

  _formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString("ru-RU", { hour12: false });
  }

  _truncate(s, n = 80) {
    const text = typeof s === "string" ? s : JSON.stringify(s ?? "");
    return text.length > n ? text.slice(0, n) + "…" : text;
  }

  render() {
    // Only real inbound traffic is replayable — not our own outbound
    // commands, and not previous replays (they're tagged "replay",
    // not "in", so they don't appear in this list).
    const replayable = this._messages
      .filter((m) => m.direction === "in")
      .slice(-15)
      .reverse();

    return html`
      <div class="section">
        <div class="header"><h2>Replay &amp; Inject</h2></div>
        <div class="hint">
          Feed a synthetic WS message into the coordinator without touching the broker.  Works offline; state_cache, entities and state-diff all see it.
        </div>
        ${this._status ? html`<div class="status status-${this._statusKind}">${this._status}</div>` : ""}

        <div class="subsection">
          <h4>Manual inject</h4>
        <textarea class="json-editor"
          .value=${this._payload}
          spellcheck="false"
          @input=${(e) => { this._payload = e.target.value; }}
          placeholder="Paste a SocketMessageDto-shaped JSON..."></textarea>
        <div class="btn-bar">
          <button class="btn-primary"
            ?disabled=${this._busy || !this._payload.trim()}
            @click=${this._inject}>
            ${this._busy ? "Working..." : "Inject"}
          </button>
          <button class="btn-secondary"
            @click=${() => { this._payload = DEFAULT_PAYLOAD; }}>
            Reset template
          </button>
        </div>
      </div>

      <div class="subsection">
        <h4>Replay from log</h4>
        ${replayable.length === 0
          ? html`<div class="empty">No inbound WS messages yet.</div>`
          : html`
            <table class="replay-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Topic</th>
                  <th>Device</th>
                  <th>Payload preview</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${replayable.map((m) => html`
                  <tr>
                    <td class="t">${this._formatTime(m.ts)}</td>
                    <td class="topic">${m.topic}</td>
                    <td class="device">${m.device_id || "—"}</td>
                    <td class="preview" title="${JSON.stringify(m.payload)}">
                      ${this._truncate(m.payload)}
                    </td>
                    <td>
                      <button class="btn-secondary small"
                        ?disabled=${this._busy}
                        @click=${() => this._replayOne(m.payload)}>
                        Replay
                      </button>
                    </td>
                  </tr>`)}
              </tbody>
            </table>
          `}
        </div>
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
      .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
      h2 { margin: 0; font-size: 1.1em; font-weight: 500; color: var(--primary-text-color); }
      h4 { margin: 12px 0 6px; font-size: 0.9em; color: var(--primary-text-color); }
      .hint { color: var(--secondary-text-color); font-size: 0.8em; margin-bottom: 10px; }
      .status {
        padding: 6px 10px;
        border-radius: 4px;
        margin-bottom: 10px;
        font-size: 0.85em;
        font-family: monospace;
      }
      .status-info { background: var(--secondary-background-color); color: var(--primary-text-color); }
      .status-success { background: rgba(76, 175, 80, 0.12); color: var(--success-color, #4caf50); }
      .status-warning { background: rgba(255, 152, 0, 0.12); color: var(--warning-color, #ff9800); }
      .status-error { background: rgba(244, 67, 54, 0.12); color: var(--error-color, #f44336); }
      .subsection { border-top: 1px solid var(--divider-color); padding-top: 4px; }
      .json-editor {
        width: 100%;
        min-height: 140px;
        font-family: monospace;
        font-size: 0.85em;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        padding: 8px;
        box-sizing: border-box;
        resize: vertical;
      }
      .btn-bar { display: flex; gap: 8px; margin-top: 6px; }
      .btn-primary {
        background: var(--primary-color, #03a9f4);
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        cursor: pointer;
      }
      .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
      .btn-secondary {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        padding: 6px 12px;
        cursor: pointer;
      }
      .btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
      .btn-secondary.small { padding: 2px 8px; font-size: 0.8em; }
      .empty { color: var(--secondary-text-color); font-style: italic; padding: 12px; text-align: center; }
      .replay-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
      .replay-table th {
        text-align: left;
        padding: 6px 8px;
        border-bottom: 1px solid var(--divider-color);
        color: var(--secondary-text-color);
        font-weight: 500;
      }
      .replay-table td { padding: 4px 8px; vertical-align: middle; }
      .t { font-family: monospace; color: var(--secondary-text-color); width: 80px; }
      .topic { font-family: monospace; width: 130px; }
      .device { font-family: monospace; width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .preview { font-family: monospace; color: var(--primary-text-color); word-break: break-all; }
    `;
  }
}

customElements.define("sberhome-replay-view", SberHomeReplayView);
