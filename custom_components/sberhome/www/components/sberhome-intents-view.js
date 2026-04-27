/**
 * Voice Intents tab — список Sber-сценариев + create/edit/delete/test.
 *
 * Backend: websocket_api/intents.py.  Все 8 endpoints (list, get,
 * create, update, delete, test, schema, devices_for_picker).
 *
 * UX:
 * - Список с filter по name / phrase + last_fired_at column.
 * - Бейдж «sber-only» для сценариев которые мы не можем разобрать
 *   (is_ha_managed=false) — показываем read-only.
 * - Кнопка «+ New» открывает <sberhome-intent-modal>.
 * - Кликом по строке тоже открывает edit-модалку.
 */

import { LitElement, html, css } from "../lit-base.js";

class SberHomeIntentsView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _intents: { type: Array },
      _loading: { type: Boolean },
      _error: { type: String },
      _filter: { type: String },
      _editingIntent: { type: Object },
      _isCreatingNew: { type: Boolean },
    };
  }

  constructor() {
    super();
    this._intents = [];
    this._loading = false;
    this._error = "";
    this._filter = "";
    this._editingIntent = null;
    this._isCreatingNew = false;
  }

  connectedCallback() {
    super.connectedCallback();
    this._fetchAll();
    // Live-обновление last_fired_at: подписываемся на sberhome_intent
    // event-bus, чтобы по факту срабатывания фразы видеть свежий timestamp.
    // НО только когда модалка не открыта — иначе fetch'и сбрасывают
    // intent prop в parent → modal pre-fills из stale data (уже починено
    // через _draft, но shod refresh shouldn't trigger anyway).
    this._unsubIntentEvent = null;
    if (this.hass?.connection) {
      this.hass.connection
        .subscribeEvents((evt) => {
          // Skip refresh пока модалка открыта — пользователь редактирует.
          if (this._editingIntent) return;
          this._fetchAll();
        }, "sberhome_intent")
        .then((unsub) => {
          this._unsubIntentEvent = unsub;
        });
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._unsubIntentEvent) {
      this._unsubIntentEvent();
      this._unsubIntentEvent = null;
    }
  }

  async _fetchAll() {
    if (!this.hass) return;
    this._loading = true;
    try {
      const resp = await this.hass.callWS({ type: "sberhome/intents/list" });
      this._intents = resp.intents || [];
      this._error = "";
    } catch (e) {
      this._error = e.message || String(e);
    } finally {
      this._loading = false;
    }
  }

  _filtered() {
    if (!this._filter) return this._intents;
    const f = this._filter.toLowerCase();
    return this._intents.filter((it) => {
      if ((it.name || "").toLowerCase().includes(f)) return true;
      return (it.phrases || []).some((p) =>
        (p || "").toLowerCase().includes(f)
      );
    });
  }

  _onCreateNew() {
    this._isCreatingNew = true;
    this._editingIntent = {
      name: "",
      phrases: [],
      actions: [{ type: "ha_event_only", data: {} }],
      enabled: true,
    };
  }

  _onEditIntent(intent) {
    this._isCreatingNew = false;
    this._editingIntent = JSON.parse(JSON.stringify(intent));
  }

  _onCloseModal() {
    this._editingIntent = null;
    this._isCreatingNew = false;
  }

  async _onSavedIntent() {
    this._editingIntent = null;
    this._isCreatingNew = false;
    await this._fetchAll();
  }

  async _onDeleteIntent(intent) {
    if (
      !confirm(`Удалить intent «${intent.name}»? Sber-сценарий тоже удалится.`)
    )
      return;
    try {
      await this.hass.callWS({
        type: "sberhome/intents/delete",
        intent_id: intent.id,
      });
      this._toast(`Удалён: ${intent.name}`, "success");
      await this._fetchAll();
    } catch (e) {
      this._toast(`Ошибка: ${e.message || e}`, "error");
    }
  }

  async _onTestIntent(intent, e) {
    e?.stopPropagation();
    try {
      const result = await this.hass.callWS({
        type: "sberhome/intents/test",
        intent_id: intent.id,
      });
      const note =
        result?.sber_response?.note ||
        "HA event fired (Sber-side action не выполняется — произнеси фразу для real test)";
      this._toast(note, "success");
    } catch (e) {
      this._toast(`Ошибка: ${e.message || e}`, "error");
    }
  }

  _toast(message, type = "info") {
    this.dispatchEvent(
      new CustomEvent("toast", {
        detail: { message, type },
        bubbles: true,
        composed: true,
      })
    );
  }

  _formatLastFired(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffSec = Math.round((now - d) / 1000);
      if (diffSec < 60) return `${diffSec} с назад`;
      if (diffSec < 3600) return `${Math.round(diffSec / 60)} мин назад`;
      if (diffSec < 86400) return `${Math.round(diffSec / 3600)} ч назад`;
      return d.toLocaleDateString("ru-RU");
    } catch {
      return iso;
    }
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
      button.primary {
        padding: 8px 16px; border-radius: 6px;
        border: none; cursor: pointer;
        background: var(--primary-color); color: #fff;
        font-weight: 500;
      }
      button.primary:hover { opacity: 0.9; }
      .counter {
        font-size: 13px;
        color: var(--secondary-text-color);
      }
      .empty {
        text-align: center; padding: 48px 16px;
        color: var(--secondary-text-color);
      }
      .intent-list {
        display: flex; flex-direction: column; gap: 8px;
      }
      .intent-row {
        background: var(--card-background-color);
        border-radius: 8px; padding: 12px 16px;
        display: grid;
        grid-template-columns: 1fr auto auto auto;
        gap: 12px; align-items: center;
        cursor: pointer;
        transition: background 0.15s;
      }
      .intent-row:hover { background: var(--secondary-background-color); }
      .intent-row.read-only {
        opacity: 0.85;
        border-left: 3px solid var(--warning-color, #f5a623);
      }
      .intent-name {
        font-weight: 500; font-size: 15px;
        margin-bottom: 4px;
      }
      .intent-meta {
        font-size: 13px; color: var(--secondary-text-color);
        display: flex; gap: 16px; flex-wrap: wrap;
      }
      .badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 11px;
        background: var(--secondary-background-color);
      }
      .badge.disabled {
        background: var(--error-color); color: #fff;
      }
      .badge.read-only {
        background: var(--warning-color, #f5a623); color: #fff;
      }
      .badge.fired {
        background: var(--success-color, #4caf50); color: #fff;
      }
      .icon-btn {
        background: transparent; border: 1px solid var(--divider-color);
        padding: 6px 10px; border-radius: 6px; cursor: pointer;
        color: var(--primary-text-color);
        font-size: 13px;
      }
      .icon-btn:hover { background: var(--secondary-background-color); }
      .icon-btn.danger { color: var(--error-color); border-color: var(--error-color); }
      .icon-btn.danger:hover { background: var(--error-color); color: #fff; }
      .phrases {
        font-style: italic;
        color: var(--secondary-text-color);
        font-size: 13px;
      }
      .actions-summary {
        font-size: 12px;
        color: var(--secondary-text-color);
      }
    `;
  }

  render() {
    const filtered = this._filtered();
    return html`
      <div class="toolbar">
        <input
          type="search"
          placeholder="Поиск по имени или фразе…"
          .value=${this._filter}
          @input=${(e) => (this._filter = e.target.value)}
        />
        <button class="primary" @click=${this._onCreateNew}>
          + Новый intent
        </button>
        <span class="counter">
          ${filtered.length} ${filtered.length === this._intents.length ? "" : `/ ${this._intents.length}`} intent'ов
        </span>
      </div>

      ${this._error
        ? html`<div class="empty">Ошибка: ${this._error}</div>`
        : !this._intents.length && !this._loading
          ? html`
              <div class="empty">
                Sber-сценариев пока нет.<br />
                Нажми «+ Новый intent» — создадим первый.
              </div>
            `
          : html`
              <div class="intent-list">
                ${filtered.map((intent) => this._renderIntent(intent))}
              </div>
            `}

      ${this._editingIntent
        ? html`
            <sberhome-intent-modal
              .hass=${this.hass}
              .intent=${this._editingIntent}
              .isNew=${this._isCreatingNew}
              @close-intent-modal=${this._onCloseModal}
              @intent-saved=${this._onSavedIntent}
            ></sberhome-intent-modal>
          `
        : ""}
    `;
  }

  _renderIntent(intent) {
    const readOnly = !intent.is_ha_managed;
    return html`
      <div
        class="intent-row ${readOnly ? "read-only" : ""}"
        @click=${() => this._onEditIntent(intent)}
        title=${readOnly
          ? "Sber-managed — actions с типом не из HA registry, edit ограничен"
          : "Клик — редактировать"}
      >
        <div>
          <div class="intent-name">${intent.name || "(без имени)"}</div>
          <div class="phrases">
            «${(intent.phrases || []).join("», «")}»
          </div>
          <div class="intent-meta">
            <span class="actions-summary">
              ${(intent.actions || []).map((a) => a.type).join(" · ") || "no-op"}
            </span>
            ${intent.last_fired_at
              ? html`<span class="badge fired">
                  🔥 ${this._formatLastFired(intent.last_fired_at)}
                </span>`
              : ""}
            ${!intent.enabled
              ? html`<span class="badge disabled">disabled</span>`
              : ""}
            ${readOnly
              ? html`<span class="badge read-only">sber-only</span>`
              : ""}
          </div>
        </div>
        <button
          class="icon-btn"
          @click=${(e) => this._onTestIntent(intent, e)}
          title="Симулировать срабатывание (HA event)"
        >
          ▶ Test
        </button>
        <button
          class="icon-btn"
          @click=${(e) => {
            e.stopPropagation();
            this._onEditIntent(intent);
          }}
          title="Редактировать"
        >
          ✎
        </button>
        <button
          class="icon-btn danger"
          @click=${(e) => {
            e.stopPropagation();
            this._onDeleteIntent(intent);
          }}
          title="Удалить"
        >
          🗑
        </button>
      </div>
    `;
  }
}

customElements.define("sberhome-intents-view", SberHomeIntentsView);
