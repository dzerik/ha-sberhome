# Подтверждение протокола email OTP

Проверено 2026-11-04 без отправки кодов и без входа в аккаунт.

## Источники

- [Issue №80](https://github.com/dzerik/ha-sberhome/issues/80): реальный ответ после
  SMS содержит единственный `email_otp` с `initialization_required: true`.
- Публичная страница `https://online.sberbank.ru/CSAFront/oidc/authorize.do`
  загружает официальный клиент Sber ID **r-97.0.0** и указывает
  `uapiV2Enabled: true`, `uapiV2Url: /CSAFront/uapi/v2`.
- [Официальный JS-клиент](https://esa-res.online.sberbank.ru/ESA/sberid/r-97.0.0/bundle.js):
  обработчик email-формы, её инициализация и общие построители запросов.

Код стороннего клиента в репозиторий не копируется. Ниже — описание контракта,
а не дамп пользовательской сессии.

## Наблюдаемая логика клиента

1. Проверка SMS отправляет `POST /CSAFront/uapi/v2/verify` с
   `identifier.type=ouid` и `authenticator.type=sms_otp`.
2. Ответ с новым `email_otp`, требующим инициализации, переводит клиент на
   отдельный экран email. Отсутствие authcode на этом этапе не является отказом.
3. Email-форма отправляет `POST /CSAFront/uapi/v2/initialize`:
   `identifier={type: ouid, data: {value: <текущий ouid>}}`,
   `authenticator={type: email_otp}`, `channel={type: web, data: ...}`.
   Общие данные channel включают `rsa_data`; существующий независимый клиент
   уже использует этот канал и заголовок `Referer: SD`.
4. Ответ initialize содержит **объект** `authenticator` с `type`, `lifetime`
   и `data.emails`; если ответ содержит новый `ouid`, клиент заменяет текущий.
5. Email-код отправляется тем же `POST /verify` с `authenticator.type=email_otp`
   и `authenticator.data.value=<код>`, используя текущий ouid.
6. Финальный authcode извлекается существующим обработчиком завершения.
   `response_data.toc` используется клиентом для признака типа пользователя,
   а не как идентификатор следующего запроса.

Статические коды ошибок клиента включают `no_operation` и `operation_timeout`
(операция больше не доступна) и `invalid_credentials` (неверный фактор).
Точные ответы на ошибку email-кода и истёкшую сессию в живой сессии не снимались;
варианты ответов в тестах являются синтетическими.

## Границы подтверждения

Формат запросов подтверждён опубликованным кодом провайдера. У пользователя нет
аккаунта с email-фактором; совместимость полной цепочки SMS→email→токены
в живой сессии пока не подтверждена. Задача такой проверки остаётся открытой.
