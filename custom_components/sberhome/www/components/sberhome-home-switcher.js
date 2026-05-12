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
      .switcher {
        display: flex;
        align-items: center;
        gap: 6px;
        background: rgba(255, 255, 255, 0.15);
        border: 1px solid rgba(255, 255, 255, 0.3);
        padding: 4px 8px 4px 10px;
        border-radius: 6px;
        font-size: 13px;
      }
      .icon {
        font-size: 14px;
        opacity: 0.85;
      }
      select {
        background: transparent;
        color: inherit;
        border: none;
        font-size: 13px;
        padding: 2px 4px;
        cursor: pointer;
        outline: none;
        max-width: 180px;
      }
      select option {
        color: #000;
        background: #fff;
      }
    `;
  }

  render() {
    if (!this.homes || this.homes.length <= 1) {
      return html``;
    }
    const value = this.selectedHomeId || "__all__";
    return html`
      <div class="switcher" title="Фильтр устройств и комнат по дому">
        <span class="icon">🏡</span>
        <select @change=${this._onChange} .value=${value}>
          <option value="__all__" ?selected=${value === "__all__"}>
            Все дома (${this.homes.reduce((s, h) => s + (h.device_count || 0), 0)})
          </option>
          ${this.homes.map(
            (h) => html`
              <option value=${h.id} ?selected=${value === h.id}>
                ${h.name || "Дом"} (${h.device_count || 0})
              </option>
            `
          )}
        </select>
      </div>
    `;
  }
}

customElements.define("sberhome-home-switcher", SberHomeHomeSwitcher);
