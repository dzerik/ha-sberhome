/**
 * SberHome — Live WS message log (last 100, real-time via subscribe).
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

class SberHomeLogView extends LitElement {
  static get properties() {
    return { hass: { type: Object }, _messages: { type: Array } };
  }

  constructor() {
    super();
    this._messages = [];
    this._unsub = null;
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
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      .toolbar {
        display: flex;
        justify-content: space-between;
        margin-bottom: 12px;
      }
      button {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color);
        cursor: pointer;
        color: var(--primary-text-color);
      }
      pre {
        background: var(--code-editor-background-color, #1e1e1e);
        color: var(--code-editor-text-color, #d4d4d4);
        padding: 12px;
        border-radius: 6px;
        max-height: 600px;
        overflow: auto;
        font-size: 12px;
        font-family: 'Fira Code', monospace;
        white-space: pre-wrap;
      }
      .empty {
        text-align: center;
        padding: 48px;
        color: var(--secondary-text-color);
      }
    `;
  }

  render() {
    return html`
      <div class="toolbar">
        <span>${this._messages.length} сообщений (live)</span>
        <button @click=${this._clear}>Очистить</button>
      </div>
      ${this._messages.length === 0
        ? html`<div class="empty">Пока нет WS-сообщений…</div>`
        : html`<pre>${this._messages
            .map(
              (m) =>
                `[${new Date((m.ts || 0) * 1000).toISOString().slice(11, 19)}] ${m.topic || "?"} ${m.device_id || ""} ${JSON.stringify(m.payload || m).slice(0, 200)}`
            )
            .join("\n")}</pre>`}
    `;
  }
}

customElements.define("sberhome-log-view", SberHomeLogView);
