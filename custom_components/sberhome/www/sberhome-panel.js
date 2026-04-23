/**
 * SberHome — main SPA panel.
 *
 * Tabs: Devices | Monitor (status + log) | Debug (payload + raw command) | Settings.
 */

const _v = new URL(import.meta.url).searchParams.get("v") || "";
const _q = _v ? `?v=${_v}` : "";
await Promise.all([
  import(`./components/sberhome-toast.js${_q}`),
  import(`./components/sberhome-status-card.js${_q}`),
  import(`./components/sberhome-device-picker.js${_q}`),
  import(`./components/sberhome-log-view.js${_q}`),
  import(`./components/sberhome-state-diff-view.js${_q}`),
  import(`./components/sberhome-diagnose-view.js${_q}`),
  import(`./components/sberhome-replay-view.js${_q}`),
  import(`./components/sberhome-commands-view.js${_q}`),
  import(`./components/sberhome-validation-view.js${_q}`),
  import(`./components/sberhome-monitor-view.js${_q}`),
  import(`./components/sberhome-debug-view.js${_q}`),
  import(`./components/sberhome-device-modal.js${_q}`),
  import(`./components/sberhome-settings.js${_q}`),
]);

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

class SberHomePanel extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      panel: { type: Object },
      _tab: { type: Number },
      _devices: { type: Array },
      _status: { type: Object },
      _loading: { type: Boolean },
      _error: { type: String },
      _modalDeviceId: { type: String },
    };
  }

  constructor() {
    super();
    this._tab = 0;
    this._devices = [];
    this._status = null;
    this._loading = false;
    this._error = "";
    this._autoRefresh = null;
    this._modalDeviceId = "";
  }

  connectedCallback() {
    super.connectedCallback();
    this._autoRefresh = setInterval(() => this._fetchAll(), 15000);
    this._fetchAll();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._autoRefresh) {
      clearInterval(this._autoRefresh);
      this._autoRefresh = null;
    }
  }

  updated(changed) {
    if (changed.has("hass") && this.hass && !this._devices.length) {
      this._fetchAll();
    }
  }

  async _fetchAll() {
    if (!this.hass) return;
    this._loading = true;
    try {
      const [devicesResp, status] = await Promise.all([
        this.hass.callWS({ type: "sberhome/get_devices" }),
        this.hass.callWS({ type: "sberhome/get_status" }),
      ]);
      this._devices = devicesResp.devices || [];
      this._status = status;
      this._error = "";
    } catch (e) {
      this._error = e.message || String(e);
    } finally {
      this._loading = false;
    }
  }

  _onTabClick(idx) {
    this._tab = idx;
  }

  _onDeviceToggled() {
    setTimeout(() => this._fetchAll(), 500);
  }

  _onToast(e) {
    const toast = this.shadowRoot.querySelector("sberhome-toast");
    if (toast) toast.show(e.detail.message, e.detail.type);
  }

  _onShowDeviceDetail(e) {
    this._modalDeviceId = e.detail.deviceId;
  }

  _onCloseModal() {
    this._modalDeviceId = "";
  }

  async _forceRefresh() {
    if (!this.hass || this._loading) return;
    this._loading = true;
    this.requestUpdate();
    try {
      await this.hass.callWS({ type: "sberhome/force_refresh" });
      await this._fetchAll();
      const toast = this.shadowRoot.querySelector("sberhome-toast");
      if (toast) toast.show("Обновлено", "success");
    } catch (e) {
      const toast = this.shadowRoot.querySelector("sberhome-toast");
      if (toast) toast.show(`Ошибка: ${e.message || e}`, "error");
    } finally {
      this._loading = false;
    }
  }

  static get styles() {
    return css`
      :host {
        display: block;
        height: 100%;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
      }
      .header {
        display: flex;
        align-items: center;
        background: var(--app-header-background-color, var(--primary-color));
        color: var(--app-header-text-color, #fff);
        padding: 0 16px;
        height: var(--header-height, 56px);
        box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.1));
      }
      .header h1 { margin: 0; font-size: 20px; flex: 1; }
      .refresh-btn {
        background: rgba(255, 255, 255, 0.15);
        color: inherit;
        border: 1px solid rgba(255, 255, 255, 0.3);
        padding: 6px 14px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
      }
      .refresh-btn:hover:not([disabled]) {
        background: rgba(255, 255, 255, 0.25);
      }
      .refresh-btn[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .tabs {
        display: flex;
        background: var(--app-header-background-color, var(--primary-color));
        color: var(--app-header-text-color, #fff);
        padding: 0 16px;
        overflow-x: auto;
      }
      .tab {
        padding: 12px 20px;
        cursor: pointer;
        border-bottom: 3px solid transparent;
        font-size: 14px;
        text-transform: uppercase;
        white-space: nowrap;
        opacity: 0.7;
      }
      .tab.active { border-color: #fff; opacity: 1; }
      .content { padding: 16px; }
      @media (max-width: 600px) {
        .content { padding: 8px; }
      }
      .error {
        padding: 16px; margin: 16px;
        background: var(--error-color); color: #fff; border-radius: 8px;
      }
    `;
  }

  render() {
    const tabs = ["Devices", "Monitor", "Debug", "Settings"];
    return html`
      <div class="header">
        <h1>SberHome</h1>
        <button
          class="refresh-btn"
          @click=${this._forceRefresh}
          ?disabled=${this._loading}
          title="Принудительно обновить state из Sber Gateway"
        >
          ${this._loading ? "⟳" : "↻"} Обновить
        </button>
      </div>
      <div class="tabs">
        ${tabs.map(
          (label, idx) => html`
            <div class="tab ${this._tab === idx ? "active" : ""}"
              @click=${() => this._onTabClick(idx)}>
              ${label}
            </div>
          `
        )}
      </div>
      ${this._error ? html`<div class="error">${this._error}</div>` : ""}
      <div class="content"
        @toast=${this._onToast}
        @show-device-detail=${this._onShowDeviceDetail}
        @device-toggled=${this._onDeviceToggled}>
        ${this._tab === 0 ? html`
          <sberhome-device-picker .hass=${this.hass}
            .devices=${this._devices}>
          </sberhome-device-picker>` : ""}
        ${this._tab === 1 ? html`
          <sberhome-monitor-view .hass=${this.hass} .status=${this._status}>
          </sberhome-monitor-view>` : ""}
        ${this._tab === 2 ? html`
          <sberhome-debug-view .hass=${this.hass} .devices=${this._devices}>
          </sberhome-debug-view>` : ""}
        ${this._tab === 3 ? html`
          <sberhome-settings .hass=${this.hass}></sberhome-settings>` : ""}
      </div>
      <sberhome-toast></sberhome-toast>
      ${this._modalDeviceId
        ? html`<sberhome-device-modal
            .hass=${this.hass}
            .deviceId=${this._modalDeviceId}
            @close-modal=${this._onCloseModal}
          ></sberhome-device-modal>`
        : ""}
    `;
  }
}

customElements.define("sberhome-panel", SberHomePanel);
