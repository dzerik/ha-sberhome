/**
 * SberHome — Diagnostics tab. Picks one device, shows full DTO + entities.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

class SberHomeDiagnostics extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      devices: { type: Array },
      _selectedId: { type: String },
      _detail: { type: Object },
    };
  }

  constructor() {
    super();
    this.devices = [];
    this._selectedId = "";
    this._detail = null;
  }

  async _onSelect(e) {
    this._selectedId = e.target.value;
    if (!this._selectedId) {
      this._detail = null;
      return;
    }
    this._detail = await this.hass.callWS({
      type: "sberhome/device_detail",
      device_id: this._selectedId,
    });
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      select {
        padding: 8px 12px;
        border-radius: 6px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color);
        min-width: 320px;
        margin-bottom: 16px;
      }
      pre {
        background: var(--code-editor-background-color, #1e1e1e);
        color: var(--code-editor-text-color, #d4d4d4);
        padding: 12px;
        border-radius: 6px;
        max-height: 600px;
        overflow: auto;
        font-size: 12px;
        white-space: pre-wrap;
      }
    `;
  }

  render() {
    return html`
      <select @change=${this._onSelect}>
        <option value="">— выберите устройство —</option>
        ${this.devices.map(
          (d) =>
            html`<option value=${d.device_id}>
              ${d.name} (${d.category || "?"})
            </option>`
        )}
      </select>
      ${this._detail
        ? html`<pre>${JSON.stringify(this._detail, null, 2)}</pre>`
        : ""}
    `;
  }
}

customElements.define("sberhome-diagnostics", SberHomeDiagnostics);
