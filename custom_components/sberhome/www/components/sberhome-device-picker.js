/**
 * SberHome — Device picker with room/category filters.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

class SberHomeDevicePicker extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      devices: { type: Array },
      roomFilter: { type: String },
      _filter: { type: String },
      _categoryFilter: { type: String },
      _busyIds: { type: Object },
    };
  }

  constructor() {
    super();
    this.devices = [];
    this.roomFilter = null;
    this._filter = "";
    this._categoryFilter = "";
    this._busyIds = new Set();
  }

  async _toggleDevice(deviceId, enabled) {
    if (this._busyIds.has(deviceId)) return;
    this._busyIds = new Set([...this._busyIds, deviceId]);
    this.requestUpdate();
    try {
      await this.hass.callWS({
        type: "sberhome/toggle_device",
        device_id: deviceId,
        enabled,
      });
      this.dispatchEvent(
        new CustomEvent("device-toggled", {
          detail: { deviceId, enabled },
          bubbles: true,
          composed: true,
        })
      );
    } catch (e) {
      this.dispatchEvent(
        new CustomEvent("toast", {
          detail: { message: `Error: ${e.message || e}`, type: "error" },
          bubbles: true,
          composed: true,
        })
      );
    } finally {
      const next = new Set(this._busyIds);
      next.delete(deviceId);
      this._busyIds = next;
      this.requestUpdate();
    }
  }

  async _selectAll(enabled) {
    const ids = enabled ? this._filtered().map((d) => d.device_id) : [];
    try {
      await this.hass.callWS({ type: "sberhome/set_enabled", device_ids: ids });
      this.dispatchEvent(
        new CustomEvent("device-toggled", { detail: { all: true }, bubbles: true, composed: true })
      );
    } catch (e) {
      this.dispatchEvent(
        new CustomEvent("toast", {
          detail: { message: `Error: ${e.message || e}`, type: "error" },
          bubbles: true, composed: true,
        })
      );
    }
  }

  _filtered() {
    let list = this.devices;
    if (this.roomFilter) {
      list = list.filter((d) => d.room_id === this.roomFilter);
    }
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
      .badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 12px; background: var(--secondary-background-color);
        color: var(--secondary-text-color);
      }
      .badge.unknown { background: var(--error-color); color: #fff; }
      .badge.room { background: var(--primary-color); color: #fff; opacity: 0.85; }
      input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; }
      .empty { text-align: center; padding: 48px; color: var(--secondary-text-color); }
      .counter { font-size: 13px; color: var(--secondary-text-color); }
    `;
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
        <button @click=${() => this._selectAll(true)}>Выбрать все</button>
        <button @click=${() => this._selectAll(false)}>Снять все</button>
        <span class="counter">${enabledCount} / ${list.length} выбрано</span>
      </div>

      ${list.length === 0
        ? html`<div class="empty">Устройства не найдены.</div>`
        : html`
            <table>
              <thead>
                <tr>
                  <th style="width:40px"></th>
                  <th>Имя</th>
                  <th>Комната</th>
                  <th>Категория</th>
                  <th>Модель</th>
                  <th>Entities</th>
                  <th>Платформы</th>
                </tr>
              </thead>
              <tbody>
                ${list.map((d) => html`
                  <tr>
                    <td>
                      <input type="checkbox" ?checked=${d.enabled}
                        ?disabled=${this._busyIds.has(d.device_id)}
                        @change=${(e) => this._toggleDevice(d.device_id, e.target.checked)}
                      />
                    </td>
                    <td class=${d.enabled ? "" : "disabled"}>${d.name}</td>
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
                    <td>${d.model || "—"}</td>
                    <td>${d.entity_count}</td>
                    <td>
                      ${(d.platforms || []).map(
                        (p) => html`<span class="badge">${p.split(".")[1] || p}</span> `
                      )}
                    </td>
                  </tr>
                `)}
              </tbody>
            </table>
          `}
    `;
  }
}

customElements.define("sberhome-device-picker", SberHomeDevicePicker);
