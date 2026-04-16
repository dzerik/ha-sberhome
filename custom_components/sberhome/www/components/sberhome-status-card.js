/**
 * SberHome — Status card (token/WS/polling/errors).
 */

const LitElement = Object.getPrototypeOf(
  customElements.get("ha-panel-lovelace") ?? customElements.get("hui-view")
);
const html = LitElement?.prototype.html;
const css = LitElement?.prototype.css;

function _fmtTs(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}
function _fmtRelative(ts) {
  if (!ts) return "никогда";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return `${diff} сек назад`;
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  return `${Math.floor(diff / 3600)} ч назад`;
}

class SberHomeStatusCard extends LitElement {
  static get properties() {
    return { status: { type: Object } };
  }

  static get styles() {
    return css`
      :host { display: block; padding: 16px; }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px;
      }
      .card {
        background: var(--card-background-color);
        border-radius: 8px;
        padding: 16px;
        box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.05));
      }
      .card h3 {
        margin: 0 0 12px;
        font-size: 14px;
        text-transform: uppercase;
        color: var(--secondary-text-color);
        letter-spacing: 0.5px;
      }
      .row { display: flex; justify-content: space-between; padding: 4px 0; }
      .label { color: var(--secondary-text-color); }
      .value { font-weight: 500; }
      .ok { color: var(--success-color, #4caf50); }
      .bad { color: var(--error-color, #f44336); }
    `;
  }

  render() {
    const s = this.status;
    if (!s) {
      return html`<div class="grid"><div class="card">Загрузка…</div></div>`;
    }
    const wsClass = s.ws.connected ? "ok" : "bad";
    const wsText = s.ws.connected ? "Подключён" : "Отключён";
    return html`
      <div class="grid">
        <div class="card">
          <h3>Устройства</h3>
          <div class="row">
            <span class="label">Всего</span>
            <span class="value">${s.devices_total}</span>
          </div>
          <div class="row">
            <span class="label">Импортировано в HA</span>
            <span class="value">${s.devices_enabled}</span>
          </div>
        </div>

        <div class="card">
          <h3>Polling (REST)</h3>
          <div class="row">
            <span class="label">Интервал</span>
            <span class="value">${s.polling.interval_seconds}s</span>
          </div>
          <div class="row">
            <span class="label">Последний</span>
            <span class="value">${_fmtRelative(s.polling.last_at)}</span>
          </div>
          <div class="row">
            <span class="label">Запросов</span>
            <span class="value">${s.polling.count}</span>
          </div>
          <div class="row">
            <span class="label">Статус</span>
            <span class="value ${s.polling.last_success ? "ok" : "bad"}">
              ${s.polling.last_success ? "OK" : "Ошибка"}
            </span>
          </div>
        </div>

        <div class="card">
          <h3>WebSocket Push</h3>
          <div class="row">
            <span class="label">Состояние</span>
            <span class="value ${wsClass}">${wsText}</span>
          </div>
          <div class="row">
            <span class="label">Сообщений получено</span>
            <span class="value">${s.ws.message_count}</span>
          </div>
          <div class="row">
            <span class="label">Последнее</span>
            <span class="value">${_fmtRelative(s.ws.last_message_at)}</span>
          </div>
        </div>

        <div class="card">
          <h3>Токены</h3>
          <div class="row">
            <span class="label">SberID expires</span>
            <span class="value">${_fmtTs(s.tokens.sberid_expires_at)}</span>
          </div>
          <div class="row">
            <span class="label">Companion expires</span>
            <span class="value">${_fmtTs(s.tokens.companion_expires_at)}</span>
          </div>
        </div>

        <div class="card">
          <h3>Ошибки</h3>
          <div class="row">
            <span class="label">Всего за сессию</span>
            <span class="value ${s.error_count > 0 ? "bad" : "ok"}">
              ${s.error_count}
            </span>
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define("sberhome-status-card", SberHomeStatusCard);
