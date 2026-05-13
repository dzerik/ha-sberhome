/**
 * Shared mobile-CSS baseline для всех view-компонентов панели.
 *
 * Импортируется в каждый компонент:
 *
 *   import { mobileBase } from "../mobile-css.js";
 *   static get styles() {
 *     return [css`...own styles...`, mobileBase];
 *   }
 *
 * Дополняет (не заменяет) собственные мобильные правила компонента.
 * Использует `:host` селектор, поэтому работает через shadow DOM
 * границу каждого LitElement без необходимости в global CSS.
 *
 * Breakpoint 768px — захватывает планшеты в portrait + телефоны.
 */

import { css } from "./lit-base.js";

export const mobileBase = css`
  @media (max-width: 768px) {
    /* Базовый padding контейнера-view (если он рисует свой). */
    :host {
      --sberhome-mobile-padding: 8px;
    }

    /* Стандартные flex-контейнеры (toolbar/header/filters/row)
       автоматически переносятся на новую строку при нехватке места. */
    .toolbar,
    .header,
    .filters,
    .row,
    .actions,
    .controls {
      flex-wrap: wrap;
      gap: 8px;
    }

    /* Формы — уменьшенный font для inline-форм. */
    input,
    select,
    textarea {
      font-size: 13px;
    }
    input[type="search"],
    input[type="text"],
    textarea {
      min-width: 0;
    }
    /* Кнопки сохраняют тач-target минимум 36px высоту */
    button {
      font-size: 13px;
      min-height: 36px;
    }

    /* Длинные коды и log-pre блоки — горизонтальный скролл,
       чтобы не растягивали layout. */
    pre,
    code {
      font-size: 11px;
      max-width: 100%;
      overflow-x: auto;
      word-break: break-word;
      white-space: pre-wrap;
    }

    /* Generic table — компактный font, allow horizontal scroll
       внутри родительского wrapper'а если он есть. */
    table {
      font-size: 12px;
    }
    th,
    td {
      padding: 6px 8px;
    }
  }
`;
