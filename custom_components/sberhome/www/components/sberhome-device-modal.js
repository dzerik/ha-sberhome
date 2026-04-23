/**
 * SberHome — Device detail modal.
 *
 * Открывается по клику на устройство в Devices tab. Показывает:
 *  - Photo из Sber CDN (img.iot.sberdevices.ru)
 *  - Manufacturer, model, sw_version, serial, MAC, IP, connection type
 *  - Attributes с диапазонами / enum values / текущими reported values
 *  - Raw JSON (для багрепортов)
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

const IMG_BASE = "https://img.iot.sberdevices.ru";

function imgUrl(path) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${IMG_BASE}${path}`;
}

function pickPhotoUrl(raw) {
  const images = raw?.images || {};
  return imgUrl(
    images.photo ||
      images.cards_3d_on ||
      images.launcher_extra_large_on ||
      images.list_on ||
      images.launcher_small_box_on
  );
}

function attrCurrentValue(raw, key) {
  const entry = (raw?.reported_state || []).find((s) => s.key === key);
  if (!entry) return null;
  const type = entry.type;
  if (type === "BOOL") return entry.bool_value;
  if (type === "INTEGER") return entry.integer_value;
  if (type === "FLOAT") return entry.float_value;
  if (type === "STRING") return entry.string_value;
  if (type === "ENUM") return entry.enum_value;
  if (type === "COLOR" && entry.color_value) {
    const { h, s, v } = entry.color_value;
    return `h=${h} s=${s} v=${v}`;
  }
  return null;
}

function attrRangeOrOptions(attr) {
  if (attr.int_values?.range) {
    const r = attr.int_values.range;
    const unit = attr.int_values.unit ? ` ${attr.int_values.unit}` : "";
    return `${r.min}..${r.max}${r.step ? ` step ${r.step}` : ""}${unit}`;
  }
  if (attr.float_values?.range) {
    const r = attr.float_values.range;
    return `${r.min}..${r.max}`;
  }
  if (attr.enum_values?.values?.length) {
    return attr.enum_values.values.join(" | ");
  }
  if (attr.color_values) {
    const c = attr.color_values;
    const h = c.h ? `h=${c.h.min}..${c.h.max}` : "";
    const s = c.s ? `s=${c.s.min}..${c.s.max}` : "";
    const v = c.v ? `v=${c.v.min}..${c.v.max}` : "";
    return [h, s, v].filter(Boolean).join(" ");
  }
  return "—";
}

class SberHomeDeviceModal extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      deviceId: { type: String },
      _detail: { type: Object },
      _deviceSummary: { type: Object },
      _error: { type: String },
      _tab: { type: String },
      _toast: { type: String },
      _busy: { type: Boolean },
      _confirmDisconnect: { type: Boolean },
      _selectedAreaId: { type: String },
    };
  }

  constructor() {
    super();
    this._detail = null;
    this._deviceSummary = null;
    this._error = "";
    this._tab = "connection";
    this._toast = "";
    this._busy = false;
    this._confirmDisconnect = false;
    this._selectedAreaId = "";
  }

  updated(changed) {
    if (changed.has("deviceId") && this.deviceId && this.hass) {
      this._load();
    }
  }

  async _load() {
    this._detail = null;
    this._deviceSummary = null;
    this._error = "";
    this._confirmDisconnect = false;
    try {
      const [detail, devicesResp] = await Promise.all([
        this.hass.callWS({
          type: "sberhome/device_detail",
          device_id: this.deviceId,
        }),
        this.hass.callWS({ type: "sberhome/get_devices" }),
      ]);
      this._detail = detail;
      this._deviceSummary =
        (devicesResp.devices || []).find((d) => d.device_id === this.deviceId) || null;
      // Приоритет: уже назначенный HA area (не трогаем если был) →
      // автоматический match по имени Sber-комнаты → пусто.
      this._selectedAreaId =
        this._deviceSummary?.ha_area_id ||
        this._matchAreaByRoomName(this._deviceSummary?.room_name) ||
        "";
    } catch (e) {
      this._error = e.message || String(e);
    }
  }

  _autoMatchHint(summary) {
    if (!summary?.room_name || !this._selectedAreaId) return "";
    // Hint показываем только если selected area == auto-matched (а не
    // руками выбрали); проверка простая — тот ли ID нам бы выдал матчер.
    const matched = this._matchAreaByRoomName(summary.room_name);
    if (matched !== this._selectedAreaId) return "";
    const areaName =
      this.hass.areas?.[this._selectedAreaId]?.name || this._selectedAreaId;
    return html`
      <div class="hint-auto">
        ↺ Подобрано автоматически: Sber-комната
        <b>«${summary.room_name}»</b> → HA <b>«${areaName}»</b>
      </div>
    `;
  }

  _matchAreaByRoomName(roomName) {
    if (!roomName) return "";
    const needle = roomName.trim().toLowerCase();
    if (!needle) return "";
    const areas = Object.values(this.hass?.areas || {});
    // 1. Exact match (case-insensitive).
    const exact = areas.find(
      (a) => (a.name || "").trim().toLowerCase() === needle
    );
    if (exact) return exact.area_id;
    // 2. Substring match (HA area содержит Sber room name или наоборот).
    const partial = areas.find((a) => {
      const n = (a.name || "").trim().toLowerCase();
      return n && (n.includes(needle) || needle.includes(n));
    });
    return partial?.area_id || "";
  }

  get _areas() {
    return Object.values(this.hass?.areas || {}).sort((a, b) =>
      (a.name || "").localeCompare(b.name || "")
    );
  }

  async _connect() {
    if (!this.deviceId || this._busy) return;
    this._busy = true;
    try {
      await this.hass.callWS({
        type: "sberhome/toggle_device",
        device_id: this.deviceId,
        enabled: true,
      });
      // Ждём пока HA зарегистрирует девайс (entity forward is sync через coord,
      // но для device_registry нужен ~short delay).
      await new Promise((r) => setTimeout(r, 800));
      if (this._selectedAreaId) {
        try {
          await this.hass.callWS({
            type: "sberhome/set_device_area",
            device_id: this.deviceId,
            area_id: this._selectedAreaId,
          });
        } catch (err) {
          // Не критично — покажем предупреждение, но девайс всё-таки подключён.
          this._toast = `Подключено, но area не назначен: ${err.message || err}`;
          setTimeout(() => (this._toast = ""), 3500);
          await this._load();
          this.dispatchEvent(
            new CustomEvent("device-toggled", { bubbles: true, composed: true })
          );
          return;
        }
      }
      this._toast = "Подключено";
      setTimeout(() => (this._toast = ""), 2000);
      await this._load();
      this.dispatchEvent(
        new CustomEvent("device-toggled", { bubbles: true, composed: true })
      );
    } catch (e) {
      this._toast = `Ошибка: ${e.message || e}`;
      setTimeout(() => (this._toast = ""), 3000);
    } finally {
      this._busy = false;
    }
  }

  async _disconnect() {
    if (!this.deviceId || this._busy) return;
    this._busy = true;
    try {
      await this.hass.callWS({
        type: "sberhome/toggle_device",
        device_id: this.deviceId,
        enabled: false,
      });
      this._toast = "Отключено";
      setTimeout(() => (this._toast = ""), 2000);
      this._confirmDisconnect = false;
      await this._load();
      this.dispatchEvent(
        new CustomEvent("device-toggled", { bubbles: true, composed: true })
      );
    } catch (e) {
      this._toast = `Ошибка: ${e.message || e}`;
      setTimeout(() => (this._toast = ""), 3000);
    } finally {
      this._busy = false;
    }
  }

  async _changeArea() {
    if (!this.deviceId || this._busy) return;
    this._busy = true;
    try {
      await this.hass.callWS({
        type: "sberhome/set_device_area",
        device_id: this.deviceId,
        area_id: this._selectedAreaId || null,
      });
      this._toast = "Пространство обновлено";
      setTimeout(() => (this._toast = ""), 2000);
      await this._load();
    } catch (e) {
      this._toast = `Ошибка: ${e.message || e}`;
      setTimeout(() => (this._toast = ""), 3000);
    } finally {
      this._busy = false;
    }
  }

  _close() {
    this.dispatchEvent(
      new CustomEvent("close-modal", { bubbles: true, composed: true })
    );
  }

  _onBackdropClick(e) {
    if (e.target === e.currentTarget) this._close();
  }

  async _copyRaw() {
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(this._detail?.raw_payload ?? this._detail, null, 2)
      );
      this._toast = "JSON скопирован";
    } catch {
      this._toast = "Не удалось скопировать";
    }
    setTimeout(() => {
      this._toast = "";
    }, 2000);
  }

  async _refetchIndividual() {
    if (!this.hass || !this.deviceId) return;
    this._toast = "GET /devices/{id}…";
    try {
      const resp = await this.hass.callWS({
        type: "sberhome/refetch_device",
        device_id: this.deviceId,
      });
      this._detail = { ...this._detail, raw_payload: resp.raw_payload };
      this._tab = "raw";
      this._toast = "Получен свежий payload";
    } catch (e) {
      this._toast = `Ошибка: ${e.message || e}`;
    }
    setTimeout(() => {
      this._toast = "";
    }, 3000);
  }

  _renderConnection(raw) {
    const summary = this._deviceSummary || {};
    const isEnabled = !!summary.enabled;
    const areas = this._areas;
    const currentAreaName = isEnabled && summary.ha_area_id
      ? (this.hass.areas?.[summary.ha_area_id]?.name || summary.ha_area_id)
      : null;
    return html`
      <div class="conn-card">
        <div class="status-row">
          <span
            class="status-pill ${isEnabled ? "on" : "off"}"
            title="Статус в Home Assistant"
          >
            ${isEnabled ? "● Подключено" : "○ Отключено"}
          </span>
          ${isEnabled && currentAreaName
            ? html`<span class="badge-area">Пространство: ${currentAreaName}</span>`
            : ""}
          ${summary.entity_count
            ? html`<span class="meta">${summary.entity_count} entities</span>`
            : ""}
        </div>

        ${!isEnabled
          ? html`
              <div class="section">
                <div class="section-header"><h3>Подключить в Home Assistant</h3></div>
                <p class="muted">
                  После подключения ${summary.entity_count || "все"} entities
                  этого устройства появятся в HA и их можно будет использовать в
                  автоматизациях, dashboard'ах и сценариях.
                </p>
                <label class="field-label">Пространство (опционально)</label>
                <select
                  @change=${(e) => (this._selectedAreaId = e.target.value)}
                  ?disabled=${this._busy}
                >
                  <option value="" ?selected=${!this._selectedAreaId}>
                    — без пространства —
                  </option>
                  ${areas.map(
                    (a) => html`
                      <option
                        value=${a.area_id}
                        ?selected=${a.area_id === this._selectedAreaId}
                      >
                        ${a.name}
                      </option>
                    `
                  )}
                </select>
                ${this._autoMatchHint(summary)}
                <div style="margin-top:16px">
                  <button
                    class="btn-primary"
                    @click=${this._connect}
                    ?disabled=${this._busy}
                  >
                    ${this._busy ? "Подключение…" : "Подключить"}
                  </button>
                </div>
              </div>
            `
          : html`
              <div class="section">
                <div class="section-header"><h3>Пространство в Home Assistant</h3></div>
                <select
                  @change=${(e) => (this._selectedAreaId = e.target.value)}
                  ?disabled=${this._busy}
                >
                  <option value="" ?selected=${!this._selectedAreaId}>
                    — без пространства —
                  </option>
                  ${areas.map(
                    (a) => html`
                      <option
                        value=${a.area_id}
                        ?selected=${a.area_id === this._selectedAreaId}
                      >
                        ${a.name}
                      </option>
                    `
                  )}
                </select>
                <div style="margin-top:12px">
                  <button
                    @click=${this._changeArea}
                    ?disabled=${this._busy ||
                      this._selectedAreaId === (summary.ha_area_id || "")}
                  >
                    Применить пространство
                  </button>
                </div>
              </div>

              <div class="section danger-zone">
                <div class="section-header">
                  <h3>Отключение устройства</h3>
                </div>
                ${!this._confirmDisconnect
                  ? html`
                      <button
                        class="btn-danger"
                        @click=${() => (this._confirmDisconnect = true)}
                      >
                        Отключить от Home Assistant
                      </button>
                    `
                  : html`
                      <div class="warning">
                        <strong>⚠ Внимание.</strong>
                        После отключения все entities этого устройства будут
                        <b>удалены из Home Assistant</b>, а <b>автоматизации,
                        скрипты и dashboard'ы</b>, ссылающиеся на эти entities,
                        могут перестать работать. Sber-устройство не
                        пострадает — это только разрыв интеграции с HA.
                      </div>
                      <div style="display:flex; gap:8px; margin-top:12px">
                        <button
                          class="btn-danger"
                          @click=${this._disconnect}
                          ?disabled=${this._busy}
                        >
                          ${this._busy ? "Отключение…" : "Да, отключить"}
                        </button>
                        <button
                          @click=${() => (this._confirmDisconnect = false)}
                          ?disabled=${this._busy}
                        >
                          Отмена
                        </button>
                      </div>
                    `}
              </div>
            `}
      </div>
    `;
  }

  _renderInfo(raw) {
    const info = raw.device_info || {};
    const owner = raw.owner_info || {};
    const rows = [
      ["Имя", raw.name?.name || this._detail.name],
      ["Категория", this._detail.category],
      ["Тип устройства", raw.device_type_name],
      ["image_set_type", raw.image_set_type],
      ["Производитель", info.manufacturer],
      ["Модель", info.model || info.product_id],
      ["Описание", info.description],
      ["HW версия", info.hw_version || raw.hw_version],
      ["SW версия", info.sw_version || raw.sw_version],
      ["Serial", raw.serial_number],
      ["MAC", raw.mac_address],
      ["IP", raw.ip_address],
      ["Connection", raw.connection_type],
      ["External ID", raw.external_id],
      ["Correction", raw.correction?.formula_type],
      ["Хозяин", owner.is_owner ? "Да" : "Нет"],
    ].filter(([, v]) => v !== null && v !== undefined && v !== "");

    return html`
      <table class="info-table">
        ${rows.map(
          ([k, v]) => html`<tr><th>${k}</th><td>${v}</td></tr>`
        )}
      </table>
    `;
  }

  _renderAttrs(raw) {
    const attrs = raw.attributes || [];
    if (!attrs.length) return html`<div class="empty">Нет атрибутов</div>`;
    return html`
      <table class="attr-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Type</th>
            <th>Range / Values</th>
            <th>Current (reported)</th>
          </tr>
        </thead>
        <tbody>
          ${attrs.map((a) => {
            const current = attrCurrentValue(raw, a.key);
            return html`
              <tr>
                <td><code>${a.key}</code></td>
                <td><span class="pill">${a.type}</span></td>
                <td class="range">${attrRangeOrOptions(a)}</td>
                <td class="current">
                  ${current === null || current === ""
                    ? html`<span class="muted">—</span>`
                    : html`<code>${String(current)}</code>`}
                </td>
              </tr>
            `;
          })}
        </tbody>
      </table>
    `;
  }

  _renderRaw(raw) {
    return html`
      <pre>${JSON.stringify(raw, null, 2)}</pre>
    `;
  }

  _renderImages(raw) {
    const images = raw.images || {};
    const entries = Object.entries(images).filter(([, v]) => v);
    if (!entries.length) return html`<div class="empty">Нет изображений</div>`;
    return html`
      <div class="gallery">
        ${entries.map(
          ([k, v]) => html`
            <figure>
              <img src=${imgUrl(v)} alt=${k} loading="lazy" />
              <figcaption>${k}</figcaption>
            </figure>
          `
        )}
      </div>
    `;
  }

  static get styles() {
    return css`
      .backdrop {
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.55);
        display: flex;
        align-items: flex-start;
        justify-content: center;
        z-index: 20;
        padding: 32px 16px;
        overflow-y: auto;
      }
      .dialog {
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border-radius: 12px;
        max-width: 960px;
        width: 100%;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        overflow: hidden;
      }
      header {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 16px 20px;
        background: var(--secondary-background-color);
        border-bottom: 1px solid var(--divider-color);
      }
      header img.photo {
        width: 72px;
        height: 72px;
        border-radius: 8px;
        object-fit: cover;
        background: var(--primary-background-color);
      }
      header .title {
        flex: 1;
        min-width: 0;
      }
      header h2 {
        margin: 0;
        font-size: 18px;
      }
      header .subtitle {
        font-size: 13px;
        color: var(--secondary-text-color);
        margin-top: 2px;
      }
      header .close {
        background: transparent;
        border: none;
        font-size: 24px;
        cursor: pointer;
        color: var(--primary-text-color);
        width: 36px;
        height: 36px;
        border-radius: 50%;
      }
      header .close:hover {
        background: var(--primary-background-color);
      }
      nav {
        display: flex;
        border-bottom: 1px solid var(--divider-color);
        padding: 0 12px;
      }
      nav .tab {
        padding: 12px 16px;
        cursor: pointer;
        border-bottom: 3px solid transparent;
        font-size: 13px;
        text-transform: uppercase;
        font-weight: 500;
        opacity: 0.7;
      }
      nav .tab.active {
        border-color: var(--primary-color);
        opacity: 1;
      }
      .body {
        padding: 20px;
        max-height: calc(100vh - 260px);
        overflow-y: auto;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
      }
      table.info-table th {
        text-align: left;
        padding: 6px 12px 6px 0;
        color: var(--secondary-text-color);
        font-weight: 500;
        width: 160px;
        white-space: nowrap;
      }
      table.info-table td {
        padding: 6px 0;
      }
      table.attr-table {
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        overflow: hidden;
      }
      table.attr-table th, table.attr-table td {
        padding: 8px 12px;
        text-align: left;
        border-bottom: 1px solid var(--divider-color);
      }
      table.attr-table thead th {
        background: var(--secondary-background-color);
        font-weight: 600;
        font-size: 12px;
        text-transform: uppercase;
      }
      table.attr-table tr:last-child td {
        border-bottom: none;
      }
      .pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        background: var(--primary-background-color);
        font-size: 11px;
      }
      code {
        background: var(--primary-background-color);
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 12px;
      }
      .range {
        color: var(--secondary-text-color);
        font-family: var(--code-font-family, monospace);
        font-size: 12px;
      }
      .muted {
        color: var(--secondary-text-color);
      }
      pre {
        background: var(--code-editor-background-color, #1e1e1e);
        color: var(--code-editor-text-color, #d4d4d4);
        padding: 12px;
        border-radius: 6px;
        overflow: auto;
        font-size: 11px;
        white-space: pre-wrap;
        margin: 0;
      }
      .gallery {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: 12px;
      }
      .gallery figure {
        margin: 0;
        padding: 8px;
        background: var(--secondary-background-color);
        border-radius: 6px;
        text-align: center;
      }
      .gallery img {
        width: 100%;
        height: 110px;
        object-fit: contain;
        background: var(--primary-background-color);
        border-radius: 4px;
      }
      .gallery figcaption {
        font-size: 10px;
        color: var(--secondary-text-color);
        margin-top: 6px;
        word-break: break-word;
      }
      .empty {
        padding: 24px;
        text-align: center;
        color: var(--secondary-text-color);
      }
      .actions {
        padding: 12px 20px;
        border-top: 1px solid var(--divider-color);
        display: flex;
        justify-content: flex-end;
        gap: 8px;
      }
      .actions button {
        padding: 6px 14px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        color: var(--primary-text-color);
        cursor: pointer;
      }
      .actions button:hover {
        background: var(--secondary-background-color);
      }
      .toast {
        position: fixed;
        top: 24px;
        right: 24px;
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        padding: 10px 16px;
        border-radius: 6px;
        z-index: 30;
      }
      .error {
        padding: 16px;
        background: var(--error-color);
        color: #fff;
        border-radius: 6px;
        margin: 20px;
      }
      /* Connection tab */
      .status-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
        flex-wrap: wrap;
      }
      .status-pill {
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 500;
      }
      .status-pill.on {
        background: color-mix(in srgb, var(--success-color, #2e7d32) 20%, transparent);
        color: var(--success-color, #2e7d32);
      }
      .status-pill.off {
        background: color-mix(in srgb, var(--secondary-text-color) 20%, transparent);
        color: var(--secondary-text-color);
      }
      .badge-area {
        padding: 2px 10px;
        border-radius: 10px;
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        font-size: 12px;
      }
      .meta {
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      .field-label {
        display: block;
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      .conn-card select {
        width: 100%;
        padding: 8px 12px;
        border-radius: 6px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        font-size: 14px;
      }
      .btn-primary {
        padding: 10px 20px;
        border-radius: 6px;
        border: 1px solid var(--primary-color);
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
      }
      .btn-primary:hover:not([disabled]) {
        opacity: 0.9;
      }
      .btn-danger {
        padding: 10px 18px;
        border-radius: 6px;
        border: 1px solid var(--error-color);
        background: var(--error-color);
        color: #fff;
        cursor: pointer;
        font-size: 14px;
      }
      .btn-danger:hover:not([disabled]) {
        opacity: 0.9;
      }
      .btn-primary[disabled], .btn-danger[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .danger-zone {
        border: 1px dashed var(--error-color);
        border-radius: 8px;
        padding: 14px;
        margin-top: 20px;
      }
      .warning {
        background: color-mix(in srgb, var(--warning-color, #ffa726) 15%, transparent);
        border-left: 3px solid var(--warning-color, #ffa726);
        padding: 10px 14px;
        border-radius: 4px;
        font-size: 13px;
        line-height: 1.5;
      }
      p.muted {
        color: var(--secondary-text-color);
        font-size: 13px;
        line-height: 1.5;
        margin: 0 0 12px;
      }
    `;
  }

  render() {
    if (!this.deviceId) return html``;
    if (this._error) {
      return html`
        <div class="backdrop" @click=${this._onBackdropClick}>
          <div class="dialog">
            <header>
              <div class="title"><h2>Ошибка</h2></div>
              <button class="close" @click=${this._close}>×</button>
            </header>
            <div class="error">${this._error}</div>
          </div>
        </div>
      `;
    }
    if (!this._detail) {
      return html`
        <div class="backdrop" @click=${this._onBackdropClick}>
          <div class="dialog">
            <div class="body">Загрузка…</div>
          </div>
        </div>
      `;
    }
    const raw = this._detail.raw_payload || {};
    const photo = pickPhotoUrl(raw);
    const model =
      raw.device_info?.model ||
      raw.device_info?.product_id ||
      this._detail.model;
    const categories = (raw.full_categories || [])
      .map((c) => c.name)
      .filter(Boolean)
      .join(", ");

    const tabs = [
      ["connection", "Подключение"],
      ["info", "Info"],
      ["attrs", "Attributes"],
      ["images", "Images"],
      ["raw", "Raw JSON"],
    ];

    return html`
      <div class="backdrop" @click=${this._onBackdropClick}>
        <div class="dialog" @click=${(e) => e.stopPropagation()}>
          <header>
            ${photo
              ? html`<img class="photo" src=${photo} alt="" loading="lazy" />`
              : ""}
            <div class="title">
              <h2>${raw.name?.name || this._detail.name}</h2>
              <div class="subtitle">
                ${[model, categories, raw.sw_version && `v${raw.sw_version}`]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
            <button class="close" @click=${this._close} title="Закрыть">×</button>
          </header>

          <nav>
            ${tabs.map(
              ([id, label]) => html`
                <div
                  class="tab ${this._tab === id ? "active" : ""}"
                  @click=${() => (this._tab = id)}
                >
                  ${label}
                </div>
              `
            )}
          </nav>

          <div class="body">
            ${this._tab === "connection" ? this._renderConnection(raw) : ""}
            ${this._tab === "info" ? this._renderInfo(raw) : ""}
            ${this._tab === "attrs" ? this._renderAttrs(raw) : ""}
            ${this._tab === "images" ? this._renderImages(raw) : ""}
            ${this._tab === "raw" ? this._renderRaw(raw) : ""}
          </div>

          <div class="actions">
            <button
              @click=${this._refetchIndividual}
              title="GET /devices/{id} — индивидуальный fetch, bypass batch tree"
            >
              Refetch single
            </button>
            <button @click=${this._copyRaw}>Copy JSON</button>
            <button @click=${this._close}>Закрыть</button>
          </div>
        </div>
        ${this._toast ? html`<div class="toast">${this._toast}</div>` : ""}
      </div>
    `;
  }
}

customElements.define("sberhome-device-modal", SberHomeDeviceModal);
