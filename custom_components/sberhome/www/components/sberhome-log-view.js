/**
 * SberHome — Live WS message log (last 100, real-time via subscribe).
 *
 * Каждое сообщение рендерится отдельной карточкой с коротким заголовком
 * (timestamp + topic + device_id) и развёрткой по клику — полный JSON в
 * sberhome-json-block (со своей кнопкой копирования).
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";
import { Localized } from "../i18n/index.js";
import "./sberhome-json-block.js";

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

/** Badge text per message direction; ``replay`` marks DevTools injections. */
const DIRECTION_LABEL = { in: "IN", out: "OUT", replay: "REPLAY" };

class SberHomeLogView extends Localized(LitElement) {
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
    this._directionFilter = "all"; // all / in / out / replay
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

  async _copyAll() {
    await copyJson(this._messages);
    this._toast = this.t("log.copied_all", { n: this._messages.length });
    setTimeout(() => {
      this._toast = "";
    }, 2000);
  }

  static get styles() {
    return [css`
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
      .msg-header:focus-visible {
        outline: 2px solid var(--primary-color);
        outline-offset: -2px;
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
      .badge-replay {
        background: rgba(156, 39, 176, 0.2);
        color: #ab47bc;
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
        padding: 8px 12px 12px 12px;
        border-top: 1px solid var(--divider-color);
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
    `, mobileBase];
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
          <span title=${this.t("log.count_title")}>${filtered.length}/${this._messages.length}</span>
          <select
            aria-label=${this.t("log.direction_label")}
            @change=${(e) => (this._directionFilter = e.target.value)}
            .value=${this._directionFilter}
          >
            <option value="all">${this.t("log.direction_all")}</option>
            <option value="in">${this.t("log.direction_in")}</option>
            <option value="out">${this.t("log.direction_out")}</option>
            <option value="replay">${this.t("log.direction_replay")}</option>
          </select>
          <select
            aria-label=${this.t("log.topic_label")}
            @change=${(e) => (this._filter = e.target.value)}
            .value=${this._filter}
          >
            <option value="">${this.t("log.topic_all")}</option>
            ${topics.map((t) => html`<option value=${t}>${t}</option>`)}
          </select>
        </div>
        <div class="toolbar-buttons">
          <button
            @click=${this._copyAll}
            ?disabled=${this._messages.length === 0}
          >
            ${this.t("log.copy_all")}
          </button>
          <button @click=${this._clear}>${this.t("log.clear")}</button>
        </div>
      </div>
      ${filtered.length === 0
        ? html`<div class="empty">
            ${this._messages.length === 0
              ? this.t("log.empty")
              : this.t("log.empty_filtered")}
          </div>`
        : filtered.map((m, idx) => {
            // Глобальный index для _expanded — находим по reference в массиве.
            const globalIdx = this._messages.indexOf(m);
            const isExpanded = !!this._expanded[globalIdx];
            const direction = m.direction || "in";
            return html`
              <div class="msg">
                <div class="msg-header"
                  role="button"
                  tabindex="0"
                  aria-expanded=${isExpanded ? "true" : "false"}
                  @click=${() => this._toggle(globalIdx)}
                  @keydown=${(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      this._toggle(globalIdx);
                    }
                  }}>
                  <div class="msg-header-text">
                    <span class="ts">${this._formatTs(m.ts)}</span>
                    <span class="badge badge-${direction}">
                      ${DIRECTION_LABEL[direction] || direction.toUpperCase()}
                    </span>
                    <span class="topic">${m.topic || "?"}</span>
                    <span class="device">${m.device_id || ""}</span>
                  </div>
                  <span aria-hidden="true">${isExpanded ? "▾" : "▸"}</span>
                </div>
                ${isExpanded
                  ? html`
                      <div class="msg-body">
                        <sberhome-json-block
                          .hass=${this.hass}
                          .value=${m}
                          label=${this.t("log.message_json")}
                        ></sberhome-json-block>
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
