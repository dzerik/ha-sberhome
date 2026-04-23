/**
 * SberHome — Rooms view (cards grid).
 *
 * Shows rooms from Sber Smart Home with device counts.
 * Click on room → dispatches event to filter device picker.
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

class SberHomeRoomsView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      rooms: { type: Array },
      home: { type: Object },
      totalDevices: { type: Number },
      _selectedRoom: { type: String },
    };
  }

  constructor() {
    super();
    this.rooms = [];
    this.home = null;
    this.totalDevices = 0;
    this._selectedRoom = null;
  }

  _onRoomClick(roomId) {
    this._selectedRoom = this._selectedRoom === roomId ? null : roomId;
    this.dispatchEvent(
      new CustomEvent("room-selected", {
        detail: { roomId: this._selectedRoom },
        bubbles: true,
        composed: true,
      })
    );
  }

  _roomIcon(room) {
    const type = (room.image_set_type || "").toLowerCase();
    if (type.includes("kitchen")) return "🍳";
    if (type.includes("bedroom") || type.includes("sleep")) return "🛏️";
    if (type.includes("bath")) return "🛁";
    if (type.includes("living") || type.includes("hall")) return "🛋️";
    if (type.includes("child")) return "🧸";
    if (type.includes("office") || type.includes("work")) return "💼";
    if (type.includes("garage")) return "🚗";
    if (type.includes("balcony") || type.includes("terrace")) return "🌿";
    return "🏠";
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      .summary {
        display: flex;
        gap: 16px;
        align-items: center;
        margin-bottom: 16px;
        padding: 12px 16px;
        background: var(--card-background-color);
        border-radius: 8px;
        box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.1));
      }
      .summary .home-name {
        font-size: 18px;
        font-weight: 500;
        flex: 1;
      }
      .summary .stats {
        color: var(--secondary-text-color);
        font-size: 14px;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 12px;
      }
      .room-card {
        background: var(--card-background-color);
        border-radius: 12px;
        padding: 20px 16px;
        cursor: pointer;
        box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.1));
        transition: transform .15s ease, box-shadow .15s ease;
        text-align: center;
      }
      .room-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,.15);
      }
      .room-card.selected {
        border: 2px solid var(--primary-color);
        background: var(--primary-color);
        color: #fff;
      }
      .room-icon { font-size: 32px; margin-bottom: 8px; }
      .room-name {
        font-size: 16px;
        font-weight: 500;
        margin-bottom: 4px;
      }
      .room-count {
        font-size: 13px;
        color: var(--secondary-text-color);
      }
      .room-card.selected .room-count { color: rgba(255,255,255,.8); }
      .all-card {
        border: 2px dashed var(--divider-color);
        background: transparent;
        box-shadow: none;
      }
      .all-card:hover { background: var(--secondary-background-color); }
      .empty {
        text-align: center;
        padding: 48px;
        color: var(--secondary-text-color);
      }
    `;
  }

  render() {
    return html`
      ${this.home ? html`
        <div class="summary">
          <div class="home-name">🏡 ${this.home.name || "Дом"}</div>
          <div class="stats">
            ${this.rooms.length} комнат · ${this.totalDevices} устройств
          </div>
        </div>
      ` : ""}

      ${this.rooms.length === 0
        ? html`<div class="empty">Комнаты не найдены. Данные загружаются...</div>`
        : html`
          <div class="grid">
            <div
              class="room-card all-card ${!this._selectedRoom ? 'selected' : ''}"
              @click=${() => this._onRoomClick(null)}
            >
              <div class="room-icon">📋</div>
              <div class="room-name">Все устройства</div>
              <div class="room-count">${this.totalDevices} шт.</div>
            </div>
            ${this.rooms.map(r => html`
              <div
                class="room-card ${this._selectedRoom === r.id ? 'selected' : ''}"
                @click=${() => this._onRoomClick(r.id)}
              >
                <div class="room-icon">${this._roomIcon(r)}</div>
                <div class="room-name">${r.name}</div>
                <div class="room-count">${r.device_count} устройств</div>
              </div>
            `)}
          </div>
        `}
    `;
  }
}

customElements.define("sberhome-rooms-view", SberHomeRoomsView);
