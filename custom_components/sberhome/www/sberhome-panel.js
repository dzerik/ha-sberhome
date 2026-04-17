/**
 * SberHome — main SPA panel.
 *
 * Tabs: Rooms | Devices | Status | Log | Diagnostics | Settings.
 */

const _v = new URL(import.meta.url).searchParams.get("v") || "";
const _q = _v ? `?v=${_v}` : "";
await Promise.all([
  import(`./components/sberhome-toast.js${_q}`),
  import(`./components/sberhome-status-card.js${_q}`),
  import(`./components/sberhome-device-picker.js${_q}`),
  import(`./components/sberhome-rooms-view.js${_q}`),
  import(`./components/sberhome-log-view.js${_q}`),
  import(`./components/sberhome-diagnostics.js${_q}`),
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
      _rooms: { type: Array },
      _home: { type: Object },
      _status: { type: Object },
      _loading: { type: Boolean },
      _error: { type: String },
      _roomFilter: { type: String },
    };
  }

  constructor() {
    super();
    this._tab = 0;
    this._devices = [];
    this._rooms = [];
    this._home = null;
    this._status = null;
    this._loading = false;
    this._error = "";
    this._roomFilter = null;
    this._autoRefresh = null;
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
      const [devicesResp, status, roomsResp] = await Promise.all([
        this.hass.callWS({ type: "sberhome/get_devices" }),
        this.hass.callWS({ type: "sberhome/get_status" }),
        this.hass.callWS({ type: "sberhome/get_rooms" }),
      ]);
      this._devices = devicesResp.devices || [];
      this._status = status;
      this._rooms = roomsResp.rooms || [];
      this._home = roomsResp.home || null;
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

  _onRoomSelected(e) {
    this._roomFilter = e.detail.roomId;
    if (this._roomFilter) {
      this._tab = 1; // Switch to Devices tab with room filter
    }
  }

  _onToast(e) {
    const toast = this.shadowRoot.querySelector("sberhome-toast");
    if (toast) toast.show(e.detail.message, e.detail.type);
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
      .content { padding: 0; }
      .error {
        padding: 16px; margin: 16px;
        background: var(--error-color); color: #fff; border-radius: 8px;
      }
    `;
  }

  render() {
    const tabs = ["Rooms", "Devices", "Status", "Log", "Diagnostics", "Settings"];
    return html`
      <div class="header"><h1>SberHome</h1></div>
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
      <div class="content" @toast=${this._onToast} @room-selected=${this._onRoomSelected}>
        ${this._tab === 0 ? html`
          <sberhome-rooms-view .hass=${this.hass}
            .rooms=${this._rooms} .home=${this._home}
            .totalDevices=${this._devices.length}>
          </sberhome-rooms-view>` : ""}
        ${this._tab === 1 ? html`
          <sberhome-device-picker .hass=${this.hass}
            .devices=${this._devices} .roomFilter=${this._roomFilter}
            @device-toggled=${this._onDeviceToggled}>
          </sberhome-device-picker>` : ""}
        ${this._tab === 2 ? html`
          <sberhome-status-card .status=${this._status}></sberhome-status-card>` : ""}
        ${this._tab === 3 ? html`
          <sberhome-log-view .hass=${this.hass}></sberhome-log-view>` : ""}
        ${this._tab === 4 ? html`
          <sberhome-diagnostics .hass=${this.hass} .devices=${this._devices}>
          </sberhome-diagnostics>` : ""}
        ${this._tab === 5 ? html`
          <sberhome-settings .hass=${this.hass}></sberhome-settings>` : ""}
      </div>
      <sberhome-toast></sberhome-toast>
    `;
  }
}

customElements.define("sberhome-panel", SberHomePanel);
