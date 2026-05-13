/**
 * Listeners view — read-only список YAML-описанных триггеров.
 *
 * Источник данных: WS endpoint `sberhome/listeners/list`.
 * Управление через `configuration.yaml` → секция `sberhome.listeners`.
 *
 * Эмитит CustomEvent("listeners-count", {detail: {count}}) для бейджа в wrapper.
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";

export class SberhomeListenersView extends LitElement {
  static get properties() {
    return {
      hass: { attribute: false },
      _listeners: { state: true },
      _loading: { state: true },
      _filterQuery: { state: true },
    };
  }

  static get styles() {
    return [css`
      :host { display: block; }
      .header { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
      .filter { flex: 1; min-width: 200px; }
      .filter input {
        width: 100%; padding: 6px 10px; font-size: 13px;
        border: 1px solid var(--divider-color, #ddd); border-radius: 6px;
      }
      .badge {
        display: inline-block; padding: 2px 6px;
        background: var(--secondary-background-color, #f0f0f0);
        border-radius: 3px; font-size: 10px; color: var(--secondary-text-color, #666);
      }
      .badge.disabled { background: #ffe; color: #883; }
      .card {
        padding: 12px; margin-bottom: 8px;
        border: 1px solid var(--divider-color, #ddd); border-radius: 8px;
        background: var(--card-background-color, white);
      }
      .card-header { display: flex; justify-content: space-between; gap: 8px; }
      .name { font-weight: 600; font-size: 14px; }
      .slug {
        font-family: ui-monospace, "Cascadia Code", monospace;
        font-size: 11px; color: var(--secondary-text-color, #666);
      }
      .filter-summary {
        font-size: 11px; color: var(--secondary-text-color, #666);
        margin-top: 4px;
      }
      .desc { font-size: 12px; margin-top: 6px; color: var(--secondary-text-color); }
      .meta { font-size: 10px; color: var(--secondary-text-color, #999); margin-top: 6px; }
      .empty {
        padding: 24px; text-align: center;
        color: var(--secondary-text-color, #888);
        border: 1px dashed var(--divider-color, #ddd); border-radius: 8px;
      }
      .empty code {
        background: var(--code-editor-background-color, #f5f5f5);
        padding: 2px 4px; border-radius: 3px;
      }
    `, mobileBase];
  }

  constructor() {
    super();
    this._listeners = [];
    this._loading = true;
    this._filterQuery = "";
  }

  connectedCallback() {
    super.connectedCallback();
    this._load();
  }

  async _load() {
    this._loading = true;
    try {
      const result = await this.hass.callWS({ type: "sberhome/listeners/list" });
      this._listeners = result.listeners || [];
      this.dispatchEvent(
        new CustomEvent("listeners-count", {
          detail: { count: this._listeners.length },
        })
      );
    } catch (err) {
      console.error("Failed to load sberhome listeners", err);
      this._listeners = [];
    } finally {
      this._loading = false;
    }
  }

  _filterText(l) {
    const q = this._filterQuery.trim().toLowerCase();
    if (!q) return true;
    return l.slug.toLowerCase().includes(q) || l.name.toLowerCase().includes(q);
  }

  _summarize(filter) {
    const parts = [];
    if (filter.trigger_types?.length) parts.push(`trigger=${filter.trigger_types.join("/")}`);
    if (filter.scenario_name) parts.push(`name="${filter.scenario_name}"`);
    if (filter.scenario_id) parts.push(`id=${filter.scenario_id.slice(0, 8)}…`);
    if (filter.home_id) parts.push(`home=${filter.home_id.slice(0, 8)}…`);
    return parts.join(" · ") || "(no filter)";
  }

  render() {
    if (this._loading) return html`<p>Loading…</p>`;
    const visible = this._listeners.filter((l) => this._filterText(l));

    if (this._listeners.length === 0) {
      return html`
        <div class="empty">
          <p>Listeners не настроены.</p>
          <p>Добавьте в <code>configuration.yaml</code>:</p>
          <pre style="text-align: left; display: inline-block;">sberhome:
  listeners:
    - slug: morning_time
      name: "Утренние time-сценарии"
      filter:
        trigger_type: TIME</pre>
        </div>
      `;
    }

    return html`
      <div class="header">
        <div class="filter">
          <input
            type="text"
            placeholder="Filter by slug/name…"
            .value=${this._filterQuery}
            @input=${(e) => (this._filterQuery = e.target.value)}
          />
        </div>
        <span class="badge">read-only · YAML-managed</span>
      </div>

      ${visible.map(
        (l) => html`
          <div class="card">
            <div class="card-header">
              <div>
                <div class="name">⚡ ${l.name}</div>
                <div class="slug">${l.slug}</div>
              </div>
              ${l.enabled
                ? html`<span class="badge">enabled</span>`
                : html`<span class="badge disabled">disabled</span>`}
            </div>
            <div class="filter-summary">${this._summarize(l.filter)}</div>
            ${l.description ? html`<div class="desc">${l.description}</div>` : ""}
            <div class="meta">
              last fired: ${l.last_fired_at || "never"}
            </div>
          </div>
        `
      )}
    `;
  }
}

customElements.define("sberhome-listeners-view", SberhomeListenersView);
