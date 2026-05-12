/**
 * Home switcher dropdown — multi-home UI filter (issue #2).
 *
 * Показывает <select> в header панели со списком домов из Sber.
 * Если у юзера один дом — компонент рендерит пусто (скрыт).
 * Состояние выбора (`selected_home_id`) хранится в localStorage.
 *
 * Properties:
 *   - homes:           Array<{id, name, room_count, device_count, is_default}>
 *   - selectedHomeId:  string | null   (null = «Все дома»)
 *
 * Events:
 *   - `home-selected` { detail: { homeId: string | null } } — bubble + composed
 */

import { LitElement, html, css } from "../lit-base.js";

export const HOME_SWITCHER_STORAGE_KEY = "sberhome.selected_home_id";

export class SberHomeHomeSwitcher extends LitElement {
  static get properties() {
    return {
      homes: { type: Array },
      selectedHomeId: { type: String },
    };
  }

  constructor() {
    super();
    this.homes = [];
    this.selectedHomeId = null;
  }

  _onChange(e) {
    const raw = e.target.value;
    const homeId = raw === "__all__" ? null : raw;
    this.dispatchEvent(
      new CustomEvent("home-selected", {
        detail: { homeId },
        bubbles: true,
        composed: true,
      })
    );
  }

  static get styles() {
    return css`
      :host {
        display: inline-flex;
        align-items: center;
      }
      /* Единый стиль с category-dropdown в device-picker (toolbar).
         Геометрия, border-radius, font-size, padding идентичны. */
      select {
        padding: 8px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, rgba(255, 255, 255, 0.3));
        background: var(--card-background-color, rgba(255, 255, 255, 0.15));
        color: var(--primary-text-color, inherit);
        font-size: 13px;
        cursor: pointer;
        outline: none;
        max-width: 220px;
      }
      select option {
        color: var(--primary-text-color, #000);
        background: var(--card-background-color, #fff);
      }
    `;
  }

  render() {
    if (!this.homes || this.homes.length <= 1) {
      return html``;
    }
    const value = this.selectedHomeId || "__all__";
    const totalDevices = this.homes.reduce((s, h) => s + (h.device_count || 0), 0);
    return html`
      <select
        @change=${this._onChange}
        .value=${value}
        title="Фильтр устройств и комнат по дому"
      >
        <option value="__all__" ?selected=${value === "__all__"}>
          Все дома (${totalDevices})
        </option>
        ${this.homes.map(
          (h) => html`
            <option value=${h.id} ?selected=${value === h.id}>
              ${h.name || "Дом"} (${h.device_count || 0})
            </option>
          `
        )}
      </select>
    `;
  }
}

if (!customElements.get("sberhome-home-switcher")) {
  customElements.define("sberhome-home-switcher", SberHomeHomeSwitcher);
}
