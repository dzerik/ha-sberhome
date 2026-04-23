/**
 * SberHome — per-device "Why isn't it working?" diagnose view (DevTools #2).
 *
 * Compact form:
 *   * device_id input (paste from Devices tab) + Diagnose button,
 *   * verdict badge (ok / warning / broken),
 *   * list of findings with severity + title + detail + action,
 *   * collapsible raw summary for power users.
 *
 * Designed to be pastable into a bug report — one click produces a
 * self-contained readout of everything the integration knows about
 * one device.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

const VERDICT_LABEL = {
  ok: "Clean",
  warning: "Warnings",
  broken: "Broken",
};

class SberHomeDiagnoseView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _deviceId: { type: String },
      _report: { type: Object },
      _loading: { type: Boolean },
      _error: { type: String },
      _rawOpen: { type: Boolean },
    };
  }

  constructor() {
    super();
    this._deviceId = "";
    this._report = null;
    this._loading = false;
    this._error = "";
    this._rawOpen = false;
  }

  async _run() {
    if (this._loading) return;
    this._error = "";
    if (!this._deviceId.trim()) {
      this._error = "Enter a device_id to diagnose.";
      return;
    }
    this._loading = true;
    try {
      const result = await this.hass.callWS({
        type: "sberhome/diagnose_device",
        device_id: this._deviceId.trim(),
      });
      this._report = result.report;
    } catch (e) {
      this._error = e.message || String(e);
    } finally {
      this._loading = false;
    }
  }

  async _copyReport() {
    if (!this._report) return;
    const text = JSON.stringify(this._report, null, 2);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  }

  render() {
    return html`
      <div class="section">
        <div class="header">
          <h2>Why isn't it working?</h2>
        </div>
        <div class="hint">
          Runs every diagnostic rule the integration knows against one device — in tree / enabled / HA-mapped / online / fresh / WS / token / errors — and returns a verdict with actionable next steps.
        </div>
        <div class="form-row">
          <input
            type="text"
            placeholder="device_id (paste from Devices tab)"
            .value=${this._deviceId}
            @input=${(e) => { this._deviceId = e.target.value; }}
            @keydown=${(e) => { if (e.key === "Enter") this._run(); }}
          />
          <button class="btn-primary"
            ?disabled=${this._loading}
            @click=${this._run}>
            ${this._loading ? "Running..." : "Diagnose"}
          </button>
          ${this._report ? html`
            <button class="btn-secondary" @click=${this._copyReport}>Copy report</button>
          ` : ""}
        </div>
        ${this._error ? html`<div class="error">${this._error}</div>` : ""}
        ${this._report ? this._renderReport(this._report) : ""}
      </div>
    `;
  }

  _renderReport(r) {
    const verdict = r.verdict;
    return html`
      <div class="verdict verdict-${verdict}">
        <span class="badge badge-${verdict}">${VERDICT_LABEL[verdict] || verdict}</span>
        <span class="device">${r.device_id}</span>
      </div>
      <div class="findings">
        ${(r.findings || []).map((f) => html`
          <div class="finding finding-${f.severity}">
            <div class="finding-head">
              <span class="sev-dot sev-${f.severity}"></span>
              <span class="finding-title">${f.title}</span>
              <span class="finding-code">${f.code}</span>
            </div>
            <div class="finding-detail">${f.detail}</div>
            ${f.action ? html`<div class="finding-action"><strong>Action:</strong> ${f.action}</div>` : ""}
          </div>`)}
      </div>
      <div class="raw-toggle" @click=${() => { this._rawOpen = !this._rawOpen; }}>
        <span class="caret ${this._rawOpen ? "open" : ""}">&#9654;</span>
        Raw summary
      </div>
      ${this._rawOpen ? html`<pre class="raw">${JSON.stringify(r.summary, null, 2)}</pre>` : ""}
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
        margin-bottom: 4px;
      }
      h2 { margin: 0; font-size: 1.1em; font-weight: 500; color: var(--primary-text-color); }
      .hint {
        color: var(--secondary-text-color);
        font-size: 0.8em;
        margin-bottom: 10px;
      }
      .form-row {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-bottom: 12px;
      }
      input {
        flex: 1;
        padding: 6px 10px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        font-family: monospace;
      }
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
      .error { color: var(--error-color, #f44336); margin-bottom: 8px; font-size: 0.9em; }
      .verdict {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 12px;
      }
      .verdict-ok { background: rgba(76, 175, 80, 0.08); }
      .verdict-warning { background: rgba(255, 152, 0, 0.08); }
      .verdict-broken { background: rgba(244, 67, 54, 0.08); }
      .badge {
        padding: 3px 12px;
        border-radius: 14px;
        font-size: 0.8em;
        font-weight: 700;
        text-transform: uppercase;
      }
      .badge-ok { background: rgba(76, 175, 80, 0.2); color: var(--success-color, #4caf50); }
      .badge-warning { background: rgba(255, 152, 0, 0.2); color: var(--warning-color, #ff9800); }
      .badge-broken { background: rgba(244, 67, 54, 0.2); color: var(--error-color, #f44336); }
      .device { font-family: monospace; color: var(--primary-text-color); }
      .findings { display: flex; flex-direction: column; gap: 8px; }
      .finding {
        border: 1px solid var(--divider-color);
        border-left-width: 3px;
        border-radius: 4px;
        padding: 10px 12px;
        background: var(--primary-background-color);
      }
      .finding-error { border-left-color: var(--error-color, #f44336); }
      .finding-warning { border-left-color: var(--warning-color, #ff9800); }
      .finding-info { border-left-color: var(--primary-color, #03a9f4); }
      .finding-ok { border-left-color: var(--success-color, #4caf50); }
      .finding-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
      .sev-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
      }
      .sev-error { background: var(--error-color, #f44336); }
      .sev-warning { background: var(--warning-color, #ff9800); }
      .sev-info { background: var(--primary-color, #03a9f4); }
      .sev-ok { background: var(--success-color, #4caf50); }
      .finding-title { font-weight: 600; color: var(--primary-text-color); flex: 1; }
      .finding-code { font-family: monospace; font-size: 0.75em; color: var(--secondary-text-color); }
      .finding-detail { color: var(--primary-text-color); font-size: 0.9em; line-height: 1.4; }
      .finding-action {
        margin-top: 6px;
        padding: 4px 8px;
        background: var(--secondary-background-color);
        border-radius: 3px;
        font-size: 0.85em;
      }
      .raw-toggle {
        margin-top: 14px;
        color: var(--secondary-text-color);
        cursor: pointer;
        font-size: 0.85em;
        user-select: none;
      }
      .caret { display: inline-block; transition: transform 0.15s; margin-right: 4px; }
      .caret.open { transform: rotate(90deg); }
      .raw {
        background: var(--secondary-background-color);
        padding: 10px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.8em;
        overflow: auto;
        max-height: 300px;
      }
    `;
  }
}

customElements.define("sberhome-diagnose-view", SberHomeDiagnoseView);
