/** Recursive condition editor; nodes retain their own untouched wire metadata. */
import {LitElement, html, css} from "../lit-base.js";
const version = new URL(import.meta.url).searchParams.get("v") || "";
const {Localized} = await import(`../i18n/index.js${version ? `?v=${version}` : ""}`);
const KINDS = ["device", "check_device", "check_scenario", "group"];
const OPERATORS = ["EQUAL", "NOT_EQUAL", "GREATER", "LESS", "GREATER_OR_EQUAL", "LESS_OR_EQUAL"];
const SYMBOLS = ["=", "≠", ">", "<", "≥", "≤"];
const STATE_TYPES = ["BOOL", "INTEGER", "FLOAT", "ENUM", "COLOR", "STRING"];

function validShape(relation, children) {
  const kinds = children.filter((c) => !c.unknown).map((c) => c.type);
  if (relation === "AND") return kinds.filter((k) => k === "device").length === 1
    && kinds.every((k) => ["device", "check_device", "check_scenario", "unknown"].includes(k));
  return relation === "OR" && kinds.every((k) => ["device", "group", "unknown"].includes(k));
}

export function conditionError(node, depth = 0, count = {value: 0}) {
  if (!node || typeof node !== "object") return true;
  if (depth > 8 || ++count.value > 64) return true;
  if (node.unknown || node.type === "unknown") {
    return !node.data?.raw || typeof node.data.raw !== "object" || Array.isArray(node.data.raw);
  }
  const d = node.data || {};
  const text = (v) => typeof v === "string" && !!v.trim();
  if (node.type === "group") {
    return !["AND", "OR"].includes(d.relation) || !Array.isArray(d.conditions)
      || !d.conditions.length || d.conditions.some((child) => conditionError(child, depth + 1, count))
      || !validShape(d.relation, d.conditions);
  }
  if (["device", "check_device"].includes(node.type)) {
    return !text(d.device_id) || !text(d.attribute?.key) || !STATE_TYPES.includes(d.attribute?.type)
      || !OPERATORS.includes(d.operator || "EQUAL");
  }
  if (node.type === "check_scenario") return !text(d.scenario_id) || !text(d.status);
  return true;
}

export function newCondition(type) {
  const data = type === "group" ? {relation: "AND", conditions: []}
    : type === "check_scenario" ? {scenario_id: "", status: "pending"}
    : {device_id: "", attribute: {}, operator: "EQUAL", delay_seconds: 0, parent_id: "", categories_slugs: []};
  return {type, data, unknown: false};
}

export class SberHomeConditionEditor extends Localized(LitElement) {
  static get properties() {
    return {hass: {}, node: {}, disabled: {type: Boolean}, excludeScenarioId: {}, depth: {type: Number}};
  }
  constructor() {
    super();
    this.node = newCondition("group");
    this.disabled = false;
    this.depth = 0;
  }
  static get styles() {
    return css`
      :host {display:block; min-width:0; color:var(--primary-text-color);}
      .field {margin:0 0 12px; min-width:0;}
      label {display:block; font-size:13px; margin-bottom:6px;}
      select, input[type="text"], input[type="number"] {
        box-sizing:border-box; width:100%; min-width:0; padding:8px; border-radius:6px;
        border:1px solid var(--divider-color); color:inherit; background:var(--primary-background-color);
        font:inherit;
      }
      .child {min-width:0; border:1px solid var(--divider-color); border-radius:8px; padding:10px; margin:12px 0;}
      .row {display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px;}
      .row select {flex:1; width:auto;}
      button {padding:8px; min-height:36px; border:1px solid var(--divider-color); border-radius:6px;
        background:var(--primary-background-color); color:inherit; cursor:pointer;}
      button:disabled {opacity:.5; cursor:default;}
      .help, .unknown {font-size:12px; color:var(--secondary-text-color); overflow-wrap:anywhere;}
      sberhome-attr-form[disabled] {pointer-events:none; opacity:.65;}
      .attribute {overflow:auto;}
      @media(max-width:600px) {.child {padding:8px;} .row {gap:4px;}}
    `;
  }
  _editable() { return !this.disabled && !this.node?.unknown && this.node?.type !== "unknown"; }
  _emit(node) {
    if (!this._editable()) return;
    this.dispatchEvent(new CustomEvent("condition-changed", {detail: {node}, bubbles: true, composed: true}));
  }
  _setField(key, value) {
    const data = {...this.node.data, [key]: value};
    if (key === "device_id") Object.assign(data, {attribute: {}, parent_id: "", categories_slugs: []});
    this._emit({...this.node, data});
  }
  _setChild(index, node) {
    if (!this._editable()) return;
    this._setField("conditions", this.node.data.conditions.map((child, i) => i === index ? node : child));
  }
  _allowedKinds(index = -1) {
    if (this.node.data.relation === "OR") return ["device", "group"];
    const event = this.node.data.conditions.some((c, i) => i !== index && c.type === "device");
    return [...(event ? [] : ["device"]), "check_device", "check_scenario"];
  }
  _changeChildType(index, type) {
    if (!this._editable() || !this._allowedKinds(index).includes(type)) return;
    this._setChild(index, newCondition(type));
  }
  _addChild(type) {
    if (!this._editable()) return;
    if (!this._allowedKinds().includes(type) || this.depth >= 8) return;
    this._setField("conditions", [...this.node.data.conditions, newCondition(type)]);
  }
  _removeChild(index) {
    if (!this._editable()) return;
    this._setField("conditions", this.node.data.conditions.filter((_, i) => i !== index));
  }
  _renderGroup() {
    const d = this.node.data;
    return html`
      <div class="field"><label>${this.t("conditions.relation")}</label>
        <select ?disabled=${this.disabled} @change=${(e) => this._setField("relation", e.target.value)}>
          ${["AND", "OR"].map((r) => html`<option value=${r} ?selected=${d.relation === r}>${this.t(`conditions.${r.toLowerCase()}`)}</option>`)}
        </select>
      </div>
      <div class="help">${this.t("conditions.group_help")} ${this.t("conditions.structure")}</div>
      ${d.conditions.map((child, i) => html`
        <div class="child">
          <div class="row">
            ${child.unknown || child.type === "unknown" ? "" : html`
              <select ?disabled=${this.disabled} @change=${(e) => this._changeChildType(i, e.target.value)}>
                ${KINDS.map((kind) => html`<option value=${kind} ?selected=${kind === child.type}
                  ?disabled=${!this._allowedKinds(i).includes(kind)}>${this.t(`conditions.${kind}`)}</option>`)}
              </select>`}
            <button ?disabled=${this.disabled} aria-label=${this.t("conditions.remove")}
              @click=${() => this._removeChild(i)}>×</button>
          </div>
          <sberhome-condition-editor .hass=${this.hass} .node=${child} .disabled=${this.disabled}
            .excludeScenarioId=${this.excludeScenarioId} .depth=${this.depth + 1}
            @condition-changed=${(e) => {e.stopPropagation(); this._setChild(i, e.detail.node);}}>
          </sberhome-condition-editor>
        </div>`)}
      <div class="row">
        ${KINDS.map((kind) => html`<button ?disabled=${this.disabled || this.depth >= 8 || !this._allowedKinds().includes(kind)}
          @click=${() => this._addChild(kind)}>+ ${this.t(`conditions.${kind}`)}</button>`)}
      </div>`;
  }
  _renderDevice() {
    const d = this.node.data;
    return html`
      <div class="field"><label>${this.t("conditions.device_label")}</label>
        <sberhome-device-picker-field .hass=${this.hass} .field=${{key: "device_id", multiple: false}}
          .value=${d.device_id} ?disabled=${this.disabled}
          @value-changed=${(e) => this._setField("device_id", e.detail.value)}>
        </sberhome-device-picker-field>
      </div>
      <div class="field"><label>${this.t("conditions.comparison")}</label>
        <select ?disabled=${this.disabled} @change=${(e) => this._setField("operator", e.target.value)}>
          ${OPERATORS.map((op, i) => html`<option value=${op} ?selected=${op === (d.operator || "EQUAL")}>${SYMBOLS[i]}</option>`)}
        </select>
      </div>
      <div class="field attribute"><label>${this.t("conditions.attribute")}</label>
        <sberhome-attr-form .hass=${this.hass} .deviceId=${d.device_id}
          .value=${d.attribute?.key ? [d.attribute] : []} .conditionMode=${true} .disabled=${this.disabled}
          @attributes-change=${(e) => {
            const values = e.detail.attributes || [];
            this._setField("attribute", values.at(-1) || {});
          }}>
        </sberhome-attr-form>
      </div>
      ${this.node.type === "device" ? html`
        <div class="field"><label>${this.t("conditions.delay")}</label>
          <input type="number" min="0" .value=${d.delay_seconds || 0} ?disabled=${this.disabled}
            @input=${(e) => this._setField("delay_seconds", Math.max(0, parseInt(e.target.value, 10) || 0))} />
        </div>` : html`<div class="help">${this.t("conditions.check_help")}</div>`}`;
  }
  render() {
    if (this.node.unknown || this.node.type === "unknown") {
      return html`<div class="unknown">${this.t("conditions.unknown", {type: this.node.data?.raw?.type || "unknown"})}</div>`;
    }
    if (this.node.type === "group") return this._renderGroup();
    if (["device", "check_device"].includes(this.node.type)) return this._renderDevice();
    const d = this.node.data;
    return html`
      <div class="field"><label>${this.t("conditions.scenario_label")}</label>
        <sberhome-scenario-picker-field .hass=${this.hass} .value=${d.scenario_id}
          .excludeId=${this.excludeScenarioId} ?disabled=${this.disabled}
          @value-changed=${(e) => this._setField("scenario_id", e.detail.value)}>
        </sberhome-scenario-picker-field>
      </div>
      <div class="field"><label>${this.t("conditions.status")}</label>
        <input type="text" .value=${d.status || ""} ?disabled=${this.disabled}
          @input=${(e) => this._setField("status", e.target.value)} />
        <div class="help">${this.t("conditions.status_help")}</div>
      </div>`;
  }
}
customElements.define("sberhome-condition-editor", SberHomeConditionEditor);
