/**
 * Automations wrapper — segmented control «Intents | Listeners | TTS».
 *
 * Контейнер для трёх подвью:
 * - sberhome-intents-view — голосовые сценарии Sber (read/write).
 * - sberhome-listeners-view — YAML-описанные триггеры из configuration.yaml.
 * - sberhome-tts-view — 🧪 EXPERIMENTAL TTS surrogate (run-time edit Sber-сценария
 *   для произнесения произвольного текста через колонки).
 *
 * Listeners-вью эмитит CustomEvent("listeners-count", {detail: {count}}),
 * чтобы показывать бейдж рядом с табом.
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";

// Subviews импортируются ДИНАМИЧЕСКИ с тем же cache-buster `?v=…`, что
// у самого этого модуля. Иначе браузер навсегда кэширует подмодули
// (статический `import "./sberhome-tts-view.js"` идёт по URL без query
// string — другой кэш-ключ, который не инвалидируется бампом версии).
// Top-level await блокирует завершение этого модуля до подгрузки
// подкомпонентов, поэтому к моменту первого render'а они уже
// зарегистрированы в customElements.
const _v = new URL(import.meta.url).searchParams.get("v") || "";
const _q = _v ? `?v=${_v}` : "";
await Promise.all([
  import(`./sberhome-intents-view.js${_q}`),
  import(`./sberhome-listeners-view.js${_q}`),
  import(`./sberhome-tts-view.js${_q}`),
]);

export class SberhomeAutomationsView extends LitElement {
  static get properties() {
    return {
      hass: { attribute: false },
      homes: { attribute: false },
      selectedHomeId: { attribute: false },
      _section: { state: true },
      _listenersCount: { state: true },
    };
  }

  static get styles() {
    return [css`
      :host { display: block; }
      /* Подтабы — chip-стиль, единый с табом «Колонки» (speakers-view). */
      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin: 12px 16px;
      }
      .chip {
        border: 1px solid var(--divider-color, #ccc);
        background: transparent;
        color: var(--secondary-text-color, #666);
        border-radius: 999px;
        padding: 6px 14px;
        font-size: 13px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }
      .chip.active {
        background: var(--primary-color, #03a9f4);
        border-color: var(--primary-color, #03a9f4);
        color: #fff;
      }
      .count {
        font-size: 11px;
        line-height: 1;
        padding: 1px 6px;
        border-radius: 999px;
        background: var(--divider-color, #ddd);
        color: var(--primary-text-color);
      }
      .chip.active .count {
        background: rgba(255, 255, 255, 0.3);
        color: #fff;
      }
    `, mobileBase];
  }

  constructor() {
    super();
    this._section = "intents";
    this._listenersCount = 0;
    this.homes = [];
    this.selectedHomeId = null;
  }

  _onListenersCount(ev) {
    this._listenersCount = ev.detail?.count ?? 0;
  }

  render() {
    return html`
      <div class="chips">
        <button
          class="chip ${this._section === "intents" ? "active" : ""}"
          @click=${() => (this._section = "intents")}
        >🎤 Сценарии</button>
        <button
          class="chip ${this._section === "listeners" ? "active" : ""}"
          @click=${() => (this._section = "listeners")}
        >⚡ Слушатели${this._listenersCount
          ? html`<span class="count">${this._listenersCount}</span>`
          : ""}</button>
        <button
          class="chip ${this._section === "tts" ? "active" : ""}"
          @click=${() => (this._section = "tts")}
        >🔊 Озвучка</button>
      </div>

      ${this._section === "intents"
        ? html`<sberhome-intents-view
            .hass=${this.hass}
            .homes=${this.homes}
            .selectedHomeId=${this.selectedHomeId}
          ></sberhome-intents-view>`
        : this._section === "listeners"
        ? html`<sberhome-listeners-view
            .hass=${this.hass}
            @listeners-count=${this._onListenersCount}
          ></sberhome-listeners-view>`
        : html`<sberhome-tts-view .hass=${this.hass}></sberhome-tts-view>`}
    `;
  }
}

customElements.define("sberhome-automations-view", SberhomeAutomationsView);
