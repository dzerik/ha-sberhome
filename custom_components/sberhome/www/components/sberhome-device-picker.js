/**
 * SberHome — Device picker with room/category filters.
 *
 * Клик на строке / иконке / имени → открывает модальное окно, где есть
 * подключение/отключение + выбор HA space. Per-row checkbox'ов больше нет.
 */

import { LitElement, html, css } from "../lit-base.js";

const IMG_BASE = "https://img.iot.sberdevices.ru";

// MDI иконки fallback по HA-категории (если у устройства нет Sber photo).
const CATEGORY_MDI = {
  light: "mdi:lightbulb",
  switch: "mdi:toggle-switch",
  socket: "mdi:power-socket-eu",
  sensor_temp: "mdi:thermometer",
  sensor_humidity: "mdi:water-percent",
  sensor_door: "mdi:door",
  sensor_pir: "mdi:motion-sensor",
  sensor_smoke: "mdi:smoke-detector",
  sensor_gas: "mdi:gas-cylinder",
  sensor_water_leak: "mdi:water-alert",
  curtain: "mdi:curtains",
  window_blind: "mdi:blinds",
  gate: "mdi:gate",
  valve: "mdi:valve",
  hub: "mdi:hub",
  kettle: "mdi:kettle",
  vacuum_cleaner: "mdi:robot-vacuum",
  tv: "mdi:television",
  led_strip: "mdi:led-strip",
  hvac_ac: "mdi:air-conditioner",
  hvac_boiler: "mdi:water-boiler",
  hvac_humidifier: "mdi:air-humidifier",
  hvac_fan: "mdi:fan",
  hvac_heater: "mdi:radiator",
  hvac_radiator: "mdi:radiator",
  hvac_air_purifier: "mdi:air-purifier",
  hvac_underfloor_heating: "mdi:heating-coil",
  intercom: "mdi:door-closed-lock",
  relay: "mdi:electric-switch",
  scenario_button: "mdi:gesture-tap-button",
};

function sberIconUrl(iconPath) {
  if (!iconPath) return null;
  return iconPath.startsWith("http") ? iconPath : `${IMG_BASE}${iconPath}`;
}

class SberHomeDevicePicker extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      devices: { type: Array },
      _filter: { type: String },
      _categoryFilter: { type: String },
    };
  }

  constructor() {
    super();
    this.devices = [];
    this._filter = "";
    this._categoryFilter = "";
  }

  _openDetail(deviceId) {
    this.dispatchEvent(
      new CustomEvent("show-device-detail", {
        detail: { deviceId },
        bubbles: true,
        composed: true,
      })
    );
  }

  _filtered() {
    let list = this.devices;
    if (this._categoryFilter) {
      list = list.filter((d) => d.category === this._categoryFilter);
    }
    if (this._filter) {
      const f = this._filter.toLowerCase();
      list = list.filter(
        (d) =>
          (d.name || "").toLowerCase().includes(f) ||
          (d.category || "").toLowerCase().includes(f) ||
          (d.room_name || "").toLowerCase().includes(f) ||
          (d.image_set_type || "").toLowerCase().includes(f)
      );
    }
    return list;
  }

  _uniqueCategories() {
    return [...new Set(this.devices.map((d) => d.category).filter(Boolean))].sort();
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      .toolbar {
        display: flex; gap: 12px; align-items: center;
        margin-bottom: 16px; flex-wrap: wrap;
      }
      input[type="search"] {
        flex: 1; min-width: 200px; padding: 8px 12px;
        border-radius: 6px; border: 1px solid var(--divider-color);
        background: var(--card-background-color); color: var(--primary-text-color);
      }
      select {
        padding: 8px 12px; border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color); color: var(--primary-text-color);
      }
      button {
        padding: 8px 16px; border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color); color: var(--primary-text-color);
        cursor: pointer;
      }
      button:hover { background: var(--secondary-background-color); }
      table {
        width: 100%; border-collapse: collapse;
        background: var(--card-background-color);
        border-radius: 8px; overflow: hidden;
      }
      th, td {
        padding: 10px 12px; text-align: left;
        border-bottom: 1px solid var(--divider-color);
      }
      th {
        background: var(--secondary-background-color);
        font-weight: 500; font-size: 13px; color: var(--secondary-text-color);
      }
      tr:hover { background: var(--secondary-background-color); }
      td.disabled { opacity: 0.5; }
      a.device-link {
        color: var(--primary-color);
        cursor: pointer;
        text-decoration: none;
      }
      a.device-link:hover { text-decoration: underline; }
      .badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 12px; background: var(--secondary-background-color);
        color: var(--secondary-text-color);
      }
      .badge.unknown { background: var(--error-color); color: #fff; }
      .badge.room { background: var(--primary-color); color: #fff; opacity: 0.85; }
      .empty { text-align: center; padding: 48px; color: var(--secondary-text-color); }
      .counter { font-size: 13px; color: var(--secondary-text-color); }
      tr.row-clickable { cursor: pointer; }
      tr.disabled-row td:not(.icon-cell) { opacity: 0.5; }
      td.icon-cell {
        width: 48px;
        padding: 6px;
      }
      .device-icon {
        width: 36px;
        height: 36px;
        border-radius: 8px;
        object-fit: contain;
        background: var(--primary-background-color);
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .device-icon.disabled {
        filter: grayscale(100%);
        opacity: 0.4;
      }
      .device-icon img {
        width: 100%;
        height: 100%;
        border-radius: 8px;
        object-fit: contain;
      }
      .device-icon ha-icon, .device-icon .fallback-icon {
        --mdc-icon-size: 24px;
        color: var(--primary-text-color);
        font-size: 24px;
      }
      .badge.off {
        background: var(--error-color);
        color: #fff;
        opacity: 0.8;
      }
      .badge.unsupported {
        background: var(--warning-color, #f5a623);
        color: #fff;
        opacity: 0.9;
      }
      tr.unsupported-row td:not(.icon-cell) { opacity: 0.55; }
    `;
  }

  _renderDeviceIcon(d) {
    const url = sberIconUrl(d.icon_path);
    const cls = `device-icon ${d.enabled ? "" : "disabled"}`;
    if (url) {
      return html`
        <div class=${cls}>
          <img
            src=${url}
            alt=${d.category || "device"}
            loading="lazy"
            @error=${(e) => {
              e.target.style.display = "none";
              e.target.parentElement.innerHTML = this._fallbackIcon(d);
            }}
          />
        </div>
      `;
    }
    return html`<div class=${cls}>${this._fallbackLit(d)}</div>`;
  }

  _fallbackLit(d) {
    const icon = CATEGORY_MDI[d.category] || "mdi:devices";
    return html`<ha-icon icon=${icon}></ha-icon>`;
  }

  _fallbackIcon(d) {
    const icon = CATEGORY_MDI[d.category] || "mdi:devices";
    return `<ha-icon icon="${icon}"></ha-icon>`;
  }

  render() {
    const list = this._filtered();
    const enabledCount = list.filter((d) => d.enabled).length;
    const categories = this._uniqueCategories();
    return html`
      <div class="toolbar">
        <input
          type="search"
          placeholder="Поиск по имени, категории, комнате..."
          .value=${this._filter}
          @input=${(e) => (this._filter = e.target.value)}
        />
        <select @change=${(e) => (this._categoryFilter = e.target.value)} .value=${this._categoryFilter}>
          <option value="">Все категории</option>
          ${categories.map((c) => html`<option value=${c}>${c}</option>`)}
        </select>
        <span class="counter">${enabledCount} / ${list.length} подключено</span>
      </div>

      ${list.length === 0
        ? html`<div class="empty">Устройства не найдены.</div>`
        : html`
            <table>
              <thead>
                <tr>
                  <th style="width:56px"></th>
                  <th>Имя</th>
                  <th>Комната Sber</th>
                  <th>Категория</th>
                  <th>Модель</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                ${list.map((d) => {
                  const unsupported = !d.category;
                  const rowClasses = [
                    "row-clickable",
                    d.enabled ? "" : "disabled-row",
                    unsupported ? "unsupported-row" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  const rowTitle = unsupported
                    ? "Категория устройства не поддерживается интеграцией"
                    : "Клик — настройка подключения и пространства";
                  return html`
                    <tr
                      class=${rowClasses}
                      @click=${() => this._openDetail(d.device_id)}
                      title=${rowTitle}
                    >
                      <td class="icon-cell">${this._renderDeviceIcon(d)}</td>
                      <td>
                        <a class="device-link">${d.name}</a>
                      </td>
                      <td>
                        ${d.room_name
                          ? html`<span class="badge room">${d.room_name}</span>`
                          : html`<span style="color:var(--secondary-text-color)">—</span>`}
                      </td>
                      <td>
                        <span class="badge ${d.category ? "" : "unknown"}">
                          ${d.category || "unknown"}
                        </span>
                      </td>
                      <td>
                        ${unsupported
                          ? html`<span class="badge unsupported">не поддерживается</span>`
                          : d.enabled
                            ? html`<span class="badge room">${d.entity_count} entities</span>`
                            : html`<span class="badge off">отключено</span>`}
                      </td>
                    </tr>
                  `;
                })}
              </tbody>
            </table>
          `}
    `;
  }
}

customElements.define("sberhome-device-picker", SberHomeDevicePicker);
