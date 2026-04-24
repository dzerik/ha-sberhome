/**
 * SberHome — Settings tab (scan_interval, force refresh).
 */

import { LitElement, html, css } from "../lit-base.js";

class SberHomeSettings extends LitElement {
  static get properties() {
    return { hass: { type: Object }, _scanInterval: { type: Number } };
  }

  constructor() {
    super();
    this._scanInterval = 30;
  }

  async connectedCallback() {
    super.connectedCallback();
    if (!this.hass) return;
    const s = await this.hass.callWS({ type: "sberhome/get_settings" });
    this._scanInterval = s.scan_interval;
  }

  async _save() {
    await this.hass.callWS({
      type: "sberhome/update_settings",
      scan_interval: parseInt(this._scanInterval, 10),
    });
    this.dispatchEvent(
      new CustomEvent("toast", {
        detail: { message: "Настройки сохранены", type: "success" },
        bubbles: true,
        composed: true,
      })
    );
  }

  async _refresh() {
    await this.hass.callWS({ type: "sberhome/force_refresh" });
    this.dispatchEvent(
      new CustomEvent("toast", {
        detail: { message: "Refresh запрошен", type: "info" },
        bubbles: true,
        composed: true,
      })
    );
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; max-width: 480px; }
      .field { margin-bottom: 16px; }
      label {
        display: block;
        margin-bottom: 6px;
        color: var(--secondary-text-color);
        font-size: 13px;
      }
      input[type="number"] {
        padding: 8px 12px;
        border-radius: 6px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        width: 100%;
      }
      button {
        padding: 10px 20px;
        border-radius: 6px;
        background: var(--primary-color);
        color: #fff;
        border: none;
        cursor: pointer;
        margin-right: 8px;
      }
      button.secondary {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
      }
    `;
  }

  render() {
    return html`
      <div class="field">
        <label>Интервал polling (сек)</label>
        <input
          type="number"
          min="10"
          max="3600"
          .value=${this._scanInterval}
          @input=${(e) => (this._scanInterval = e.target.value)}
        />
      </div>
      <button @click=${this._save}>Сохранить</button>
      <button class="secondary" @click=${this._refresh}>Запросить refresh</button>
    `;
  }
}

customElements.define("sberhome-settings", SberHomeSettings);
