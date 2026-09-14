/**
 * SberHome — Status card: health verdict, polling, WebSocket, tokens, errors.
 *
 * Сверху — оценка здоровья с причинами (из `health.py`): раньше пользователь
 * сам сводил счётчики в вывод, и «3 ошибки за сессию» одинаково выглядели
 * при единичном сбое час назад и при недоступном облаке сейчас.
 */

import { LitElement, html, css } from "../lit-base.js";
import { mobileBase } from "../mobile-css.js";
import { Localized } from "../i18n/index.js";

export class SberHomeStatusCard extends Localized(LitElement) {
  static get properties() {
    return { hass: { type: Object }, status: { type: Object } };
  }

  _lang() {
    return (this.hass && this.hass.language) || undefined;
  }

  _fmtTs(ts) {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleString(this._lang());
  }

  _fmtRelative(ts) {
    if (!ts) return this.t("status.never");
    const diff = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (diff < 60) return this.t("status.seconds_ago", { n: diff });
    if (diff < 3600) return this.t("status.minutes_ago", { n: Math.floor(diff / 60) });
    return this.t("status.hours_ago", { n: Math.floor(diff / 3600) });
  }

  /** Текст одной причины здоровья по её коду и параметрам. */
  _issueText(issue) {
    const params = { ...issue.params };
    if (issue.code === "token_expiring") params.token = this.t(`status.token_${issue.params.token}`);
    return this.t(`health.issue.${issue.code}`, params);
  }

  static get styles() {
    return [css`
      :host { display: block; padding: 16px; }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr));
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
      .health { margin-bottom: 16px; }
      .health-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
      .badge {
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
      }
      .badge.healthy { background: rgba(76, 175, 80, 0.15); color: var(--success-color, #4caf50); }
      .badge.degraded { background: rgba(255, 152, 0, 0.15); color: var(--warning-color, #ff9800); }
      .badge.unhealthy { background: rgba(244, 67, 54, 0.15); color: var(--error-color, #f44336); }
      .issues { margin: 8px 0 0; padding-left: 20px; }
      .issues li { margin: 2px 0; }
      .issues li.error { color: var(--error-color, #f44336); }
      .row { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; }
      .label { color: var(--secondary-text-color); }
      .value { font-weight: 500; text-align: right; overflow-wrap: anywhere; }
      .ok { color: var(--success-color, #4caf50); }
      .bad { color: var(--error-color, #f44336); }
      .warn { color: var(--warning-color, #ff9800); }
      .error-text { font-family: monospace; font-size: 12px; overflow-wrap: anywhere; margin-top: 4px; }
    `, mobileBase];
  }

  render() {
    const s = this.status;
    if (!s) {
      return html`<div class="grid"><div class="card">${this.t("status.loading")}</div></div>`;
    }
    const health = s.health || { score: "healthy", issues: [] };
    const selection = s.selection || {};
    const registry = s.registry || {};
    const tokens = s.tokens || {};
    return html`
      <div class="card health">
        <div class="health-head">
          <h3 style="margin:0">${this.t("status.health")}</h3>
          <span class="badge ${health.score}">${this.t(`health.score.${health.score}`)}</span>
        </div>
        ${health.issues.length
          ? html`<ul class="issues">
              ${health.issues.map((issue) => html`<li class=${issue.severity}>${this._issueText(issue)}</li>`)}
            </ul>`
          : ""}
      </div>
      <div class="grid">
        <div class="card">
          <h3>${this.t("status.devices")}</h3>
          <div class="row">
            <span class="label">${this.t("status.devices_total")}</span>
            <span class="value">${s.devices_total}</span>
          </div>
          <div class="row">
            <span class="label">${this.t("status.devices_enabled")}</span>
            <span class="value">${s.devices_enabled}</span>
          </div>
          ${selection.stored !== null && selection.stored !== undefined
            ? html`<div class="row">
                <span class="label">${this.t("status.selection_resolved")}</span>
                <span class="value ${selection.unresolved ? "warn" : ""}">${selection.resolved} / ${selection.stored}</span>
              </div>`
            : ""}
          ${registry.last_prune_removed
            ? html`<div class="row">
                <span class="label">${this.t("status.pruned")}</span>
                <span class="value">${registry.last_prune_removed}</span>
              </div>`
            : ""}
        </div>

        <div class="card">
          <h3>${this.t("status.polling")}</h3>
          <div class="row">
            <span class="label">${this.t("status.interval")}</span>
            <span class="value">${this.t("status.seconds", { n: s.polling?.interval_seconds ?? "—" })}</span>
          </div>
          <div class="row">
            <span class="label">${this.t("status.last")}</span>
            <span class="value">${this._fmtRelative(s.polling?.last_at)}</span>
          </div>
          <div class="row">
            <span class="label">${this.t("status.requests")}</span>
            <span class="value">${s.polling?.count ?? 0}</span>
          </div>
          <div class="row">
            <span class="label">${this.t("status.state")}</span>
            <span class="value ${s.polling?.last_success ? "ok" : "bad"}">
              ${s.polling?.last_success ? this.t("status.ok") : this.t("status.failing")}
            </span>
          </div>
          ${(s.background_polls || []).filter((p) => p.state === "failed").map((p) => html`
            <div class="row">
              <span class="label">${this.t("status.poll_failed", { name: p.name })}</span>
              <span class="value warn">${this.t("status.poll_stopped")}</span>
            </div>
            ${p.error ? html`<div class="error-text">${p.error}</div>` : ""}`)}
          ${(s.background_polls || []).some((p) => p.state === "unsupported")
            ? html`<div class="row">
                <span class="label">${this.t("status.polls_unsupported")}</span>
                <span class="value">${s.background_polls.filter((p) => p.state === "unsupported").map((p) => p.name).join(", ")}</span>
              </div>`
            : ""}
        </div>

        <div class="card">
          <h3>${this.t("status.websocket")}</h3>
          <div class="row">
            <span class="label">${this.t("status.state")}</span>
            <span class="value ${s.ws?.connected ? "ok" : "bad"}">
              ${s.ws?.connected ? this.t("status.connected") : this.t("status.disconnected")}
            </span>
          </div>
          <div class="row">
            <span class="label">${this.t("status.messages")}</span>
            <span class="value">${s.ws?.message_count ?? 0}</span>
          </div>
          <div class="row">
            <span class="label">${this.t("status.last")}</span>
            <span class="value">${this._fmtRelative(s.ws?.last_message_at)}</span>
          </div>
        </div>

        <div class="card">
          <h3>${this.t("status.tokens")}</h3>
          ${["sberid", "companion", "smart_home"]
            .filter((name) => tokens[`${name}_expires_at`])
            .map((name) => html`<div class="row">
              <span class="label">${this.t(`status.token_${name}`)}</span>
              <span class="value">${this._fmtTs(tokens[`${name}_expires_at`])}</span>
            </div>`)}
        </div>

        <div class="card">
          <h3>${this.t("status.errors")}</h3>
          <div class="row">
            <span class="label">${this.t("status.errors_session")}</span>
            <span class="value ${s.error_count > 0 ? "bad" : "ok"}">${s.error_count}</span>
          </div>
          ${s.consecutive_failures
            ? html`<div class="row">
                <span class="label">${this.t("status.errors_in_a_row")}</span>
                <span class="value bad">${s.consecutive_failures}</span>
              </div>`
            : ""}
          ${s.last_error
            ? html`<div class="row">
                  <span class="label">${this.t("status.last_error")}</span>
                  <span class="value">${this._fmtRelative(s.last_error.at)}</span>
                </div>
                <div class="error-text">${s.last_error.kind}: ${s.last_error.message}</div>`
            : ""}
        </div>
      </div>
    `;
  }
}

customElements.define("sberhome-status-card", SberHomeStatusCard);
