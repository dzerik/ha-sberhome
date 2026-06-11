import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";

/**
 * 🧪 EXPERIMENTAL — TTS surrogate UI tab.
 * Третий segment в Automations panel. Статус surrogate-сценариев per home,
 * тестовая озвучка с latency feedback, автогенерированный YAML snippet.
 */
export class SberhomeTtsView extends LitElement {
  static get properties() {
    return {
      hass: { attribute: false },
      _loading: { state: true },
      _homes: { state: true },
      _selectedHomeId: { state: true },
      _message: { state: true },
      _selectedDeviceIds: { state: true },
      _testStatus: { state: true },
    };
  }

  static get styles() {
    return [
      css`
        :host { display: block; padding: 12px 16px; }
        .banner {
          background: #fff3cd; border: 1px solid #ffe69c;
          border-left: 3px solid #cf9000; border-radius: 4px;
          padding: 10px 12px; margin-bottom: 14px;
        }
        .banner .title { font-weight: 600; font-size: 13px; color: #7a5500; }
        .banner .body { font-size: 11px; color: #7a5500; margin-top: 4px; line-height: 1.4; }
        .section-title { font-size: 13px; font-weight: 600; margin: 14px 0 6px 0; }
        .card { border: 1px solid var(--divider-color, #ddd); border-radius: 6px;
                background: var(--card-background-color, white); padding: 10px; }
        .home-row { display: flex; justify-content: space-between; align-items: center;
                    padding: 8px 10px; border-bottom: 1px solid var(--divider-color, #eee); font-size: 12px; }
        .home-row:last-child { border-bottom: none; }
        .badge { padding: 2px 6px; border-radius: 3px; font-size: 10px; }
        .badge.ok { background: #e0f0e0; color: #286; }
        .badge.absent { background: #f0f0f0; color: #888; }
        .scenario-id { font-size: 10px; color: var(--secondary-text-color, #888); margin-left: 6px; }
        .label { font-size: 11px; color: var(--secondary-text-color, #666); margin-bottom: 4px; }
        select, input, textarea {
          width: 100%; padding: 5px 8px; font-size: 12px; box-sizing: border-box;
          border: 1px solid var(--divider-color, #ddd); border-radius: 4px;
          background: var(--card-background-color, white);
          color: var(--primary-text-color);
        }
        .speaker-chip {
          display: inline-block; font-size: 10px; padding: 3px 6px; border-radius: 3px;
          background: #e8f0fe; color: #226; margin: 2px;
        }
        .speaker-chip.offline { background: #f0f0f0; color: #999; }
        button.primary {
          padding: 6px 14px; font-size: 12px; background: var(--primary-color, #0066cc);
          color: var(--text-primary-color, white); border: 0; border-radius: 4px; cursor: pointer;
        }
        button.secondary {
          padding: 3px 8px; font-size: 11px; border: 1px solid var(--primary-color, #0066cc);
          color: var(--primary-color, #0066cc); background: transparent; border-radius: 3px; cursor: pointer;
        }
        pre.yaml {
          background: #1e1e1e; color: #dcdcdc; font-size: 11px;
          padding: 10px; border-radius: 6px; line-height: 1.4;
          margin: 0; overflow-x: auto;
        }
        .latency { font-size: 11px; color: var(--secondary-text-color, #888); margin-left: 8px; }
        ha-code-editor {
          border: 1px solid var(--divider-color, #ddd);
          border-radius: 4px;
          overflow: hidden;
          display: block;
          min-height: 60px;
          font-size: 12px;
        }
        .template-examples { margin-top: 6px; font-size: 11px; }
        .template-examples summary {
          cursor: pointer; color: var(--secondary-text-color, #666);
          user-select: none; padding: 4px 0;
        }
        .template-examples ul { list-style: none; padding: 6px 0 0 0; margin: 0; }
        .template-examples li {
          padding: 3px 0; line-height: 1.5;
          color: var(--secondary-text-color, #666);
        }
        .template-examples code {
          background: var(--secondary-background-color, #f5f5f5);
          color: var(--primary-text-color);
          padding: 2px 5px; border-radius: 3px;
          font-family: var(--code-font-family, monospace);
          font-size: 10px; cursor: pointer; margin-right: 6px;
          white-space: nowrap;
        }
        .template-examples code:hover {
          background: var(--primary-color, #0066cc);
          color: var(--text-primary-color, #fff);
        }
        .template-hint {
          padding: 6px 8px; margin-top: 6px;
          background: var(--secondary-background-color, #f5f5f5);
          border-radius: 4px; line-height: 1.5;
        }
        .template-hint code {
          cursor: default; font-size: 10px;
          background: transparent; padding: 0;
        }
        .template-hint code:hover {
          background: transparent; color: inherit;
        }
      `,
      mobileBase,
    ];
  }

  constructor() {
    super();
    this._loading = true;
    this._homes = [];
    this._selectedHomeId = null;
    this._message = "Привет из Home Assistant";
    this._selectedDeviceIds = null; // null = default (all)
    this._testStatus = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadStatus();
  }

  async _loadStatus() {
    this._loading = true;
    try {
      const r = await this.hass.callWS({ type: "sberhome/tts_surrogate/status" });
      this._homes = r.homes || [];
      if (!this._selectedHomeId && this._homes.length) {
        this._selectedHomeId = this._homes[0].home_id;
      }
    } catch (err) {
      console.error("TTS surrogate status failed", err);
      this._homes = [];
    } finally {
      this._loading = false;
    }
  }

  async _ensureSurrogate(homeId) {
    try {
      const r = await this.hass.callWS({
        type: "sberhome/tts_surrogate/ensure",
        home_id: homeId,
      });
      if (r && r.ok === false) {
        console.error("TTS surrogate ensure rejected", r);
        alert("Не удалось создать surrogate: " + (r.error || "unknown error"));
        return;
      }
      await this._loadStatus();
    } catch (err) {
      console.error("TTS surrogate ensure failed", err);
      alert("Не удалось создать surrogate: " + (err.message || String(err)));
    }
  }

  async _runTest() {
    if (!this._selectedHomeId) return;
    this._testStatus = { running: true };
    const payload = {
      type: "sberhome/tts_surrogate/test",
      home_id: this._selectedHomeId,
      message: this._message,
    };
    if (this._selectedDeviceIds && this._selectedDeviceIds.length) {
      payload.device_ids = this._selectedDeviceIds;
    }
    try {
      const r = await this.hass.callWS(payload);
      this._testStatus = r;
    } catch (err) {
      this._testStatus = { ok: false, error: err.message || String(err) };
    }
  }

  _copyYaml() {
    const yaml = this._renderYamlSnippet({ asString: true });
    navigator.clipboard.writeText(yaml).catch((err) => {
      console.error("Copy failed", err);
    });
  }

  _selectedHome() {
    return this._homes.find((h) => h.home_id === this._selectedHomeId);
  }

  _renderYamlSnippet({ asString = false } = {}) {
    const home = this._selectedHome();
    if (!home) return asString ? "" : html``;
    const slug = this._homeSlug(home.name);
    // Какие speaker'ы попадут в device_ids: явно выбранные либо все из дома
    // (default behaviour notify-entity'а). Всегда показываем закомментированными
    // чтобы юзер мог раскомментировать для override без необходимости копировать
    // UUID'ы вручную из device picker.
    const ids =
      this._selectedDeviceIds && this._selectedDeviceIds.length
        ? this._selectedDeviceIds
        : home.speakers.map((s) => s.id);
    const lines = [
      `- service: notify.send_message`,
      `  target:`,
      `    entity_id: notify.sberhome_${slug}`,
      `  data:`,
      `    message: "${this._message.replace(/"/g, '\\"')}"`,
      `    # device_ids:  # раскомментируйте для override (default = все колонки дома)`,
    ];
    ids.forEach((id) => lines.push(`    #   - ${id}`));
    return asString ? lines.join("\n") : html`<pre class="yaml">${lines.join("\n")}</pre>`;
  }

  // Cyrillic → Latin (same as yaml_utils.slugify) — HA генерирует entity_id
  // из имени, транслитерируя/слагифицируя его. Мы должны делать то же самое,
  // иначе YAML-сниппет будет ссылаться на несуществующий entity.
  static _CYR_TO_LAT = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo",
    ж: "zh", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m",
    н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u",
    ф: "f", х: "h", ц: "ts", ч: "ch", ш: "sh", щ: "sch",
    ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
  };

  _homeSlug(name) {
    const lower = (name || "home").toLowerCase();
    const lat = [...lower]
      .map((ch) => (SberhomeTtsView._CYR_TO_LAT[ch] ?? ch))
      .join("");
    return (
      lat
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "") || "home"
    );
  }

  _toggleSpeaker(deviceId) {
    const home = this._selectedHome();
    if (!home) return;
    const allIds = home.speakers.map((s) => s.id);
    let current = this._selectedDeviceIds == null ? [...allIds] : [...this._selectedDeviceIds];
    if (current.includes(deviceId)) {
      current = current.filter((id) => id !== deviceId);
    } else {
      current.push(deviceId);
    }
    // Если выбраны все — возвращаемся в "default" режим (null)
    this._selectedDeviceIds =
      current.length === allIds.length && allIds.every((id) => current.includes(id)) ? null : current;
  }

  _renderHomeRow(h) {
    return html`
      <div class="home-row">
        <div>
          <span style="font-weight:600;">🏠 ${h.name || h.home_id}</span>
          ${h.scenario_id
            ? html`<span class="scenario-id">scenario_id: ${h.scenario_id.slice(0, 8)}…</span>`
            : html`<span class="scenario-id">не создан</span>`}
        </div>
        ${h.scenario_id
          ? html`<span class="badge ok">✓ создан</span>`
          : (h.speakers && h.speakers.length > 0)
          ? html`<button class="secondary" @click=${() => this._ensureSurrogate(h.home_id)}>
              Создать сейчас
            </button>`
          : html`<span class="badge absent" title="Нет колонок Sber в этом доме">
              без колонок
            </span>`}
      </div>
    `;
  }

  _renderTestForm() {
    const home = this._selectedHome();
    if (!home) return html`<div class="card">Нет домов с колонками.</div>`;
    const speakerIds =
      this._selectedDeviceIds == null
        ? new Set(home.speakers.map((s) => s.id))
        : new Set(this._selectedDeviceIds);
    return html`
      <div class="card">
        <div class="label">Дом</div>
        <select
          .value=${this._selectedHomeId}
          @change=${(e) => {
            this._selectedHomeId = e.target.value;
            this._selectedDeviceIds = null;
          }}
        >
          ${this._homes.map((h) => html`<option value=${h.home_id}>${h.name}</option>`)}
        </select>

        <div class="label" style="margin-top:8px;">Фраза</div>
        <ha-code-editor
          mode="jinja2"
          autocomplete-entities
          autocomplete-icons
          .value=${this._message}
          @value-changed=${(e) => (this._message = e.detail.value)}
        ></ha-code-editor>
        ${this._renderTemplateExamples()}

        <div class="label" style="margin-top:8px;">Колонки (по умолчанию — все в доме)</div>
        <div>
          ${home.speakers.length === 0
            ? html`<span class="speaker-chip offline">нет колонок в этом доме</span>`
            : home.speakers.map(
                (s) => html`
                  <span
                    class="speaker-chip ${s.online === false ? "offline" : ""}"
                    style="cursor:pointer;"
                    @click=${() => this._toggleSpeaker(s.id)}
                  >
                    ${speakerIds.has(s.id) ? "☑" : "☐"} ${s.name}
                  </span>
                `
              )}
        </div>

        <div style="margin-top:10px;">
          <button class="primary" @click=${this._runTest} ?disabled=${home.speakers.length === 0}>
            ▶ Озвучить
          </button>
          ${this._testStatus?.running ? html`<span class="latency">тестируем…</span>` : ""}
          ${this._testStatus?.ok === true
            ? html`<span class="latency">latency ${this._testStatus.latency_ms}ms</span>`
            : ""}
          ${this._testStatus?.ok === false
            ? html`<span class="latency" style="color:#c33;">${this._testStatus.error}</span>`
            : ""}
        </div>
      </div>
    `;
  }

  _insertSnippet(snippet) {
    const current = this._message || "";
    this._message = current ? `${current} ${snippet}` : snippet;
  }

  /**
   * Подсказки с готовыми Jinja2-шаблонами для surrogate-TTS.
   * Клик по `<code>` дописывает сниппет в текущую фразу.
   * Бэкенд (TtsSurrogateService.send) рендерит шаблон перед отправкой
   * в Sber на КАЖДЫЙ вызов — для surrogate это «live»-подстановка.
   */
  _renderTemplateExamples() {
    return html`
      <details class="template-examples">
        <summary>Примеры шаблонов (click чтобы вставить)</summary>
        <ul>
          <li>
            <code @click=${() => this._insertSnippet("{{ states('sensor.living_temp') }}")}
              >{{ states('sensor.living_temp') }}</code>
            — значение датчика
          </li>
          <li>
            <code @click=${() =>
              this._insertSnippet("{{ state_attr('climate.bedroom', 'current_temperature') }}")}
              >{{ state_attr('climate.bedroom', 'current_temperature') }}</code>
            — атрибут сущности
          </li>
          <li>
            <code @click=${() => this._insertSnippet("{{ now().strftime('%H:%M') }}")}
              >{{ now().strftime('%H:%M') }}</code>
            — текущее время
          </li>
          <li>
            <code @click=${() =>
              this._insertSnippet(
                "{% if is_state('binary_sensor.door', 'on') %}открыта{% else %}закрыта{% endif %}"
              )}
              >{% if is_state('binary_sensor.door', 'on') %}открыта{% else %}закрыта{% endif %}</code>
            — условие
          </li>
        </ul>
        <div class="template-hint">
          Surrogate-TTS подставляет значения <strong>на каждое произнесение</strong>
          (через <code>notify.sber_tts_*</code> в HA-автоматизации).
          Доступны стандартные функции: <code>states()</code>,
          <code>state_attr()</code>, <code>is_state()</code>,
          <code>now()</code>, фильтры (<code>round</code>, <code>float</code> и т.п.).
        </div>
      </details>
    `;
  }

  render() {
    if (this._loading) return html`<p>Loading…</p>`;
    return html`
      <div class="banner">
        <div class="title">🧪 EXPERIMENTAL</div>
        <div class="body">
          Фича работает через run-time edit Sber-сценария. Каждый вызов = 2–3 API-call'а
          в облако. Не для частых уведомлений (>1/мин). Sber может изменить wire-формат
          или начать лимитировать.
        </div>
      </div>

      <div class="section-title">Состояние surrogate-сценариев</div>
      <div class="card" style="padding:0;">
        ${this._homes.length === 0
          ? html`<div style="padding:14px;text-align:center;color:#888;font-size:12px;">
              Нет домов в state_cache.
            </div>`
          : this._homes.map((h) => this._renderHomeRow(h))}
      </div>

      <div class="section-title">Тестовая озвучка</div>
      ${this._renderTestForm()}

      <div class="section-title">YAML для HA-automation</div>
      ${this._renderYamlSnippet()}
      <div style="text-align:right;margin-top:4px;">
        <button class="secondary" @click=${this._copyYaml}>📋 Скопировать</button>
      </div>
    `;
  }
}

customElements.define("sberhome-tts-view", SberhomeTtsView);
