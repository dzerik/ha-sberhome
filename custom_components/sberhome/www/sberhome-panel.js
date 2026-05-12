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
  import(`./components/sberhome-intents-view.js${_q}`),
  import(`./components/sberhome-intent-modal.js${_q}`),
  import(`./components/sberhome-home-switcher.js${_q}`),
]);

import { LitElement, html, css } from "./lit-base.js";

// Inline (вместо импорта из switcher) — иначе модуль загрузится дважды:
// один раз через dynamic import с `?v=` querystring, второй раз через
// статический import без querystring, и ESM посчитает их разными
// модулями → `customElements.define` упадёт с "name already used".
const HOME_SWITCHER_STORAGE_KEY = "sberhome.selected_home_id";

class SberHomePanel extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      panel: { type: Object },
      _tab: { type: Number },
      _devices: { type: Array },
      _status: { type: Object },
      _homes: { type: Array },
      _selectedHomeId: { type: String },
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
    this._homes = [];
    this._selectedHomeId = this._loadSelectedHomeId();
    this._loading = false;
    this._error = "";
    this._autoRefresh = null;
    this._modalDeviceId = "";
  }

  _loadSelectedHomeId() {
    try {
      return window.localStorage.getItem(HOME_SWITCHER_STORAGE_KEY) || null;
    } catch (e) {
      return null;
    }
  }

  _persistSelectedHomeId(homeId) {
    try {
      if (homeId === null) {
        window.localStorage.removeItem(HOME_SWITCHER_STORAGE_KEY);
      } else {
        window.localStorage.setItem(HOME_SWITCHER_STORAGE_KEY, homeId);
      }
    } catch (e) {
      // ignore — приватный режим, переполнение и т.п.
    }
  }

  _onHomeSelected(e) {
    const homeId = e.detail?.homeId ?? null;
    this._selectedHomeId = homeId;
    this._persistSelectedHomeId(homeId);
  }

  /** Devices, отфильтрованные по выбранному дому (или все, если null). */
  get _visibleDevices() {
    if (!this._selectedHomeId) return this._devices;
    return this._devices.filter((d) => d.home_id === this._selectedHomeId);
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
      const [devicesResp, status, homesResp] = await Promise.all([
        this.hass.callWS({ type: "sberhome/get_devices" }),
        this.hass.callWS({ type: "sberhome/get_status" }),
        this.hass.callWS({ type: "sberhome/get_homes" }).catch(() => ({ homes: [] })),
      ]);
      this._devices = devicesResp.devices || [];
      this._status = status;
      this._homes = homesResp?.homes || [];
      // Если выбранного дома больше нет (удалён, не загрузился) — сбрасываем.
      if (
        this._selectedHomeId &&
        !this._homes.some((h) => h.id === this._selectedHomeId)
      ) {
        this._selectedHomeId = null;
        this._persistSelectedHomeId(null);
      }
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
        min-height: 100%;
        font-family: var(--paper-font-body1_-_font-family, "Roboto", sans-serif);
        color: var(--primary-text-color);
        background: var(--primary-background-color);
        box-sizing: border-box;
      }

      /* Шапка + табы в собственном container'е — view-компоненты
         (sberhome-device-picker, monitor-view, ...) имеют свой padding,
         поэтому host оставлен без отступов. */
      .top {
        padding: 16px 16px 0;
      }

      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
        flex-wrap: wrap;
        gap: 8px;
      }

      .header h1 {
        margin: 0;
        font-size: 24px;
        font-weight: 400;
        display: flex;
        align-items: baseline;
        gap: 8px;
      }

      .header .version {
        font-size: 13px;
        font-weight: 400;
        color: var(--secondary-text-color);
        font-family: ui-monospace, SFMono-Regular, monospace;
      }

      .header-actions {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }

      /* Refresh-btn в стиле HA-card form-controls: padding/border-radius/
         border одинаковые с home-switcher select'ом и category-dropdown'ом
         внутри device-picker. */
      .refresh-btn {
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        padding: 8px 12px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }
      .refresh-btn:hover:not([disabled]) {
        background: var(--secondary-background-color);
      }
      .refresh-btn[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .tabs {
        display: flex;
        border-bottom: 2px solid var(--divider-color, #e0e0e0);
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
      }
      .tabs::-webkit-scrollbar {
        display: none;
      }

      .tab {
        padding: 12px 24px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--secondary-text-color);
        border-bottom: 2px solid transparent;
        margin-bottom: -2px;
        transition: color 0.2s, border-color 0.2s;
        user-select: none;
        white-space: nowrap;
        flex-shrink: 0;
      }
      .tab:hover {
        color: var(--primary-color);
      }
      .tab.active {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }

      .content {
        /* контент рисуется встроенными view-компонентами, padding на них
           самих — здесь только container */
      }

      .error {
        padding: 12px 16px;
        margin: 0 16px 16px;
        background: var(--error-color);
        color: #fff;
        border-radius: 8px;
        font-size: 13px;
      }

      /* ── Mobile (планшеты + телефоны) ── */
      @media (max-width: 768px) {
        .top {
          padding: 8px 8px 0;
        }
        .header h1 {
          font-size: 20px;
        }
        .header {
          margin-bottom: 12px;
        }
        .tab {
          padding: 10px 14px;
          font-size: 12px;
        }
        .error {
          margin: 0 8px 12px;
        }
      }
    `;
  }

  render() {
    const tabs = ["Devices", "Voice Intents", "Monitor", "Debug", "Settings"];
    return html`
      <div class="top">
        <div class="header">
          <h1>
            SberHome
            ${this._status?.version
              ? html`<span class="version">v${this._status.version}</span>`
              : ""}
          </h1>
          <div class="header-actions">
            <sberhome-home-switcher
              .homes=${this._homes}
              .selectedHomeId=${this._selectedHomeId}
              @home-selected=${this._onHomeSelected}
            ></sberhome-home-switcher>
            <button
              class="refresh-btn"
              @click=${this._forceRefresh}
              ?disabled=${this._loading}
              title="Принудительно обновить state из Sber Gateway"
            >
              <span aria-hidden="true">${this._loading ? "⟳" : "↻"}</span>
              <span>Обновить</span>
            </button>
          </div>
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
      </div>

      ${this._error ? html`<div class="error">${this._error}</div>` : ""}
      <div class="content"
        @toast=${this._onToast}
        @show-device-detail=${this._onShowDeviceDetail}
        @device-toggled=${this._onDeviceToggled}>
        ${this._tab === 0 ? html`
          <sberhome-device-picker .hass=${this.hass}
            .devices=${this._visibleDevices}>
          </sberhome-device-picker>` : ""}
        ${this._tab === 1 ? html`
          <sberhome-intents-view .hass=${this.hass}
            .homes=${this._homes}
            .selectedHomeId=${this._selectedHomeId}>
          </sberhome-intents-view>` : ""}
        ${this._tab === 2 ? html`
          <sberhome-monitor-view .hass=${this.hass} .status=${this._status}>
          </sberhome-monitor-view>` : ""}
        ${this._tab === 3 ? html`
          <sberhome-debug-view .hass=${this.hass} .devices=${this._visibleDevices}>
          </sberhome-debug-view>` : ""}
        ${this._tab === 4 ? html`
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
