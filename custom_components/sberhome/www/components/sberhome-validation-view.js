/**
 * SberHome — inbound schema validation view (DevTools #5).
 *
 * Early-warning system for Sber REST/WS API drift: flags unknown
 * attribute keys, unknown value types, and malformed type/value pairs
 * in every incoming reported_state snapshot.
 *
 * Two tabs:
 *   "By device" — latest per-device status.  Best for "which devices
 *                 are currently emitting weird payloads".
 *   "Timeline"  — chronological feed, newest first.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

class SberHomeValidationView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _byDevice: { type: Object },
      _recent: { type: Array },
      _tab: { type: String },
      _error: { type: String },
    };
  }

  constructor() {
    super();
    this._byDevice = {};
    this._recent = [];
    this._tab = "by_device";
    this._error = "";
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
            this._byDevice = event.snapshot.by_device || {};
            this._recent = event.snapshot.recent || [];
          } else if (event.issues) {
            const updated = { ...this._byDevice };
            for (const issue of event.issues) {
              updated[issue.device_id] = (updated[issue.device_id] || []).filter(() => false);
            }
            for (const issue of event.issues) {
              (updated[issue.device_id] ||= []).push(issue);
            }
            this._byDevice = updated;
            this._recent = [...this._recent, ...event.issues];
          }
        },
        { type: "sberhome/subscribe_validation_issues" },
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
      await this.hass.callWS({ type: "sberhome/clear_validation_issues" });
      this._byDevice = {};
      this._recent = [];
      this._error = "";
    } catch (e) {
      this._error = e.message || String(e);
    }
  }

  _formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString("ru-RU", { hour12: false });
  }

  _counts() {
    let warnings = 0;
    let infos = 0;
    for (const list of Object.values(this._byDevice)) {
      for (const i of list) {
        if (i.severity === "warning") warnings++;
        else if (i.severity === "info") infos++;
      }
    }
    return { warnings, infos };
  }

  render() {
    const { warnings, infos } = this._counts();
    return html`
      <div class="section">
        <div class="header">
          <h2>Schema Validation</h2>
          <div class="toolbar">
            <button class="btn-danger"
              ?disabled=${this._recent.length === 0}
              @click=${this._clear}>
              Clear
            </button>
          </div>
        </div>
        <div class="summary">
          <span class="chip chip-warning">${warnings} warnings</span>
          <span class="chip chip-info">${infos} info</span>
          <span class="hint">Unknown keys / malformed type/value pairs in every reported_state — early warning for API drift.</span>
        </div>
        ${this._error ? html`<div class="error">${this._error}</div>` : ""}
        <div class="tabs">
          <button class="tab ${this._tab === "by_device" ? "active" : ""}"
            @click=${() => { this._tab = "by_device"; }}>
            By device
          </button>
          <button class="tab ${this._tab === "timeline" ? "active" : ""}"
            @click=${() => { this._tab = "timeline"; }}>
            Timeline
          </button>
        </div>
        ${this._tab === "by_device" ? this._renderByDevice() : this._renderTimeline()}
      </div>
    `;
  }

  _renderByDevice() {
    const entries = Object.keys(this._byDevice).sort();
    if (entries.length === 0) {
      return html`<div class="empty">No validation events yet.</div>`;
    }
    return html`
      <table class="issue-table">
        <thead>
          <tr>
            <th>Device</th>
            <th></th>
            <th>Type</th>
            <th>Key</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          ${entries.flatMap((did) => {
            const issues = this._byDevice[did] || [];
            if (issues.length === 0) {
              return [html`
                <tr class="clean">
                  <td class="device">${did}</td>
                  <td><span class="badge badge-clean">clean</span></td>
                  <td colspan="3">No issues in latest snapshot</td>
                </tr>`];
            }
            return issues.map((i, idx) => html`
              <tr class="sev-${i.severity}">
                <td class="device">${idx === 0 ? did : ""}</td>
                <td><span class="badge badge-${i.severity}">${i.severity}</span></td>
                <td class="type">${i.type}</td>
                <td class="key">${i.key || "—"}</td>
                <td class="desc">${i.description}</td>
              </tr>`);
          })}
        </tbody>
      </table>
    `;
  }

  _renderTimeline() {
    const rows = [...this._recent].reverse();
    if (rows.length === 0) {
      return html`<div class="empty">No issues yet.</div>`;
    }
    return html`
      <table class="issue-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Device</th>
            <th></th>
            <th>Type</th>
            <th>Key</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((i) => html`
            <tr class="sev-${i.severity}">
              <td class="t">${this._formatTime(i.ts)}</td>
              <td class="device">${i.device_id}</td>
              <td><span class="badge badge-${i.severity}">${i.severity}</span></td>
              <td class="type">${i.type}</td>
              <td class="key">${i.key || "—"}</td>
              <td class="desc">${i.description}</td>
            </tr>`)}
        </tbody>
      </table>
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
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }
      h2 { margin: 0; font-size: 1.1em; font-weight: 500; color: var(--primary-text-color); }
      .summary { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
      .chip {
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75em;
        font-weight: 600;
      }
      .chip-warning { background: rgba(255, 152, 0, 0.15); color: var(--warning-color, #ff9800); }
      .chip-info { background: rgba(3, 169, 244, 0.15); color: var(--primary-color, #03a9f4); }
      .hint {
        color: var(--secondary-text-color);
        font-size: 0.8em;
        margin-left: 8px;
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
      .error { color: var(--error-color, #f44336); margin-bottom: 8px; font-size: 0.9em; }
      .empty { color: var(--secondary-text-color); font-style: italic; padding: 12px; text-align: center; }
      .tabs { display: flex; gap: 0; border-bottom: 1px solid var(--divider-color); margin-bottom: 8px; }
      .tab {
        background: none;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 6px 14px;
        color: var(--secondary-text-color);
        font-size: 0.85em;
        cursor: pointer;
      }
      .tab.active { color: var(--primary-text-color); border-bottom-color: var(--primary-color, #03a9f4); }
      .issue-table { width: 100%; border-collapse: collapse; font-size: 0.8em; }
      .issue-table th {
        text-align: left;
        padding: 6px 8px;
        border-bottom: 1px solid var(--divider-color);
        color: var(--secondary-text-color);
        font-weight: 500;
      }
      .issue-table td { padding: 4px 8px; vertical-align: top; }
      .t { font-family: monospace; color: var(--secondary-text-color); width: 80px; }
      .device { font-family: monospace; font-weight: 500; color: var(--primary-text-color); }
      .type { font-family: monospace; color: var(--secondary-text-color); }
      .key { font-family: monospace; color: var(--primary-text-color); }
      .desc { color: var(--primary-text-color); }
      .clean .device, .clean td { color: var(--secondary-text-color); }
      .badge {
        display: inline-block;
        padding: 1px 8px;
        border-radius: 10px;
        font-size: 0.7em;
        font-weight: 600;
        text-transform: uppercase;
      }
      .badge-warning { background: rgba(255, 152, 0, 0.15); color: var(--warning-color, #ff9800); }
      .badge-info { background: rgba(3, 169, 244, 0.15); color: var(--primary-color, #03a9f4); }
      .badge-clean { background: rgba(76, 175, 80, 0.15); color: var(--success-color, #4caf50); }
      .sev-warning .desc { color: var(--warning-color, #ff9800); }
    `;
  }
}

customElements.define("sberhome-validation-view", SberHomeValidationView);
