/**
 * SberHome — Settings tab.
 *
 * Поля строятся по ответу `sberhome/get_settings`: значения, умолчания и
 * границы приходят с бэкенда, поэтому форма не держит свою копию
 * диапазонов (раньше она разошлась с формой параметров — 3600 против 300).
 * Сохранение применяется без перезагрузки интеграции.
 *
 * Здесь же экспорт и импорт конфигурации: выбор устройств (стабильными
 * ключами) и настройки одним JSON-файлом.
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";
import { Localized } from "../i18n/index.js";

/** Поля формы в порядке показа; шаг ввода — единственное, что знает панель. */
export const FIELDS = [
  { key: "scan_interval", step: 1 },
  { key: "devtools_buffer_size", step: 10 },
  { key: "command_timeout", step: 1 },
];

export class SberHomeSettings extends Localized(LitElement) {
  static get properties() {
    return {
      hass: { type: Object },
      _settings: { state: true },
      _defaults: { state: true },
      _limits: { state: true },
      _dirty: { state: true },
      _busy: { state: true },
    };
  }

  constructor() {
    super();
    this._settings = null;
    this._defaults = {};
    this._limits = {};
    this._dirty = false;
    this._busy = false;
  }

  connectedCallback() {
    super.connectedCallback();
    if (this.hass && !this._settings) this._load();
  }

  updated(changed) {
    if (changed.has("hass") && this.hass && !this._settings && !this._busy) this._load();
  }

  async _load() {
    this._busy = true;
    try {
      const res = await this.hass.callWS({ type: "sberhome/get_settings" });
      this._settings = { ...res.settings };
      this._defaults = res.defaults || {};
      this._limits = res.limits || {};
      this._dirty = false;
    } catch (e) {
      this._toast(this.t("settings.load_failed", { error: e.message || e }), "error");
    } finally {
      this._busy = false;
    }
  }

  _toast(message, type = "info") {
    this.dispatchEvent(new CustomEvent("toast", { detail: { message, type }, bubbles: true, composed: true }));
  }

  _onInput(key, raw) {
    this._settings = { ...this._settings, [key]: raw === "" ? "" : Number(raw) };
    this._dirty = true;
  }

  /** Поля вне границ — сохранять их бессмысленно, бэкенд отклонит запрос. */
  _invalidKeys() {
    return FIELDS.map((f) => f.key).filter((key) => {
      const value = this._settings?.[key];
      const limits = this._limits[key];
      if (typeof value !== "number" || Number.isNaN(value)) return true;
      return limits ? value < limits.min || value > limits.max : false;
    });
  }

  async _save() {
    this._busy = true;
    try {
      await this.hass.callWS({ type: "sberhome/update_settings", settings: this._settings });
      this._dirty = false;
      this._toast(this.t("settings.saved"), "success");
    } catch (e) {
      this._toast(this.t("settings.save_failed", { error: e.message || e }), "error");
    } finally {
      this._busy = false;
    }
  }

  _resetDefaults() {
    this._settings = { ...this._settings, ...this._defaults };
    this._dirty = true;
  }

  async _refresh() {
    await this.hass.callWS({ type: "sberhome/force_refresh" });
    this._toast(this.t("settings.refresh_requested"), "info");
  }

  async _export() {
    try {
      const config = await this.hass.callWS({ type: "sberhome/export_config" });
      const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "sberhome_config.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      this._toast(this.t("settings.export_failed", { error: e.message || e }), "error");
    }
  }

  async _import(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    let config;
    try {
      config = JSON.parse(await file.text());
    } catch {
      this._toast(this.t("settings.import_not_json"), "error");
      return;
    }
    this._busy = true;
    try {
      const res = await this.hass.callWS({ type: "sberhome/import_config", config });
      this._toast(this.t("settings.imported", { n: res.devices }), "success");
    } catch (e) {
      this._toast(this.t("settings.import_failed", { error: e.message || e }), "error");
      this._busy = false;
      return;
    }
    /* The import reloads the entry before answering — re-read what it stored. */
    this._busy = false;
    await this._load();
  }

  static get styles() {
    return [css`
      :host { display: block; padding: 16px; max-width: 560px; }
      .field { margin-bottom: 16px; }
      label { display: block; margin-bottom: 4px; color: var(--primary-text-color); font-size: 14px; }
      .hint { color: var(--secondary-text-color); font-size: 12px; margin-top: 4px; }
      input[type="number"] {
        box-sizing: border-box;
        padding: 8px 12px;
        border-radius: 6px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        width: 100%;
      }
      input[aria-invalid="true"] { border-color: var(--error-color, #f44336); }
      .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
      button, .file-label {
        padding: 10px 20px;
        border-radius: 6px;
        background: var(--primary-color);
        color: #fff;
        border: none;
        cursor: pointer;
        font-size: 14px;
      }
      button:disabled { opacity: 0.5; cursor: default; }
      button.secondary, .file-label {
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
      }
      button:focus-visible, .file-label:focus-within { outline: 2px solid var(--primary-color); outline-offset: 2px; }
      h3 { margin: 0 0 8px; font-size: 15px; }
      .file-label input { position: absolute; width: 1px; height: 1px; opacity: 0; }
    `, mobileBase];
  }

  render() {
    if (!this._settings) return html`<div>${this.t("status.loading")}</div>`;
    const invalid = this._invalidKeys();
    return html`
      ${FIELDS.map((f) => {
        const limits = this._limits[f.key] || {};
        const id = `field-${f.key}`;
        return html`<div class="field">
          <label for=${id}>${this.t(`settings.field.${f.key}`)}</label>
          <input id=${id} type="number" min=${limits.min} max=${limits.max} step=${f.step}
            aria-invalid=${invalid.includes(f.key) ? "true" : "false"}
            .value=${String(this._settings[f.key] ?? "")}
            @input=${(e) => this._onInput(f.key, e.target.value)}>
          <div class="hint">${this.t(`settings.hint.${f.key}`, limits)}</div>
        </div>`;
      })}
      <div class="actions">
        <button @click=${this._save} ?disabled=${!this._dirty || this._busy || invalid.length > 0}>
          ${this.t("settings.save")}
        </button>
        <button class="secondary" @click=${this._resetDefaults} ?disabled=${this._busy}>${this.t("settings.reset")}</button>
        <button class="secondary" @click=${this._refresh}>${this.t("settings.refresh")}</button>
      </div>
      <h3>${this.t("settings.backup")}</h3>
      <div class="hint" style="margin-bottom:8px">${this.t("settings.backup_hint")}</div>
      <div class="actions">
        <button class="secondary" @click=${this._export}>${this.t("settings.export")}</button>
        <label class="file-label">
          ${this.t("settings.import")}
          <input type="file" accept="application/json,.json" @change=${this._import} ?disabled=${this._busy}>
        </label>
      </div>
    `;
  }
}

customElements.define("sberhome-settings", SberHomeSettings);
