/**
 * SberHome — Device picker (opt-in selection table).
 *
 * Displays ALL Sber devices fetched from coordinator with a checkbox per
 * row to enable/disable. Calls `sberhome/toggle_device` WS endpoint.
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
      _filter: { type: String },
      _busyIds: { type: Object },
    };
  }

  constructor() {
    super();
    this.devices = [];
    this._filter = "";
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
          detail: { message: `Ошибка: ${e.message || e}`, type: "error" },
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
    const ids = enabled
      ? this._filtered().map((d) => d.device_id)
      : [];
    try {
      await this.hass.callWS({
        type: "sberhome/set_enabled",
        device_ids: ids,
      });
      this.dispatchEvent(
        new CustomEvent("device-toggled", {
          detail: { all: true },
          bubbles: true,
          composed: true,
        })
      );
    } catch (e) {
      this.dispatchEvent(
        new CustomEvent("toast", {
          detail: { message: `Ошибка: ${e.message || e}`, type: "error" },
          bubbles: true,
          composed: true,
        })
      );
    }
  }

  _filtered() {
    if (!this._filter) return this.devices;
    const f = this._filter.toLowerCase();
    return this.devices.filter(
      (d) =>
        (d.name || "").toLowerCase().includes(f) ||
        (d.category || "").toLowerCase().includes(f) ||
        (d.image_set_type || "").toLowerCase().includes(f)
    );
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      .toolbar {
        display: flex;
        gap: 12px;
        align-items: center;
        margin-bottom: 16px;
        flex-wrap: wrap;
      }
      input[type="search"] {
        flex: 1;
        min-width: 240px;
        padding: 8px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        color: var(--primary-text-color);
      }
      button {
        padding: 8px 16px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        color: var(--primary-text-color);
        cursor: pointer;
      }
      button:hover { background: var(--secondary-background-color); }
      table {
        width: 100%;
        border-collapse: collapse;
        background: var(--card-background-color);
        border-radius: 8px;
        overflow: hidden;
      }
      th, td {
        padding: 12px;
        text-align: left;
        border-bottom: 1px solid var(--divider-color);
      }
      th {
        background: var(--secondary-background-color);
        font-weight: 500;
        font-size: 13px;
        color: var(--secondary-text-color);
      }
      tr:hover { background: var(--secondary-background-color); }
      td.disabled { opacity: 0.5; }
      .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
      }
      .badge.unknown { background: var(--error-color); color: #fff; }
      input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; }
      .empty {
        text-align: center;
        padding: 48px;
        color: var(--secondary-text-color);
      }
    `;
  }

  render() {
    const list = this._filtered();
    const enabledCount = list.filter((d) => d.enabled).length;
    return html`
      <div class="toolbar">
        <input
          type="search"
          placeholder="Поиск по имени, категории, image_set_type…"
          .value=${this._filter}
          @input=${(e) => (this._filter = e.target.value)}
        />
        <button @click=${() => this._selectAll(true)}>Выбрать все</button>
        <button @click=${() => this._selectAll(false)}>Снять все</button>
        <span>${enabledCount} / ${list.length} выбрано</span>
      </div>

      ${list.length === 0
        ? html`<div class="empty">Устройства не найдены.</div>`
        : html`
            <table>
              <thead>
                <tr>
                  <th style="width:40px"></th>
                  <th>Имя</th>
                  <th>Категория</th>
                  <th>Image type</th>
                  <th>Модель</th>
                  <th>Entities</th>
                  <th>Платформы</th>
                </tr>
              </thead>
              <tbody>
                ${list.map(
                  (d) => html`
                    <tr>
                      <td>
                        <input
                          type="checkbox"
                          ?checked=${d.enabled}
                          ?disabled=${this._busyIds.has(d.device_id)}
                          @change=${(e) =>
                            this._toggleDevice(d.device_id, e.target.checked)}
                        />
                      </td>
                      <td class=${d.enabled ? "" : "disabled"}>${d.name}</td>
                      <td>
                        <span class="badge ${d.category ? "" : "unknown"}">
                          ${d.category || "unknown"}
                        </span>
                      </td>
                      <td><code>${d.image_set_type}</code></td>
                      <td>${d.model || "—"}</td>
                      <td>${d.entity_count}</td>
                      <td>
                        ${(d.platforms || [])
                          .map(
                            (p) =>
                              html`<span class="badge">${p.split(".")[1] || p}</span> `
                          )}
                      </td>
                    </tr>
                  `
                )}
              </tbody>
            </table>
          `}
    `;
  }
}

customElements.define("sberhome-device-picker", SberHomeDevicePicker);
