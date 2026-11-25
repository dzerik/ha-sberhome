## Context

Подтверждены четыре действующих ключа config entry: token, companion_tokens,
csafront_tokens, companion_settings_tokens. Дополнительно удаляется reserved
sberid_tokens. CSAFront bundle включает client_uuid, телефон и оба вида токенов.
ConfigFlow уже проверяет прежний unique_id и обновляет существующую запись.
async_remove закрывает клиентов незавершённого входа; coordinator.async_shutdown
останавливает WS, polling, intents и закрывает общий HTTP transport.

## Goals / Non-Goals

Полный локальный сброс этих credentials с сохранением identity и настроек.
Серверный logout, очистка cookies браузера и переключение способа/аккаунта вне scope.
Резервные копии HA являются историей пользователя и этим действием не переписываются.

## Decisions

Options init становится меню: настройки подключения и сброс авторизации.
Существующая форма переходит в settings. reset_auth — отдельное подтверждение;
закрытие ничего не меняет. После успешной выгрузки под setup_lock прекращаются
auth flows только этой записи, атомарно удаляются credential keys и повышается
несекретный auth_generation. Сохраняются auth_method и unique_id.
Старые token stores/reauth flows сверяют поколение перед чтением/записью.
Клиенты flow, включая короткоживущую проверку gateway, отслеживаются сразу
после создания и закрываются при async_remove. Флаг removed и проверки
после ожиданий не дают старой операции заново зарегистрировать вход.
Начальный reauth проверяет поколение entry_data, пока framework удерживает
reauth lock: невидимый во время сброса старый flow завершается, новый запускается.
Для legacy записи unique_id восстанавливается из token.id_token.sub или SMS
phone до очистки. Если identity неизвестна, credentials и подключение сохраняются.
Очистка не запускает обычный options reload: options не меняются, используется
штатный entry.async_start_reauth. Отсутствующие токены после рестарта требуют reauth.

## Validation plan

1. RED: HA options reset для обоих способов, отмена и unload failure;
   stale stores после очистки/нового входа; существующий reauth закрывается.
2. GREEN: меню, подтверждение, token generation, guards в config flow.
3. Настоящий HA lifecycle поверх FakeCloud: остановлены HTTP/WS/polling,
   registry/options сохраняются; missing credentials снова требуют вход.
4. Тесты штатного входа прежним/чужим аккаунтом и всех локализаций.
5. Полный pytest >=99%, Ruff, mypy, strict OpenSpec, независимый review.

На живом HA сброс credentials не выполняется: он требует нового интерактивного входа.
Код может быть установлен обычным SSH/tar.gz деплоем без запуска сброса.
