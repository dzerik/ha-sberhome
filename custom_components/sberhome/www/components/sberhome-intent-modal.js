/**
 * IntentModal — create/edit voice intent.
 *
 * Schema-driven форма: action_types schema получаем через
 * sberhome/intents/schema, для каждого выбранного action_type
 * рендерится свой набор полей из FieldSpec'ов.
 */

import { LitElement, html, css } from "../lit-base.js";

class SberHomeIntentModal extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      intent: { type: Object },     // initial value от parent — read-once
      isNew: { type: Boolean },
      _draft: { type: Object },     // local state — что юзер реально редактирует
      _schema: { type: Array },
      _saving: { type: Boolean },
      _error: { type: String },
      _phraseInput: { type: String },
    };
  }

  constructor() {
    super();
    this.intent = null;
    this.isNew = false;
    this._draft = null;
    this._schema = [];
    this._saving = false;
    this._error = "";
    this._phraseInput = "";
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadSchema();
  }

  willUpdate(changed) {
    // Initial copy intent prop → _draft ровно один раз при mount.
    // ВАЖНО: дальше parent может пересылать тот же или другой intent на
    // каждом re-render (например когда hass обновляется в HA), но мы
    // НЕ перезатираем _draft — иначе пользовательские правки исчезают.
    if (changed.has("intent") && this.intent && !this._draft) {
      this._draft = JSON.parse(JSON.stringify(this.intent));
    }
  }

  async _loadSchema() {
    try {
      const resp = await this.hass.callWS({
        type: "sberhome/intents/schema",
      });
      this._schema = resp.action_types || [];
    } catch (e) {
      this._error = `Schema load failed: ${e.message || e}`;
    }
  }

  _close() {
    this.dispatchEvent(
      new CustomEvent("close-intent-modal", { bubbles: true, composed: true })
    );
  }

  _onBackdropClick(e) {
    if (e.target === e.currentTarget) this._close();
  }

  _onNameChange(e) {
    this._draft = { ...this._draft, name: e.target.value };
  }

  _onAddPhrase() {
    const phrase = (this._phraseInput || "").trim();
    if (!phrase) return;
    if ((this._draft.phrases || []).includes(phrase)) {
      this._phraseInput = "";
      return;
    }
    this._draft = {
      ...this._draft,
      phrases: [...(this._draft.phrases || []), phrase],
    };
    this._phraseInput = "";
  }

  _onRemovePhrase(p) {
    this._draft = {
      ...this._draft,
      phrases: this._draft.phrases.filter((x) => x !== p),
    };
  }

  _onPhraseInputKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      this._onAddPhrase();
    }
  }

  _onActionTypeChange(idx, newType) {
    const reg = this._schema.find((s) => s.type === newType);
    const defaultData = {};
    (reg?.fields || []).forEach((f) => {
      if (f.default !== undefined) defaultData[f.key] = f.default;
      else if (f.multiple) defaultData[f.key] = [];
    });
    const newActions = this._draft.actions.map((a, i) =>
      i === idx ? { type: newType, data: defaultData, unknown: false } : a
    );
    this._draft = { ...this._draft, actions: newActions };
  }

  _onActionFieldChange(idx, fieldKey, value) {
    const newActions = this._draft.actions.map((a, i) =>
      i === idx ? { ...a, data: { ...a.data, [fieldKey]: value } } : a
    );
    this._draft = { ...this._draft, actions: newActions };
  }

  _onAddAction() {
    this._draft = {
      ...this._draft,
      actions: [
        ...(this._draft.actions || []),
        { type: "ha_event_only", data: {} },
      ],
    };
  }

  _onRemoveAction(idx) {
    this._draft = {
      ...this._draft,
      actions: this._draft.actions.filter((_, i) => i !== idx),
    };
  }

  _onEnabledToggle(e) {
    this._draft = { ...this._draft, enabled: e.target.checked };
  }

  _validate() {
    if (!(this._draft.name || "").trim()) {
      return "Имя intent'а не может быть пустым";
    }
    if (!(this._draft.phrases || []).length) {
      return "Нужна хотя бы одна голосовая фраза";
    }
    if (!(this._draft.actions || []).length) {
      return "Добавь хотя бы одно действие (ha_event_only тоже подходит)";
    }
    for (const action of this._draft.actions) {
      if (action.unknown) continue;
      const reg = this._schema.find((s) => s.type === action.type);
      if (!reg) continue;
      for (const f of reg.fields || []) {
        if (!f.required) continue;
        const v = action.data?.[f.key];
        if (v === undefined || v === null || v === "" ||
            (Array.isArray(v) && !v.length)) {
          return `Поле «${f.label}» обязательно`;
        }
      }
    }
    return null;
  }

  async _onSave() {
    const err = this._validate();
    if (err) {
      this._error = err;
      return;
    }
    this._error = "";
    this._saving = true;
    try {
      if (this.isNew) {
        await this.hass.callWS({
          type: "sberhome/intents/create",
          spec: this._draft,
        });
      } else {
        await this.hass.callWS({
          type: "sberhome/intents/update",
          intent_id: this._draft.id,
          spec: this._draft,
        });
      }
      this.dispatchEvent(
        new CustomEvent("intent-saved", { bubbles: true, composed: true })
      );
    } catch (e) {
      this._error = e.message || String(e);
    } finally {
      this._saving = false;
    }
  }

  static get styles() {
    return css`
      :host {
        position: fixed;
        inset: 0;
        z-index: 100;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .backdrop {
        position: absolute; inset: 0;
        background: rgba(0, 0, 0, 0.5);
      }
      .modal {
        position: relative;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border-radius: 12px;
        padding: 24px;
        max-width: 720px; width: 92%;
        max-height: 92vh; overflow-y: auto;
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
      }
      .header {
        display: flex; align-items: center; gap: 12px;
        margin-bottom: 16px;
      }
      .header h2 {
        margin: 0; flex: 1; font-size: 18px;
      }
      .close-btn {
        background: transparent; border: none; cursor: pointer;
        font-size: 24px; color: var(--secondary-text-color);
        padding: 0; line-height: 1;
      }
      .field {
        margin-bottom: 16px;
      }
      .field label {
        display: block; font-weight: 500; margin-bottom: 6px;
        font-size: 13px;
      }
      .field .help {
        font-size: 12px; color: var(--secondary-text-color);
        margin-top: 4px;
      }
      input[type="text"], input[type="search"], input[type="number"],
      textarea, select {
        width: 100%; box-sizing: border-box;
        padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        font-size: 14px;
        font-family: inherit;
      }
      textarea { min-height: 80px; resize: vertical; }
      .phrases-input {
        display: flex; gap: 8px; align-items: center;
      }
      .phrases-input input { flex: 1; }
      .chips {
        display: flex; gap: 8px; flex-wrap: wrap;
        margin-top: 8px;
      }
      .chip {
        background: var(--primary-color); color: #fff;
        padding: 4px 8px 4px 12px; border-radius: 14px;
        display: inline-flex; align-items: center; gap: 6px;
        font-size: 13px;
      }
      .chip button {
        background: transparent; border: none; color: inherit;
        cursor: pointer; font-size: 14px; padding: 0; line-height: 1;
        opacity: 0.85;
      }
      .chip button:hover { opacity: 1; }
      .actions-section {
        background: var(--secondary-background-color);
        padding: 12px; border-radius: 8px;
        margin-bottom: 16px;
      }
      .action-card {
        background: var(--card-background-color);
        padding: 12px; border-radius: 6px; margin-bottom: 8px;
        border: 1px solid var(--divider-color);
      }
      .action-card-header {
        display: flex; gap: 8px; align-items: center;
        margin-bottom: 12px;
      }
      .action-card-header select { flex: 1; }
      .add-btn {
        background: transparent;
        border: 1px dashed var(--divider-color);
        color: var(--primary-text-color);
        padding: 8px 12px; border-radius: 6px; cursor: pointer;
        width: 100%; font-size: 13px;
      }
      .add-btn:hover { background: var(--primary-background-color); }
      .footer {
        display: flex; justify-content: flex-end; gap: 8px;
        margin-top: 16px;
        border-top: 1px solid var(--divider-color);
        padding-top: 16px;
      }
      .btn {
        padding: 10px 18px; border-radius: 6px; cursor: pointer;
        font-size: 14px; font-weight: 500;
        border: 1px solid var(--divider-color);
        background: var(--primary-background-color);
        color: var(--primary-text-color);
      }
      .btn.primary {
        background: var(--primary-color);
        color: #fff; border-color: var(--primary-color);
      }
      .btn[disabled] { opacity: 0.5; cursor: not-allowed; }
      .error {
        background: var(--error-color); color: #fff;
        padding: 8px 12px; border-radius: 6px; margin-bottom: 12px;
        font-size: 13px;
      }
      .read-only-note {
        background: var(--warning-color, #f5a623);
        color: #fff;
        padding: 10px 12px; border-radius: 6px; margin-bottom: 16px;
        font-size: 13px;
      }
      .switch-row {
        display: flex; align-items: center; gap: 8px;
      }
    `;
  }

  render() {
    if (!this._draft) return html``;
    const readOnly = !this.isNew && !this._draft.is_ha_managed;

    return html`
      <div class="backdrop" @click=${this._onBackdropClick}></div>
      <div class="modal">
        <div class="header">
          <h2>
            ${this.isNew
              ? "Новый voice intent"
              : `Редактирование: ${this._draft.name || "(без имени)"}`}
          </h2>
          <button class="close-btn" @click=${this._close}>×</button>
        </div>

        ${readOnly
          ? html`
              <div class="read-only-note">
                Sber-managed scenario — содержит actions с типами вне
                нашего registry. Имя и фразы можно менять, actions
                сохранятся как есть (read-only).
              </div>
            `
          : ""}
        ${this._error ? html`<div class="error">${this._error}</div>` : ""}

        <!-- Имя -->
        <div class="field">
          <label>Имя intent'а</label>
          <input
            type="text"
            placeholder="Например: Утренний кофе"
            .value=${this._draft.name || ""}
            @input=${this._onNameChange}
          />
        </div>

        <!-- Phrases -->
        <div class="field">
          <label>Голосовые фразы</label>
          <div class="phrases-input">
            <input
              type="text"
              placeholder="Добавь фразу и Enter"
              .value=${this._phraseInput}
              @input=${(e) => (this._phraseInput = e.target.value)}
              @keydown=${this._onPhraseInputKeyDown}
            />
            <button class="btn" @click=${this._onAddPhrase}>+</button>
          </div>
          ${(this._draft.phrases || []).length
            ? html`
                <div class="chips">
                  ${this._draft.phrases.map(
                    (p) => html`
                      <span class="chip">
                        ${p}
                        <button @click=${() => this._onRemovePhrase(p)}>
                          ×
                        </button>
                      </span>
                    `
                  )}
                </div>
              `
            : html`<div class="help">Произнесённые в колонку — будут триггерить intent.</div>`}
        </div>

        <!-- Enabled -->
        <div class="field switch-row">
          <input
            type="checkbox"
            id="enabled"
            .checked=${this._draft.enabled !== false}
            @change=${this._onEnabledToggle}
          />
          <label for="enabled" style="margin: 0;">Активен в Sber</label>
        </div>

        <!-- Actions -->
        <div class="field">
          <label>Действия</label>
          <div class="actions-section">
            ${(this._draft.actions || []).map((action, idx) =>
              this._renderAction(action, idx, readOnly)
            )}
            ${!readOnly
              ? html`
                  <button class="add-btn" @click=${this._onAddAction}>
                    + добавить действие
                  </button>
                `
              : ""}
          </div>
        </div>

        <div class="footer">
          <button class="btn" @click=${this._close}>Отмена</button>
          <button
            class="btn primary"
            @click=${this._onSave}
            ?disabled=${this._saving}
          >
            ${this._saving ? "Сохранение…" : this.isNew ? "Создать" : "Сохранить"}
          </button>
        </div>
      </div>
    `;
  }

  _renderAction(action, idx, parentReadOnly) {
    if (action.unknown) {
      return html`
        <div class="action-card">
          <div class="action-card-header">
            <strong>${action.type}</strong>
            <span class="help" style="flex: 1; margin: 0;">
              Sber-action не из HA registry — read-only
            </span>
          </div>
        </div>
      `;
    }

    const reg = this._schema.find((s) => s.type === action.type);
    return html`
      <div class="action-card">
        <div class="action-card-header">
          <select
            .value=${action.type}
            @change=${(e) => this._onActionTypeChange(idx, e.target.value)}
            ?disabled=${parentReadOnly}
          >
            ${this._schema.map(
              (s) => html`
                <option value=${s.type} ?selected=${s.type === action.type}>
                  ${s.ui_label}
                </option>
              `
            )}
          </select>
          ${!parentReadOnly && this._draft.actions.length > 1
            ? html`
                <button
                  class="btn"
                  style="padding: 4px 10px;"
                  @click=${() => this._onRemoveAction(idx)}
                  title="Удалить это действие"
                >
                  ×
                </button>
              `
            : ""}
        </div>
        ${(reg?.fields || []).map((field) =>
          this._renderField(idx, action, field, parentReadOnly)
        )}
      </div>
    `;
  }

  _renderField(actionIdx, action, field, readOnly) {
    const value = action.data?.[field.key];

    return html`
      <div class="field">
        <label>
          ${field.label}${field.required ? " *" : ""}
        </label>
        ${this._renderInputForType(actionIdx, field, value, readOnly)}
        ${field.help_text
          ? html`<div class="help">${field.help_text}</div>`
          : ""}
      </div>
    `;
  }

  _renderInputForType(actionIdx, field, value, readOnly) {
    const onChange = (newValue) =>
      this._onActionFieldChange(actionIdx, field.key, newValue);

    switch (field.type) {
      case "text":
        return html`
          <input
            type="text"
            .value=${value || ""}
            ?disabled=${readOnly}
            @input=${(e) => onChange(e.target.value)}
          />
        `;
      case "number":
        return html`
          <input
            type="number"
            .value=${value ?? ""}
            ?disabled=${readOnly}
            @input=${(e) => onChange(parseFloat(e.target.value) || 0)}
          />
        `;
      case "bool":
        return html`
          <input
            type="checkbox"
            .checked=${!!value}
            ?disabled=${readOnly}
            @change=${(e) => onChange(e.target.checked)}
          />
        `;
      case "enum":
        return html`
          <select
            ?disabled=${readOnly}
            @change=${(e) => onChange(e.target.value)}
          >
            ${(field.options || []).map(
              (opt) => html`
                <option value=${opt} ?selected=${opt === value}>${opt}</option>
              `
            )}
          </select>
        `;
      case "multitext":
        return html`
          <textarea
            ?disabled=${readOnly}
            @input=${(e) => {
              try {
                onChange(JSON.parse(e.target.value));
              } catch {
                // невалидный JSON — игнорим до первого валидного
              }
            }}
          >${typeof value === "string"
            ? value
            : JSON.stringify(value || [], null, 2)}</textarea>
        `;
      case "device_picker":
        return html`
          <sberhome-device-picker-field
            .hass=${this.hass}
            .field=${field}
            .value=${value}
            ?disabled=${readOnly}
            @value-changed=${(e) => onChange(e.detail.value)}
          ></sberhome-device-picker-field>
        `;
      default:
        return html`
          <em>Unsupported field type: ${field.type}</em>
        `;
    }
  }
}

customElements.define("sberhome-intent-modal", SberHomeIntentModal);


/**
 * Device picker field — отдельный компонент, дёргает
 * sberhome/intents/devices_for_picker и рендерит select(s).
 */
class SberHomeDevicePickerField extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      field: { type: Object },
      value: {},
      disabled: { type: Boolean },
      _devices: { type: Array },
    };
  }

  constructor() {
    super();
    this._devices = [];
  }

  connectedCallback() {
    super.connectedCallback();
    this._fetch();
  }

  async _fetch() {
    try {
      const params = { type: "sberhome/intents/devices_for_picker" };
      if (this.field?.device_category?.length) {
        params.category = this.field.device_category;
      }
      const resp = await this.hass.callWS(params);
      this._devices = resp.devices || [];
    } catch (e) {
      console.warn("device picker fetch failed", e);
    }
  }

  _onChange(deviceId, checked) {
    if (this.field.multiple) {
      const current = Array.isArray(this.value) ? this.value : [];
      const next = checked
        ? [...current, deviceId]
        : current.filter((x) => x !== deviceId);
      this.dispatchEvent(
        new CustomEvent("value-changed", { detail: { value: next } })
      );
    } else {
      this.dispatchEvent(
        new CustomEvent("value-changed", { detail: { value: deviceId } })
      );
    }
  }

  static get styles() {
    return css`
      :host { display: block; }
      .device-list {
        max-height: 240px; overflow-y: auto;
        border: 1px solid var(--divider-color);
        border-radius: 6px;
        background: var(--primary-background-color);
      }
      .device-row {
        display: flex; align-items: center; gap: 8px;
        padding: 8px 12px;
        border-bottom: 1px solid var(--divider-color);
        font-size: 13px;
      }
      .device-row:last-child { border-bottom: none; }
      .device-row label {
        flex: 1; cursor: pointer; margin: 0;
        font-weight: normal; font-size: 13px;
      }
      .device-meta {
        font-size: 11px; color: var(--secondary-text-color);
      }
      .empty {
        padding: 12px; text-align: center;
        color: var(--secondary-text-color); font-size: 13px;
      }
    `;
  }

  render() {
    if (!this._devices.length) {
      return html`
        <div class="empty">
          ${this.field?.device_category?.length
            ? `Нет устройств категории «${this.field.device_category.join(", ")}»`
            : "Нет устройств"}
        </div>
      `;
    }
    const isChecked = (id) =>
      this.field.multiple
        ? Array.isArray(this.value) && this.value.includes(id)
        : this.value === id;
    const inputType = this.field.multiple ? "checkbox" : "radio";

    return html`
      <div class="device-list">
        ${this._devices.map(
          (d) => html`
            <div class="device-row">
              <input
                type=${inputType}
                name="dp-${this.field.key}"
                id="dp-${this.field.key}-${d.device_id}"
                ?disabled=${this.disabled}
                .checked=${isChecked(d.device_id)}
                @change=${(e) => this._onChange(d.device_id, e.target.checked)}
              />
              <label for="dp-${this.field.key}-${d.device_id}">
                ${d.name}
                <div class="device-meta">
                  ${d.category} · ${d.model || "—"}
                  ${d.room ? html` · ${d.room}` : ""}
                </div>
              </label>
            </div>
          `
        )}
      </div>
    `;
  }
}

customElements.define(
  "sberhome-device-picker-field",
  SberHomeDevicePickerField
);
