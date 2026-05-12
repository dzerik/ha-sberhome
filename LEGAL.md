# Правовая позиция проекта

## Что делает проект

`ha-sberhome` — Home Assistant integration, которая позволяет
**конечному пользователю** управлять **собственными устройствами**,
зарегистрированными в его учётной записи Sber Smart Home («Салют!»).
Интеграция работает строго **под управлением пользователя и от его имени**:

- авторизация — собственными учётными данными пользователя
  (Sber ID OAuth через `id.sber.ru` либо SMS-OTP на телефон, привязанный
  к аккаунту пользователя);
- запросы идут с IP пользователя, с его access_token-ом, к публично
  доступному gateway-серверу `gateway.iot.sberdevices.ru`;
- никаких чужих данных, токенов, credentials проект не использует и
  не запрашивает;
- никакого массового scraping'а, прокси-пулов, DoS-нагрузки на
  Sber-серверы интеграция не создаёт.

## Два пути авторизации

### 1. Sber ID OAuth — стандартный путь (документирован Sber)

Использует **публично задокументированные** endpoint'ы:

- `GET https://id.sber.ru/CSAFront/oidc/authorize.do` — OAuth 2.0 / OIDC
  authorization code flow с PKCE.
- `POST https://online.sberbank.ru:4431/CSAFront/api/service/oidc/v3/token`
  — token exchange.

Это **тот же flow**, что использует [официальный Sber ID iOS SDK](https://github.com/SberID/ios-sdk),
[Sber ID JS SDK](https://github.com/SberID/js-sdk) и публично документирован
на developer.sber.ru:

- [Sber ID — параметры запроса](https://api.developer.sber.ru/product/SberbankID/doc/v1/reqparametrs)
- [Sber ID — мобильные параметры](https://developer.sberbank.ru/doc/v1/sberbank-id/reqmobile)
- [Cloud migration checklist](https://developers.sber.ru/docs/ru/sberid/faq/a4-switching-to-cloud)

Этот путь — стандартная партнёрская интеграция через Sber ID, и
правовых вопросов к нему быть не должно.

### 2. SMS-OTP (beta) — путь на основе открытого источника

Альтернативный flow для пользователей, у которых стандартный путь не
работает (блокировка `companionapp://` в браузере, баги мобильного
UA-сниффинга и т.п.):

- `POST /CSAFront/uapi/v2/authenticate` (SMS init);
- `POST /CSAFront/uapi/v2/verify` (OTP → authcode);
- `POST /CSAFront/api/service/oidc/v3/token` (authcode → токены);
- `GET mp-prom.salutehome.ru/v13/smarthome/token` (SmartHomeToken).

Wire-format этих endpoint'ов получен **полностью из открытого
проекта** [shuryak/sberdevices](https://github.com/shuryak/sberdevices)
(Go, MIT-license, публичный с 2023 года). Все endpoint'ы, заголовки,
anti-bot `rsa_data` ритуал, persistent `X-Device-ID`, refresh-rotation
— переиспользованы оттуда без изменений по существу; здесь они
портированы на Python/asyncio.

### Что НЕ использовалось

- Декомпиляция мобильного приложения «Салют!» или его firmware
- Дизассемблирование binary
- Извлечение `.proto`-схем или приватных ключей из APK
- Обход технических средств защиты (TLS-bypass, certificate pinning,
  DRM)
- Cracking паролей или brute-force credentials
- Перехват чужого трафика, MITM
- Несанкционированный доступ — пользователь авторизуется собственными
  credentials

## Правовые основания

### Ст. 1280 ГК РФ (императивная норма)

> «Лицо, правомерно владеющее экземпляром программы для ЭВМ или базы
> данных (пользователь), вправе без разрешения автора или иного
> правообладателя и без выплаты дополнительного вознаграждения...
> изучать, исследовать или испытывать функционирование такой
> программы в целях определения идей и принципов, лежащих в основе
> любого элемента программы для ЭВМ»

Также прямо разрешена **адаптация** программ для совместимости с
другими программами и устройствами.

Норма императивна — не может быть ограничена лицензионным договором.
Подтверждено судебной практикой и юридической экспертизой:
- [zakon.ru — Реверс-инжиниринг ПО и российское право](https://zakon.ru/blog/2016/10/11/reversinzhiniring_i_rossijskoe_pravo)
- [blog.lch.legal — Реверс-инжиниринг: правовое регулирование](https://blog.lch.legal/tproduct/388828150-789941865161-revers-inzhiniring-pravovoe-regulirovani)
- [Хакер — Право на реверс](https://xakep.ru/2016/09/02/reverse-rights/)

Правомерное владение учётной записью «Салют!» — на основании договора
оферты с Sber, заключённого при регистрации пользователем своего
аккаунта.

### EU Software Directive 2009/24/EC, ст. 6

В юрисдикциях EU reverse engineering для **interoperability** прямо
разрешён директивой о правовой охране ПО.

### EFF Coders' Rights — Reverse Engineering FAQ

Электронный фронтир документирует устоявшуюся практику: использование
публично доступных endpoint'ов с собственными авторизационными данными
для interoperability не нарушает CFAA/DMCA при отсутствии circumvention
технических средств защиты.

[EFF Coders' Rights Project Reverse Engineering FAQ](https://www.eff.org/issues/coders/reverse-engineering-faq)

### Лицензионная совместимость

Источник CSAFront wire-format — [shuryak/sberdevices](https://github.com/shuryak/sberdevices)
— распространяется под MIT-license, явно допускающей повторное
использование с сохранением copyright notice. Атрибуция приведена в:
- README.md (раздел «Благодарности»);
- модульной docstring `aiosber/auth/csafront.py`;
- CHANGELOG.md для v5.1.0;
- описании GitHub-релиза v5.1.0.

## Анализ официальных документов SberDevices / Sber

### Правила гарантийного обслуживания

Источник: [sberdevices.ru/legal/warranty_rules](https://sberdevices.ru/legal/warranty_rules)

**п. 1.6**: «Компания **не предоставляет гарантии на совместимость**
приобретаемого Устройства и устройств/программных продуктов, имеющихся
у Потребителя, либо приобретённых им у третьих лиц. Компания **не
несёт ответственности** за повреждения, причинённые устройствам и
программному обеспечению третьих лиц при их совместном использовании
с Устройством.»

**п. 6.1.г–д** упоминают «программное обеспечение сторонних
разработчиков» и «несовместимость с оборудованием стороннего
производства» как основания для отказа в **гарантийном** обслуживании,
но не как запрет использования.

Документ **explicit допускает** использование устройства совместно с
продуктами третьих лиц, оговаривая только границы гарантийных
обязательств.

### Условия использования виртуального ассистента «Салют»

Источник: [salute.sber.ru/salute_terms](https://salute.sber.ru/salute_terms/)

**п. 4.15**: «Пользователю запрещено осуществлять (и/или предпринимать
попытки) копирование, воспроизведение, переработку, распространение...
использование объектного/исходного программного кода» + «пытаться
осуществить имитацию работы функций Виртуального ассистента».

Соглашение распространяется на **виртуального ассистента «Салют»** —
голосовой/NLP-сервис (распознавание речи, ответы на вопросы,
voice-навыки). Проект `ha-sberhome` не имитирует виртуального
ассистента и не задействует его функции:

- интеграция использует REST/WebSocket API устройств, а не Voice/NLP
  endpoints;
- голосовые сценарии, описанные пользователем в приложении «Салют!»,
  по-прежнему выполняются виртуальным ассистентом Sber на cloud-стороне
  — наш проект только **подписывается** на события об их срабатывании
  (через стандартный WebSocket `scenario_widgets`) для возможности
  использования голосовых триггеров в HA-автоматизациях;
- пользователь продолжает взаимодействовать с виртуальным ассистентом
  через колонки/приложение Sber штатным образом.

### Документация Sber Smart Home (C2C партнёрская)

Источник: [developers.sber.ru/docs/ru/smarthome/c2c](https://developers.sber.ru/docs/ru/smarthome/c2c)

Cloud-to-Cloud API адресован **производителям умных устройств**,
желающим выставить свои устройства в Sber Smart Home. Описывает
обратное направление (`Sber → vendor backend`), не подходит для
противоположной задачи — управления пользователем своими устройствами
из стороннего клиента.

Документация не содержит запретов на создание альтернативных клиентов
для взаимодействия пользователя с собственными устройствами.

## Защитные ограничения проекта

Проект сознательно ограничивает себя следующим:

| Ограничение | Зачем |
|---|---|
| Только собственные учётные данные пользователя | Исключает 272/159 УК РФ |
| Только публичные endpoint'ы gateway-сервера | Исключает «обход защиты» |
| Один HA-instance — один аккаунт пользователя | Исключает massive scraping |
| Open-source, некоммерческое распространение | Снимает коммерческий конфликт |
| Атрибуция к источнику wire-format'а (MIT) | Лицензионная совместимость |
| Версионирование, beta-маркировка для нестандартных flow | Прозрачность для пользователя |
| Redaction токенов в diagnostics | Защита приватности пользователя |
| Нет хранения чужих токенов на серверах разработчика | Нет посредничества |

## Позиция

Проект `ha-sberhome`:

- Использует **публично задокументированный** Sber ID OAuth flow в
  качестве основного пути авторизации.
- Для **дополнительного (beta) SMS-OTP пути** wire-format взят из
  открытого источника `shuryak/sberdevices` (MIT) с явной атрибуцией;
  никакая декомпиляция, дизассемблирование, обход технических средств
  защиты не использовались.
- Реализует interoperability между устройствами пользователя и Home
  Assistant — целью, прямо предусмотренной ст. 1280 ГК РФ.
- Не имитирует виртуального ассистента «Салют» и не задействует его
  Voice/NLP-функции.
- Не нарушает положений Правил гарантийного обслуживания SberDevices,
  которые прямо допускают использование устройств совместно с
  продуктами третьих лиц.
- Распространяется AS-IS, без гарантий, не аффилирован с ПАО Сбербанк,
  SberDevices или их дочерними структурами. Право собственности на
  товарные знаки Sber, SberDevices, «Салют», SberHome принадлежит
  правообладателям; их упоминание в документации проекта является
  **nominative use** для обозначения совместимости.

## Контакт

Если вы считаете, что проект нарушает чьи-то права, или у вас есть
вопросы по правовой стороне — пожалуйста, откройте issue в
[трекере проекта](https://github.com/dzerik/ha-sberhome/issues) или
напишите автору. Мы оперативно рассмотрим обращение.

## Источники

- [Гражданский кодекс РФ, ст. 1280](http://www.consultant.ru/document/cons_doc_LAW_64629/8c9a9f3d8867fa53d5a93e3ab07a39e26b1a51a8/)
- [SberDevices: Правила гарантийного обслуживания](https://sberdevices.ru/legal/warranty_rules)
- [SberDevices: Условия продаж](https://sberdevices.ru/legal/sale_terms)
- [Salute Terms — Условия использования виртуального ассистента](https://salute.sber.ru/salute_terms/)
- [Sber Smart Home C2C API documentation](https://developers.sber.ru/docs/ru/smarthome/c2c/api)
- [Sber ID — параметры запроса](https://api.developer.sber.ru/product/SberbankID/doc/v1/reqparametrs)
- [Sber ID iOS SDK (официальный)](https://github.com/SberID/ios-sdk)
- [Sber ID JS SDK (официальный)](https://github.com/SberID/js-sdk)
- [shuryak/sberdevices — источник CSAFront wire-format](https://github.com/shuryak/sberdevices)
- [Реверс-инжиниринг ПО и российское право — zakon.ru](https://zakon.ru/blog/2016/10/11/reversinzhiniring_i_rossijskoe_pravo)
- [Реверс-инжиниринг: правовое регулирование — blog.lch.legal](https://blog.lch.legal/tproduct/388828150-789941865161-revers-inzhiniring-pravovoe-regulirovani)
- [Право на реверс — xakep.ru](https://xakep.ru/2016/09/02/reverse-rights/)
- [EFF Coders' Rights Project Reverse Engineering FAQ](https://www.eff.org/issues/coders/reverse-engineering-faq)
- [EU Directive 2009/24/EC on the legal protection of computer programs](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32009L0024)
