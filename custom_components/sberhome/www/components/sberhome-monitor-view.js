/**
 * SberHome — Monitor tab (Status + Log combined).
 *
 * Верхняя часть — compact status card (integration health, WS connection,
 * token expiry). Под ней — log view (WS messages ring buffer).
 */

import { LitElement, html, css } from "../lit-base.js";

class SberHomeMonitorView extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      status: { type: Object },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
    `;
  }

  render() {
    return html`
      <sberhome-status-card .status=${this.status}></sberhome-status-card>
      <sberhome-diagnose-view .hass=${this.hass}></sberhome-diagnose-view>
      <sberhome-state-diff-view .hass=${this.hass}></sberhome-state-diff-view>
      <sberhome-commands-view .hass=${this.hass}></sberhome-commands-view>
      <sberhome-validation-view .hass=${this.hass}></sberhome-validation-view>
      <sberhome-replay-view .hass=${this.hass}></sberhome-replay-view>
      <sberhome-log-view .hass=${this.hass}></sberhome-log-view>
    `;
  }
}

customElements.define("sberhome-monitor-view", SberHomeMonitorView);
