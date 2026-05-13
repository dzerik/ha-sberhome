# Security Policy

## Supported versions

Поддерживается **только последняя minor-версия**. Security fix'ы
выпускаются как patch-релизы поверх последнего minor (например, для
найденной уязвимости в 5.7.x будет выпущен 5.7.N+1, для 5.6.x — нет).

| Версия | Поддержка       |
|--------|-----------------|
| 5.7.x  | ✅ active       |
| < 5.7  | ❌ deprecated   |

Обновитесь через HACS → SberHome → Update до текущей актуальной
версии перед сообщением о проблеме.

## Reporting a vulnerability

**НЕ создавайте публичный GitHub issue для security-проблемы.**

Используйте один из приватных каналов:

1. **GitHub Security Advisory (рекомендуется)** —
   откройте https://github.com/dzerik/ha-sberhome/security/advisories/new
   («Report a vulnerability»). Это создаст приватное обсуждение
   между вами и мейнтейнером. GitHub email-уведомит мейнтейнера.

2. **Email** — на адрес владельца репозитория, указанный в
   `git log` коммитов или в профиле maintainer'а.

Что включить в репорт:

- Описание уязвимости и потенциального impact'а.
- Версия интеграции (`manifest.json:version`).
- Шаги воспроизведения или PoC (если есть).
- Предлагаемое исправление (опционально).

### Response time

Best-effort, проект ведётся в свободное время:

- Подтверждение получения: 7 дней.
- Initial assessment: 14 дней.
- Public disclosure после fix'а: согласовывается с reporter'ом
  (обычно после release patch'а).

## Scope

В scope security-репортов:

- **Утечка токенов** (Sber ID OAuth2 / CSAFront SMS-OTP) — например,
  логирование access_token в plain text, передача в third-party
  без TLS, экспозиция через diagnostics.
- **SSRF / RCE** — через payload в HA service-call или WS endpoint.
- **Auth bypass** — обход OAuth-flow / pin code в panel.
- **Privilege escalation** в HA через интеграцию.
- **Dependency vulnerabilities** — CVE в `Authlib`, `httpx`,
  `websockets`, других зависимостях.

Out of scope:

- **Уязвимости в Sber Gateway API** — это не наша поверхность,
  репортите Sber'у напрямую.
- **Социальная инженерия** — фишинговый сайт `id.sber.ru` и т.п.
- **Self-XSS в HA panel** — требует уже скомпрометированный
  HA-аккаунт.

## Security features

- **Token storage** — все Sber токены хранятся в
  `config_entry.data` HA (HA-managed, не plain-text файлы).
- **TLS pinning** — `ssl_context` с Russian Trusted Root CA
  загружен через `ssl.create_default_context(cadata=ROOT_CA_PEM)`
  (см. `aiosber/transport/ssl.py`).
- **Diagnostics redaction** — токены и приватные UUIDs фильтруются
  в `diagnostics.py` перед экспортом.
- **GitHub Dependabot** — еженедельные PR'ы обновления зависимостей
  (см. `.github/dependabot.yml`).
- **Secret scanning push protection** — включено на репо, блокирует
  commit'ы со случайно попавшими токенами.
