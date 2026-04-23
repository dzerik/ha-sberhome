/**
 * SberHome — Live WS message log (last 100, real-time via subscribe).
 *
 * Каждое сообщение рендерится отдельной карточкой с коротким заголовком
 * (timestamp + topic + device_id) и развёрткой по клику — полный JSON +
 * кнопка "Copy" для копирования в буфер обмена.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

async function copyJson(obj) {
  const text = JSON.stringify(obj, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  }
}

class SberHomeLogView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _messages: { type: Array },
      _expanded: { type: Object },
      _toast: { type: String },
      _filter: { type: String },
      _directionFilter: { type: String },
    };
  }

  constructor() {
    super();
    this._messages = [];
    this._unsub = null;
    this._expanded = {}; // index → bool
    this._toast = "";
    this._filter = ""; // topic filter (DEVICE_STATE / COMMAND / …)
    this._directionFilter = "all"; // all / in / out
  }

  _filtered() {
    return this._messages.filter((m) => {
      if (this._directionFilter !== "all" && (m.direction || "in") !== this._directionFilter) {
        return false;
      }
      if (this._filter && !(m.topic || "").includes(this._filter)) {
        return false;
      }
      return true;
    });
  }

  _uniqueTopics() {
    return [...new Set(this._messages.map((m) => m.topic).filter(Boolean))].sort();
  }

  async connectedCallback() {
    super.connectedCallback();
    if (!this.hass) return;
    this._unsub = await this.hass.connection.subscribeMessage(
      (event) => {
        if (event.snapshot) {
          this._messages = event.snapshot;
        } else if (event.message) {
          this._messages = [event.message, ...this._messages].slice(0, 100);
        }
      },
      { type: "sberhome/subscribe_messages" }
    );
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._unsub) {
      this._unsub();
      this._unsub = null;
    }
  }

  async _clear() {
    await this.hass.callWS({ type: "sberhome/clear_message_log" });
    this._messages = [];
    this._expanded = {};
  }

  _toggle(idx) {
    this._expanded = { ...this._expanded, [idx]: !this._expanded[idx] };
  }

  async _copy(msg) {
    await copyJson(msg);
    this._toast = "Сообщение скопировано";
    setTimeout(() => {
      this._toast = "";
    }, 2000);
  }

  async _copyAll() {
    await copyJson(this._messages);
    this._toast = `Скопировано ${this._messages.length} сообщений`;
    setTimeout(() => {
      this._toast = "";
    }, 2000);
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      .toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        gap: 8px;
      }
      .toolbar-buttons {
        display: flex;
        gap: 8px;
      }
      button {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        cursor: pointer;
        color: var(--primary-text-color);
        font-size: 12px;
      }
      button:hover {
        background: var(--secondary-background-color);
      }
      .msg {
        border: 1px solid var(--divider-color);
        border-radius: 6px;
        margin-bottom: 6px;
        background: var(--card-background-color);
        overflow: hidden;
      }
      .msg-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        cursor: pointer;
        user-select: none;
        font-family: 'Fira Code', monospace;
        font-size: 12px;
      }
      .msg-header:hover {
        background: var(--secondary-background-color);
      }
      .msg-header-text {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .topic {
        font-weight: 600;
        color: var(--primary-color);
      }
      .ts {
        color: var(--secondary-text-color);
        margin-right: 8px;
      }
      .device {
        color: var(--secondary-text-color);
        margin-left: 8px;
      }
      .badge {
        display: inline-block;
        padding: 1px 6px;
        border-radius: 3px;
        font-size: 10px;
        font-weight: 700;
        margin-right: 8px;
        letter-spacing: 0.5px;
      }
      .badge-in {
        background: rgba(33, 150, 243, 0.2);
        color: #2196f3;
      }
      .badge-out {
        background: rgba(255, 152, 0, 0.2);
        color: #ff9800;
      }
      select, input[type="text"] {
        padding: 4px 8px;
        border-radius: 4px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        font-size: 12px;
      }
      .msg-body {
        padding: 0 12px 12px 12px;
        border-top: 1px solid var(--divider-color);
      }
      .msg-actions {
        display: flex;
        justify-content: flex-end;
        padding: 8px 0;
      }
      pre {
        background: var(--code-editor-background-color, #1e1e1e);
        color: var(--code-editor-text-color, #d4d4d4);
        padding: 12px;
        border-radius: 6px;
        max-height: 400px;
        overflow: auto;
        font-size: 11px;
        font-family: 'Fira Code', monospace;
        white-space: pre-wrap;
        margin: 0;
      }
      .empty {
        text-align: center;
        padding: 48px;
        color: var(--secondary-text-color);
      }
      .toast {
        position: fixed;
        top: 24px;
        right: 24px;
        background: var(--primary-color);
        color: var(--text-primary-color, white);
        padding: 10px 16px;
        border-radius: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,.2);
        z-index: 10;
        font-size: 13px;
      }
    `;
  }

  _formatTs(ts) {
    return new Date((ts || 0) * 1000).toISOString().slice(11, 19);
  }

  render() {
    const filtered = this._filtered();
    const topics = this._uniqueTopics();
    return html`
      <div class="toolbar">
        <div style="display: flex; gap: 8px; align-items: center;">
          <span>${filtered.length}/${this._messages.length}</span>
          <select
            @change=${(e) => (this._directionFilter = e.target.value)}
            .value=${this._directionFilter}
          >
            <option value="all">Все направления</option>
            <option value="in">Только входящие (IN)</option>
            <option value="out">Только исходящие (OUT)</option>
          </select>
          <select
            @change=${(e) => (this._filter = e.target.value)}
            .value=${this._filter}
          >
            <option value="">Все topics</option>
            ${topics.map((t) => html`<option value=${t}>${t}</option>`)}
          </select>
        </div>
        <div class="toolbar-buttons">
          <button
            @click=${this._copyAll}
            ?disabled=${this._messages.length === 0}
          >
            Copy all
          </button>
          <button @click=${this._clear}>Очистить</button>
        </div>
      </div>
      ${filtered.length === 0
        ? html`<div class="empty">
            ${this._messages.length === 0
              ? "Пока нет WS-сообщений…"
              : "Нет сообщений по текущему фильтру."}
          </div>`
        : filtered.map((m, idx) => {
            // Глобальный index для _expanded — находим по reference в массиве.
            const globalIdx = this._messages.indexOf(m);
            const isExpanded = !!this._expanded[globalIdx];
            const direction = m.direction || "in";
            return html`
              <div class="msg">
                <div class="msg-header" @click=${() => this._toggle(globalIdx)}>
                  <div class="msg-header-text">
                    <span class="ts">${this._formatTs(m.ts)}</span>
                    <span class="badge badge-${direction}">
                      ${direction === "in" ? "IN" : "OUT"}
                    </span>
                    <span class="topic">${m.topic || "?"}</span>
                    <span class="device">${m.device_id || ""}</span>
                  </div>
                  <span>${isExpanded ? "▾" : "▸"}</span>
                </div>
                ${isExpanded
                  ? html`
                      <div class="msg-body">
                        <div class="msg-actions">
                          <button
                            @click=${(e) => {
                              e.stopPropagation();
                              this._copy(m);
                            }}
                          >
                            Copy JSON
                          </button>
                        </div>
                        <pre>${JSON.stringify(m, null, 2)}</pre>
                      </div>
                    `
                  : ""}
              </div>
            `;
          })}
      ${this._toast ? html`<div class="toast">${this._toast}</div>` : ""}
    `;
  }
}

customElements.define("sberhome-log-view", SberHomeLogView);
