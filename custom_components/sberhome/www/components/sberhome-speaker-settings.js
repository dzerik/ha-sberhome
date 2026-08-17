/**
 * Speaker settings — настройки одной колонки Сбер (/v18): эквалайзер,
 * светомузыка, LED, детские режимы. Переиспользуется в модалке устройства
 * (таб «🔊 Звук»).
 *
 * Источник — WS `sberhome/staros/list` (список колонок + specs по serial).
 * Управление — через штатные HA-сущности (в specs есть `entity_id`).
 *
 * Контракт: <sberhome-speaker-settings .hass=${hass} .serial=${serial}>
 * Если serial не задан — показывает все колонки (обзор).
 */

import { LitElement, css, html } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";

export class SberhomeSpeakerSettings extends LitElement {
  static get properties() {
    return {
      hass: { attribute: false },
      serial: { attribute: false }, // фильтр по одной колонке; null = все
      _data: { state: true },
      _loading: { state: true },
    };
  }

  constructor() {
    super();
    this.serial = null;
    this._data = null;
    this._loading = true;
  }

  connectedCallback() {
    super.connectedCallback();
    this._load();
  }

  async _load() {
    this._loading = true;
    try {
      this._data = await this.hass.callWS({ type: "sberhome/staros/list" });
    } catch (err) {
      console.error("Failed to load sberhome staros settings", err);
      this._data = null;
    } finally {
      this._loading = false;
    }
  }

  async _refresh() {
    this._loading = true;
    try {
      await this.hass.callWS({ type: "sberhome/force_refresh" });
    } catch (err) {
      console.error("Failed to force refresh", err);
    }
    await this._load();
  }

  _toggle(entityId, state) {
    if (!entityId) return;
    this.hass.callService("switch", state === "on" ? "turn_off" : "turn_on", {
      entity_id: entityId,
    });
    setTimeout(() => this._load(), 400);
  }

  _select(entityId, option) {
    if (!entityId) return;
    this.hass.callService("select", "select_option", { entity_id: entityId, option });
    setTimeout(() => this._load(), 400);
  }

  _setNumber(entityId, value) {
    if (!entityId) return;
    this.hass.callService("number", "set_value", { entity_id: entityId, value });
    setTimeout(() => this._load(), 400);
  }

  _fmtFreq(hz) {
    if (hz == null) return "";
    return hz >= 1000 ? `${(hz / 1000).toFixed(hz % 1000 ? 1 : 0)}k` : `${hz}`;
  }

  render() {
    const toolbar = html`
      <div class="toolbar">
        <button class="refresh" @click=${this._refresh} ?disabled=${this._loading}>
          ↻ Обновить
        </button>
        <span class="hint-inline">Правки из приложения Сбера подтягиваются
          по «Обновить», по событию от колонки и раз в 10 минут.</span>
      </div>
    `;
    if (this._loading && !this._data) return html`${toolbar}<p>Загрузка…</p>`;
    const data = this._data;
    if (!data || !data.speaker_present) {
      return html`${toolbar}<div class="empty"><p>Колонки Сбер не обнаружены.</p></div>`;
    }
    if (!data.available) {
      return html`${toolbar}
        <div class="empty warn">
          <p>Колонка есть, но канал настроек недоступен.</p>
          <p>Похоже, вход выполнен по SMS. Переавторизуйтесь через Сбер ID,
            чтобы управлять настройками и эквалайзером.</p>
        </div>`;
    }
    let devices = data.devices || [];
    if (this.serial) devices = devices.filter((d) => d.serial === this.serial);
    if (!devices.length) {
      return html`${toolbar}<div class="empty"><p>Нет данных настроек колонки.</p></div>`;
    }
    return html`
      ${toolbar}
      <div class="wrap">
        ${devices.map((d) => this._renderDevice(d, data.settings?.[d.serial] || []))}
      </div>
    `;
  }

  _renderDevice(device, specs) {
    const eq = specs.filter((s) => s.eq_group);
    const enabled = eq.find((s) => s.eq_role === "enabled");
    const preset = eq.find((s) => s.eq_role === "preset");
    const bands = eq
      .filter((s) => s.eq_role === "band")
      .sort((a, b) => (a.eq_band_index ?? 0) - (b.eq_band_index ?? 0));
    const others = specs.filter(
      (s) =>
        !s.eq_group &&
        !(s.platform === "select" && (!s.options || s.options.length === 0)),
    );
    return html`
      <div class="card">
        ${this.serial
          ? ""
          : html`<div class="card-header">
              <span class="name">${device.name || device.product || "Колонка"}</span>
              <span class="slug">${device.serial}</span>
            </div>`}

        ${eq.length
          ? html`
              <div class="section">
                <div class="section-title">Эквалайзер</div>
                ${enabled
                  ? html`<div class="row">
                      <span>Включён</span>
                      <button
                        class="pill ${enabled.state === "on" ? "on" : ""}"
                        @click=${() => this._toggle(enabled.entity_id, enabled.state)}
                      >
                        ${enabled.state === "on" ? "вкл" : "выкл"}
                      </button>
                    </div>`
                  : ""}
                ${preset
                  ? html`<div class="chips">
                      ${(preset.options || []).map(
                        (opt) => html`<button
                          class="chip ${opt === preset.state ? "active" : ""}"
                          @click=${() => this._select(preset.entity_id, opt)}
                        >
                          ${opt}
                        </button>`,
                      )}
                    </div>`
                  : ""}
                ${bands.length ? this._renderEq(bands) : ""}
              </div>
            `
          : ""}

        ${others.length
          ? html`<div class="section">
              <div class="section-title">Настройки</div>
              ${others.map((s) => this._renderOther(s))}
            </div>`
          : ""}
      </div>
    `;
  }

  // Визуальный эквалайзер: вертикальные ползунки по полосам, нулевая линия
  // по центру. Интерактивны, если у полосы есть number-сущность.
  _renderEq(bands) {
    const min = bands[0]?.min ?? -6;
    const max = bands[0]?.max ?? 6;
    return html`
      <div class="eq">
        <div class="eq-axis"><span>+${max}</span><span>0</span><span>${min}</span></div>
        <div class="eq-lanes">
          <div class="eq-zero"></div>
          ${bands.map((b) => {
            const editable = b.entity_id && b.platform === "number";
            const cls = b.state > 0 ? "pos" : b.state < 0 ? "neg" : "";
            return html`<div class="eq-col">
              <span class="eq-gain ${cls}">${b.state > 0 ? "+" : ""}${b.state}</span>
              <input
                class="eq-slider"
                type="range"
                .min=${min}
                .max=${max}
                .step=${b.step ?? 1}
                .value=${String(b.state)}
                ?disabled=${!editable}
                @change=${(e) => this._setNumber(b.entity_id, Number(e.target.value))}
              />
              <span class="eq-freq">${this._fmtFreq(b.eq_frequency)}</span>
            </div>`;
          })}
        </div>
      </div>
    `;
  }

  _renderOther(spec) {
    if (spec.platform === "switch") {
      return html`<div class="row">
        <span>${spec.name}</span>
        <button
          class="pill ${spec.state === "on" ? "on" : ""}"
          @click=${() => this._toggle(spec.entity_id, spec.state)}
        >
          ${spec.state === "on" ? "вкл" : "выкл"}
        </button>
      </div>`;
    }
    if (spec.platform === "select") {
      const titles = spec.option_titles || {};
      return html`<div class="row">
        <span>${spec.name}</span>
        <select @change=${(e) => this._select(spec.entity_id, e.target.value)}>
          ${(spec.options || []).map(
            (opt) => html`<option value=${opt} ?selected=${opt === spec.state}>
              ${titles[opt] || opt}
            </option>`,
          )}
        </select>
      </div>`;
    }
    if (spec.platform === "number") {
      return html`<div class="row">
        <span>${spec.name}</span>
        <div class="numctl">
          <input
            type="range"
            .min=${spec.min ?? 0}
            .max=${spec.max ?? 100}
            .step=${spec.step ?? 1}
            .value=${String(spec.state)}
            @change=${(e) => this._setNumber(spec.entity_id, Number(e.target.value))}
          />
          <span class="val">${spec.state}${spec.unit ? " " + spec.unit : ""}</span>
        </div>
      </div>`;
    }
    return html`<div class="row">
      <span>${spec.name}</span>
      <span class="val">${spec.state}${spec.unit ? " " + spec.unit : ""}</span>
    </div>`;
  }

  static get styles() {
    return [
      css`
        :host { display: block; }
        .wrap { display: flex; flex-direction: column; gap: 12px; }
        .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
        .refresh {
          padding: 6px 14px; font-size: 13px; border: 1px solid var(--divider-color, #ccc);
          border-radius: 6px; background: var(--card-background-color, white);
          color: var(--primary-text-color); cursor: pointer;
        }
        .refresh:disabled { opacity: 0.5; cursor: default; }
        .hint-inline { font-size: 11px; color: var(--secondary-text-color, #888); }
        .card {
          padding: 14px; border: 1px solid var(--divider-color, #ddd);
          border-radius: 8px; background: var(--card-background-color, white);
        }
        .card-header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 8px; }
        .name { font-weight: 600; font-size: 15px; }
        .slug { font-family: ui-monospace, "Cascadia Code", monospace; font-size: 11px; color: var(--secondary-text-color, #666); }
        .section { margin-top: 12px; }
        .section:first-of-type { margin-top: 0; }
        .section-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--secondary-text-color, #888); margin-bottom: 6px; }
        .row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 6px 0; font-size: 14px; border-top: 1px solid var(--divider-color, #eee); }
        .row:first-of-type { border-top: none; }
        .val { color: var(--secondary-text-color, #666); font-variant-numeric: tabular-nums; }
        .numctl { display: flex; align-items: center; gap: 10px; }
        .numctl input[type="range"] { width: 130px; accent-color: var(--primary-color, #03a9f4); }
        .pill { border: 1px solid var(--divider-color, #ccc); background: var(--secondary-background-color, #f0f0f0); color: var(--secondary-text-color, #666); border-radius: 999px; padding: 4px 14px; font-size: 12px; cursor: pointer; }
        .pill.on { background: var(--primary-color, #03a9f4); border-color: var(--primary-color, #03a9f4); color: #fff; }
        .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
        .chip { border: 1px solid var(--divider-color, #ccc); background: transparent; color: var(--secondary-text-color, #666); border-radius: 999px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
        .chip.active { background: var(--primary-color, #03a9f4); border-color: var(--primary-color, #03a9f4); color: #fff; }
        /* Визуальный эквалайзер */
        .eq { display: flex; gap: 8px; margin-top: 12px; }
        .eq-axis {
          display: flex; flex-direction: column; justify-content: space-between;
          font-size: 9px; color: var(--secondary-text-color, #999);
          padding: 16px 0 14px; text-align: right; min-width: 20px;
        }
        .eq-lanes {
          position: relative; flex: 1; display: flex; justify-content: space-between;
          gap: 4px; align-items: stretch;
        }
        /* Нулевая линия по центру полос (симметричный ±диапазон) */
        .eq-zero {
          position: absolute; left: 0; right: 0; top: 50%;
          border-top: 1px dashed var(--divider-color, #ccc); pointer-events: none;
        }
        .eq-col { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; min-width: 0; }
        .eq-gain { font-size: 11px; font-variant-numeric: tabular-nums; height: 12px; }
        .eq-gain.pos { color: var(--success-color, #2e7d32); }
        .eq-gain.neg { color: var(--error-color, #c62828); }
        .eq-slider {
          writing-mode: vertical-lr; direction: rtl;   /* стандартный вертикальный слайдер */
          width: 10px; height: 96px; accent-color: var(--primary-color, #03a9f4);
          cursor: pointer;
        }
        .eq-slider:disabled { cursor: default; opacity: 0.7; }
        .eq-freq { font-size: 9px; color: var(--secondary-text-color, #999); white-space: nowrap; }
        select { padding: 5px 8px; font-size: 13px; border: 1px solid var(--divider-color, #ccc); border-radius: 6px; background: var(--card-background-color, white); color: var(--primary-text-color); }
        .empty { padding: 24px; text-align: center; color: var(--secondary-text-color, #888); border: 1px dashed var(--divider-color, #ddd); border-radius: 8px; }
        .empty.warn { border-color: var(--warning-color, #e5a000); color: var(--primary-text-color); }
      `,
      mobileBase,
    ];
  }
}

if (!customElements.get("sberhome-speaker-settings")) {
  customElements.define("sberhome-speaker-settings", SberhomeSpeakerSettings);
}
