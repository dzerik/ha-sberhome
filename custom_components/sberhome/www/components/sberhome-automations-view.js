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
import "./sberhome-intents-view.js";
import "./sberhome-listeners-view.js";
import "./sberhome-tts-view.js";

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
      .segmented {
        display: inline-flex; gap: 0;
        border: 1px solid var(--divider-color, #ddd);
        border-radius: 8px; overflow: hidden;
        margin: 12px 16px;
      }
      .segmented button {
        padding: 6px 14px; font-size: 13px;
        background: transparent; border: 0; cursor: pointer;
        color: var(--primary-text-color);
        border-right: 1px solid var(--divider-color, #ddd);
      }
      .segmented button:last-child { border-right: 0; }
      .segmented button.active {
        background: var(--primary-color, #0066cc);
        color: var(--text-primary-color, white);
      }
      .count { margin-left: 6px; opacity: 0.75; font-size: 11px; }
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
      <div class="segmented">
        <button
          class=${this._section === "intents" ? "active" : ""}
          @click=${() => (this._section = "intents")}
        >🎤 Intents</button>
        <button
          class=${this._section === "listeners" ? "active" : ""}
          @click=${() => (this._section = "listeners")}
        >⚡ Listeners<span class="count">${this._listenersCount}</span></button>
        <button
          class=${this._section === "tts" ? "active" : ""}
          @click=${() => (this._section = "tts")}
        >🔊 TTS</button>
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
