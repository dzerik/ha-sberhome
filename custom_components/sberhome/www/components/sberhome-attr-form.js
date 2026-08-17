/**
 * sberhome-attr-form — форма желаемого состояния устройства ПО ЕГО СХЕМЕ.
 *
 * Вместо ручного JSON: выбираешь атрибуты и значения виджетами, которые
 * генерируются из возможностей устройства (WS `sberhome/device_write_schema`):
 *   BOOL → toggle · INTEGER/FLOAT+range → slider · ENUM → dropdown · COLOR → (скоро)
 *
 * Переиспользуется в визардах «команда устройству» (действие) и «условие по
 * устройству» (триггер). Наружу отдаёт `attributes` — плоский список
 * AttributeValue [{key, type, <value_field>}], который encoder оборачивает в
 * канонический desired_state.
 *
 * Контракт:
 *   <sberhome-attr-form
 *     .hass=${hass} .deviceId=${id} .value=${attributes}
 *     @attributes-change=${(e) => (attrs = e.detail.attributes)}>
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";

export class SberhomeAttrForm extends LitElement {
  static get properties() {
    return {
      hass: { attribute: false },
      deviceId: { attribute: false },
      value: { attribute: false }, // [{key, type, bool_value|integer_value|...}]
      _fields: { state: true },
      _loading: { state: true },
    };
  }

  static get styles() {
    return [css`
      :host { display: block; }
      .hint { color: var(--secondary-text-color, #888); font-size: 13px; padding: 6px 0; }
      .attr-row {
        display: flex; align-items: center; gap: 10px;
        padding: 6px 0; border-bottom: 1px solid var(--divider-color, #eee);
      }
      .attr-head {
        display: flex; align-items: center; gap: 8px;
        min-width: 46%; cursor: pointer; font-size: 13px;
      }
      .attr-row:not(.on) .attr-head { color: var(--secondary-text-color, #999); }
      .widget { flex: 1; display: flex; align-items: center; gap: 8px; }
      .widget input[type="range"] { flex: 1; }
      .widget select, .widget input[type="number"] { flex: 1; }
      .val { min-width: 54px; text-align: right; font-variant-numeric: tabular-nums; font-size: 12px; }
    `, mobileBase];
  }

  constructor() {
    super();
    this.value = [];
    this._fields = [];
    this._loading = false;
    this._loadedFor = null;
  }

  updated(changed) {
    if (changed.has("deviceId") && this.deviceId && this.deviceId !== this._loadedFor) {
      this._loadedFor = this.deviceId;
      this._fetchSchema();
    }
  }

  async _fetchSchema() {
    this._loading = true;
    try {
      const r = await this.hass.callWS({
        type: "sberhome/device_write_schema",
        device_id: this.deviceId,
      });
      this._fields = r?.fields || [];
    } catch (_e) {
      this._fields = [];
    }
    this._loading = false;
  }

  _cur(key) {
    return (this.value || []).find((a) => a.key === key) || null;
  }

  _emit(next) {
    this.value = next;
    this.dispatchEvent(
      new CustomEvent("attributes-change", {
        detail: { attributes: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  _toggle(field, on) {
    let next = (this.value || []).filter((a) => a.key !== field.key);
    if (on) next = [...next, this._defaultAttr(field)];
    this._emit(next);
  }

  _set(field, raw) {
    const attr = this._buildAttr(field, raw);
    this._emit([...(this.value || []).filter((a) => a.key !== field.key), attr]);
  }

  _defaultAttr(field) {
    const c = field.current;
    switch (field.type) {
      case "BOOL":
        return { key: field.key, type: "BOOL", bool_value: !!c };
      case "INTEGER":
        return { key: field.key, type: "INTEGER", integer_value: String(c ?? field.range?.min ?? 0) };
      case "FLOAT":
        return { key: field.key, type: "FLOAT", float_value: Number(c ?? field.frange?.min ?? 0) };
      case "ENUM":
        return { key: field.key, type: "ENUM", enum_value: String(c ?? field.enum?.[0] ?? "") };
      default:
        return { key: field.key, type: field.type };
    }
  }

  _buildAttr(field, v) {
    switch (field.type) {
      case "BOOL":
        return { key: field.key, type: "BOOL", bool_value: !!v };
      case "INTEGER":
        return { key: field.key, type: "INTEGER", integer_value: String(Math.round(Number(v) || 0)) };
      case "FLOAT":
        return { key: field.key, type: "FLOAT", float_value: Number(v) || 0 };
      case "ENUM":
        return { key: field.key, type: "ENUM", enum_value: String(v) };
      default:
        return { key: field.key, type: field.type };
    }
  }

  _unit(field) {
    // Юниты у Сбера часто числовые коды ("32") — показываем только буквенные.
    const u = field.unit;
    return u && isNaN(u) ? " " + u : "";
  }

  render() {
    if (!this.deviceId) return html`<div class="hint">Сначала выберите устройство</div>`;
    if (this._loading) return html`<div class="hint">Загрузка возможностей устройства…</div>`;
    if (!this._fields.length) return html`<div class="hint">У устройства нет управляемых атрибутов</div>`;
    return html`${this._fields.map((f) => this._renderField(f))}`;
  }

  _renderField(field) {
    const on = !!this._cur(field.key);
    return html`
      <div class="attr-row ${on ? "on" : ""}">
        <label class="attr-head">
          <input
            type="checkbox"
            .checked=${on}
            @change=${(e) => this._toggle(field, e.target.checked)}
          />
          <span>${field.key}</span>
        </label>
        ${on ? html`<div class="widget">${this._renderWidget(field)}</div>` : ""}
      </div>
    `;
  }

  _renderWidget(field) {
    const cur = this._cur(field.key);
    switch (field.type) {
      case "BOOL":
        return html`<input
          type="checkbox"
          .checked=${cur?.bool_value ?? false}
          @change=${(e) => this._set(field, e.target.checked)}
        />`;
      case "INTEGER":
      case "FLOAT": {
        const isInt = field.type === "INTEGER";
        const range = isInt ? field.range : field.frange;
        const v = isInt ? Number(cur?.integer_value ?? 0) : Number(cur?.float_value ?? 0);
        if (range) {
          return html`
            <input
              type="range"
              min=${range.min}
              max=${range.max}
              step=${range.step || (isInt ? 1 : 0.1)}
              .value=${v}
              @input=${(e) => this._set(field, e.target.value)}
            />
            <span class="val">${v}${this._unit(field)}</span>
          `;
        }
        return html`<input
          type="number"
          .value=${v}
          @input=${(e) => this._set(field, e.target.value)}
        />`;
      }
      case "ENUM": {
        const v = cur?.enum_value ?? field.enum?.[0] ?? "";
        return html`<select @change=${(e) => this._set(field, e.target.value)}>
          ${(field.enum || []).map(
            (o) => html`<option value=${o} ?selected=${o === v}>${o}</option>`,
          )}
        </select>`;
      }
      case "COLOR":
        return html`<span class="hint">цвет — скоро</span>`;
      default:
        return html`<span class="hint">${field.type}</span>`;
    }
  }
}

customElements.define("sberhome-attr-form", SberhomeAttrForm);
