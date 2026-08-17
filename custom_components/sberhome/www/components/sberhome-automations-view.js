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
import { Localized } from "../i18n/index.js";

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
  import(`./sberhome-ttc-view.js${_q}`),
]);

export class SberhomeAutomationsView extends Localized(LitElement) {
  static get properties() {
    return {
      hass: { attribute: false },
      homes: { attribute: false },
      selectedHomeId: { attribute: false },
      _section: { state: true },
      _listenersCount: { state: true },
      _groups: { state: true },
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
      /* Глобальная переменная «я дома» — управляет сберовскими сценариями. */
      .athome {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 12px 16px 0;
        font-size: 14px;
        color: var(--primary-text-color);
      }
      .athome .toggle {
        margin-left: auto;
        border: 1px solid var(--divider-color, #ccc);
        background: transparent;
        color: var(--secondary-text-color, #666);
        border-radius: 999px;
        padding: 6px 16px;
        font-size: 13px;
        cursor: pointer;
      }
      .athome .toggle.on {
        background: var(--primary-color, #03a9f4);
        border-color: var(--primary-color, #03a9f4);
        color: #fff;
      }
      .athome .toggle[disabled] {
        opacity: 0.5;
        cursor: default;
      }
      .section-title {
        margin: 16px 16px 4px;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--secondary-text-color, #888);
      }
      .athome small {
        color: var(--secondary-text-color, #888);
        font-size: 12px;
      }
    `, mobileBase];
  }

  constructor() {
    super();
    this._section = "intents";
    this._listenersCount = 0;
    this.homes = [];
    this.selectedHomeId = null;
    this._groups = [];
    this._groupsFetched = false;
  }

  updated(changed) {
    if (changed.has("hass") && this.hass && !this._groupsFetched) {
      this._groupsFetched = true;
      this._fetchGroups();
    }
  }

  async _fetchGroups() {
    try {
      const r = await this.hass.callWS({ type: "sberhome/get_groups" });
      this._groups = r?.groups || [];
    } catch (_e) {
      this._groups = [];
    }
  }

  _groupState(entityId) {
    const st = entityId ? this.hass?.states?.[entityId] : null;
    if (!st) return null;
    return { on: st.state === "on", available: st.state !== "unavailable" && st.state !== "unknown" };
  }

  _toggleGroup(group) {
    const s = this._groupState(group.entity_id);
    if (!s?.available) return;
    this.hass.callService("switch", s.on ? "turn_off" : "turn_on", {
      entity_id: group.entity_id,
    });
  }

  _onListenersCount(ev) {
    this._listenersCount = ev.detail?.count ?? 0;
  }

  // Все HA-сущности переменной «я дома» (switch.…at_home) по домам аккаунта.
  _atHomes() {
    const states = this.hass?.states || {};
    const out = [];
    for (const [id, st] of Object.entries(states)) {
      if (id.startsWith("switch.") && id.includes("at_home")) {
        const fn = st.attributes?.friendly_name || id;
        // Имя дома — в скобках («At home (Мой дом)»). Сущности без скобок —
        // легаси-глобальный свитч (до 5.24.2) — пропускаем.
        const m = fn.match(/\(([^)]+)\)/);
        if (!m) continue;
        out.push({
          id,
          label: m[1],
          on: st.state === "on",
          available: st.state !== "unavailable" && st.state !== "unknown",
        });
      }
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
  }

  _toggleAtHome(entity) {
    if (!entity?.available) return;
    this.hass.callService("switch", entity.on ? "turn_off" : "turn_on", {
      entity_id: entity.id,
    });
  }

  render() {
    const atHomes = this._atHomes();
    return html`
      ${atHomes.map(
        (a) => html`<div class="athome">
          <span>🏠 ${a.label}</span>
          <button
            class="toggle ${a.on ? "on" : ""}"
            ?disabled=${!a.available}
            @click=${() => this._toggleAtHome(a)}
          >${a.on ? this.t("automations.at_home") : this.t("automations.away")}</button>
        </div>`,
      )}

      ${this._groups.length
        ? html`<div class="section-title">🔀 ${this.t("automations.section_groups")}</div>
            ${this._groups.map((g) => {
              const s = this._groupState(g.entity_id);
              return html`<div class="athome">
                <span>${g.name} <small>(${g.device_count})</small></span>
                <button
                  class="toggle ${s?.on ? "on" : ""}"
                  ?disabled=${!s || !s.available}
                  @click=${() => this._toggleGroup(g)}
                >${s?.on ? this.t("common.on") : this.t("common.off")}</button>
              </div>`;
            })}`
        : ""}

      <div class="chips">
        <button
          class="chip ${this._section === "intents" ? "active" : ""}"
          @click=${() => (this._section = "intents")}
        >🎤 ${this.t("tab.scenarios")}</button>
        <button
          class="chip ${this._section === "listeners" ? "active" : ""}"
          @click=${() => (this._section = "listeners")}
        >⚡ ${this.t("tab.listeners")}${this._listenersCount
          ? html`<span class="count">${this._listenersCount}</span>`
          : ""}</button>
        <button
          class="chip ${this._section === "tts" ? "active" : ""}"
          @click=${() => (this._section = "tts")}
        >🔊 ${this.t("tab.tts")}</button>
        <button
          class="chip ${this._section === "ttc" ? "active" : ""}"
          @click=${() => (this._section = "ttc")}
        >🎙 ${this.t("tab.ttc")}</button>
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
        : this._section === "tts"
        ? html`<sberhome-tts-view .hass=${this.hass}></sberhome-tts-view>`
        : html`<sberhome-ttc-view .hass=${this.hass}></sberhome-ttc-view>`}
    `;
  }
}

customElements.define("sberhome-automations-view", SberhomeAutomationsView);
