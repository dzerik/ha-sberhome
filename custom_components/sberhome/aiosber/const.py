"""Constants for aiosber.

Endpoints и client IDs, используемые для взаимодействия с Sber
Gateway API.
"""

from __future__ import annotations

from typing import Final

# =============================================================================
# Endpoints
# =============================================================================
# OAuth endpoints — совпадают с теми, что использует sister project
# ha-sberdevices. `id.sber.ru` отвечает «Этот сервис не настроен для
# работы со Сбер ID» для используемого CLIENT_ID — Sber разделил
# identity providers, и companion OAuth остался на online.sberbank.ru.
AUTH_BASE_URL: Final = "https://online.sberbank.ru"
AUTHORIZE_ENDPOINT: Final = f"{AUTH_BASE_URL}/CSAFront/oidc/authorize.do"
TOKEN_ENDPOINT: Final = "https://online.sberbank.ru:4431/CSAFront/api/service/oidc/v3/token"

# Companion token exchange (Sber ID access → smarthome companion token).
# Endpoint: companion.devices.sberbank.ru — отдельный сервис, не gateway.
# Подтверждено через рабочую sister-integration ha-sberdevices.
COMPANION_BASE_URL: Final = "https://companion.devices.sberbank.ru"
COMPANION_TOKEN_PATH: Final = "/v13/smarthome/token"

# Канал настроек StarOS-устройств (колонки) — тот же companion-хост, но
# авторизация Authorization: Bearer <companion access token>, НЕ X-AUTH-jwt.
# Поле screen со значением null сервер не принимает — за это отвечает
# omit_none при сериализации тела запроса.
COMPANION_STAROS_DEVICES_PATH: Final = "/v18/devices"
COMPANION_STAROS_SETTINGS_PATH: Final = "/v18/devices/settings"
COMPANION_STAROS_SETTINGS_SET_PATH: Final = "/v18/devices/settings/device"

# Poll-интервал канала настроек колонок. Настройки меняются из приложения
# Сбера, и пользователь ждёт, что правки подтянутся в HA без часовой задержки,
# поэтому опрашиваем раз в 10 минут (канал лёгкий). Мгновенно — по кнопке
# «Обновить» (ws_force_refresh → async_refresh_staros, мимо троттла).
STAROS_SETTINGS_POLL_INTERVAL_SEC: Final = 600

# Gateway REST + WebSocket
GATEWAY_BASE_URL: Final = "https://gateway.iot.sberdevices.ru/gateway/v1"
# WebSocket: path `/v1`, auth через `Authorization: Bearer`, подписка на topic'и
# через query params (см. WebSocketClient).
WEBSOCKET_BASE_URL: Final = "wss://ws.iot.sberdevices.ru/v1"

# Подписки на topic'и через query string ?topic=X&topic=Y (повторяемый параметр).
# Нам реально нужны только три первых: DEVICE_STATE — патч state устройства,
# DEVMAN_EVENT — одноразовые события (button_*, alarm), GROUP_STATE — патч
# state группы (на будущее).
DEFAULT_WS_TOPICS: Final = ("DEVICE_STATE", "DEVMAN_EVENT", "GROUP_STATE")

# device_type ∈ {UNKNOWN, BOX, PORTAL}. UNKNOWN подходит для интеграций, не
# являющихся официальным Sber-устройством.
DEFAULT_WS_DEVICE_TYPE: Final = "UNKNOWN"

# WebSocket keep-alive ping interval.
WS_PING_INTERVAL_S: Final = 15.0

# =============================================================================
# Client IDs
# =============================================================================
# Основной — совпадает с приложением Sber Салют.
DEFAULT_CLIENT_ID: Final = "b1f0f0c6-fcb0-4ece-8374-6b614ebe3d42"
# Альтернативный (на случай блокировки основного)
ALT_CLIENT_ID: Final = "197b98ad-8de4-4a11-a23c-dd5f29caaaea"

# Redirect URI для OAuth (custom scheme приложения)
DEFAULT_REDIRECT_URI: Final = "companionapp://host"

# OAuth scopes — реальный API требует ровно `openid`. Дополнительные scope
# (profile/offline_access) приводят к "invalid_scope" на online.sberbank.ru.
DEFAULT_SCOPES: Final = ("openid",)

# partner_name — show в UI Sber ID браузера. Подтверждено в ha-sberdevices.
DEFAULT_PARTNER_NAME: Final = "Салют! Умный дом"

# =============================================================================
# CSAFront SMS-OTP auth (beta path)
# =============================================================================
# Альтернативный flow: вход через номер телефона + SMS-OTP, минуя
# Sber ID OAuth. Удобен для пользователей у которых стандартный
# `id.sber.ru` flow упал (например блокировка `companionapp://` в браузере).
#
# Этапы:
# 1. POST /CSAFront/uapi/v2/authenticate с phone + PKCE → ouid (SMS отправлен).
# 2. POST /CSAFront/uapi/v2/verify с OTP → authcode.
# 3. POST /CSAFront/api/service/oidc/v3/token с authcode → access + refresh.
# 4. GET /v13/smarthome/token с Bearer → SmartHomeToken (используется как
#    X-AUTH-jwt для Gateway API напрямую).
# 5. Refresh: POST .../token с grant_type=refresh_token (rotation!).
CSAFRONT_AUTHENTICATE_URL: Final = "https://online.sberbank.ru/CSAFront/uapi/v2/authenticate"
CSAFRONT_VERIFY_URL: Final = "https://online.sberbank.ru/CSAFront/uapi/v2/verify"
CSAFRONT_INITIALIZE_URL: Final = "https://online.sberbank.ru/CSAFront/uapi/v2/initialize"
# CSAFRONT_TOKEN_URL = TOKEN_ENDPOINT — reused (тот же endpoint).
CSAFRONT_SMARTHOME_TOKEN_URL: Final = "https://mp-prom.salutehome.ru/v13/smarthome/token"

# Отдельный client_id для CSAFront flow — взят из app-конфига Sber Home.
# Отличается от DEFAULT_CLIENT_ID, который используется для companion-flow.
CSAFRONT_CLIENT_ID: Final = "6835fd63-22c8-4c20-bd4a-2bba906afe5f"
CSAFRONT_REDIRECT_URI: Final = "homuzapp://host"

# auth_method значения для entry.data["auth_method"]
AUTH_METHOD_SBERID: Final = "sberid"
AUTH_METHOD_CSAFRONT: Final = "csafront"

# =============================================================================
# HTTP defaults
# =============================================================================
DEFAULT_USER_AGENT: Final = (
    "Salute+prod%2F24.08.1.15602+%28Android+34%3B+Google+sdk_gphone64_arm64%29"
)
DEFAULT_REQUEST_TIMEOUT_S: Final = 10.0
DEFAULT_CONNECT_TIMEOUT_S: Final = 5.0
DEFAULT_MAX_RETRIES: Final = 1  # один retry после refresh token

# Запас по времени до истечения токена, при котором инициируется refresh.
TOKEN_EXPIRY_LEEWAY_S: Final = 60.0

# =============================================================================
# Russian Trusted Root CA (Минцифры)
# =============================================================================
# Используется для TLS к sberdevices.ru endpoints.
# Срок действия: до 2032-02-27.
ROOT_CA_PEM: Final = """-----BEGIN CERTIFICATE-----
MIIFwjCCA6qgAwIBAgICEAAwDQYJKoZIhvcNAQELBQAwcDELMAkGA1UEBhMCUlUx
PzA9BgNVBAoMNlRoZSBNaW5pc3RyeSBvZiBEaWdpdGFsIERldmVsb3BtZW50IGFu
ZCBDb21tdW5pY2F0aW9uczEgMB4GA1UEAwwXUnVzc2lhbiBUcnVzdGVkIFJvb3Qg
Q0EwHhcNMjIwMzAxMjEwNDE1WhcNMzIwMjI3MjEwNDE1WjBwMQswCQYDVQQGEwJS
VTE/MD0GA1UECgw2VGhlIE1pbmlzdHJ5IG9mIERpZ2l0YWwgRGV2ZWxvcG1lbnQg
YW5kIENvbW11bmljYXRpb25zMSAwHgYDVQQDDBdSdXNzaWFuIFRydXN0ZWQgUm9v
dCBDQTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAMfFOZ8pUAL3+r2n
qqE0Zp52selXsKGFYoG0GM5bwz1bSFtCt+AZQMhkWQheI3poZAToYJu69pHLKS6Q
XBiwBC1cvzYmUYKMYZC7jE5YhEU2bSL0mX7NaMxMDmH2/NwuOVRj8OImVa5s1F4U
zn4Kv3PFlDBjjSjXKVY9kmjUBsXQrIHeaqmUIsPIlNWUnimXS0I0abExqkbdrXbX
YwCOXhOO2pDUx3ckmJlCMUGacUTnylyQW2VsJIyIGA8V0xzdaeUXg0VZ6ZmNUr5Y
Ber/EAOLPb8NYpsAhJe2mXjMB/J9HNsoFMBFJ0lLOT/+dQvjbdRZoOT8eqJpWnVD
U+QL/qEZnz57N88OWM3rabJkRNdU/Z7x5SFIM9FrqtN8xewsiBWBI0K6XFuOBOTD
4V08o4TzJ8+Ccq5XlCUW2L48pZNCYuBDfBh7FxkB7qDgGDiaftEkZZfApRg2E+M9
G8wkNKTPLDc4wH0FDTijhgxR3Y4PiS1HL2Zhw7bD3CbslmEGgfnnZojNkJtcLeBH
BLa52/dSwNU4WWLubaYSiAmA9IUMX1/RpfpxOxd4Ykmhz97oFbUaDJFipIggx5sX
ePAlkTdWnv+RWBxlJwMQ25oEHmRguNYf4Zr/Rxr9cS93Y+mdXIZaBEE0KS2iLRqa
OiWBki9IMQU4phqPOBAaG7A+eP8PAgMBAAGjZjBkMB0GA1UdDgQWBBTh0YHlzlpf
BKrS6badZrHF+qwshzAfBgNVHSMEGDAWgBTh0YHlzlpfBKrS6badZrHF+qwshzAS
BgNVHRMBAf8ECDAGAQH/AgEEMA4GA1UdDwEB/wQEAwIBhjANBgkqhkiG9w0BAQsF
AAOCAgEAALIY1wkilt/urfEVM5vKzr6utOeDWCUczmWX/RX4ljpRdgF+5fAIS4vH
tmXkqpSCOVeWUrJV9QvZn6L227ZwuE15cWi8DCDal3Ue90WgAJJZMfTshN4OI8cq
W9E4EG9wglbEtMnObHlms8F3CHmrw3k6KmUkWGoa+/ENmcVl68u/cMRl1JbW2bM+
/3A+SAg2c6iPDlehczKx2oa95QW0SkPPWGuNA/CE8CpyANIhu9XFrj3RQ3EqeRcS
AQQod1RNuHpfETLU/A2gMmvn/w/sx7TB3W5BPs6rprOA37tutPq9u6FTZOcG1Oqj
C/B7yTqgI7rbyvox7DEXoX7rIiEqyNNUguTk/u3SZ4VXE2kmxdmSh3TQvybfbnXV
4JbCZVaqiZraqc7oZMnRoWrXRG3ztbnbes/9qhRGI7PqXqeKJBztxRTEVj8ONs1d
WN5szTwaPIvhkhO3CO5ErU2rVdUr89wKpNXbBODFKRtgxUT70YpmJ46VVaqdAhOZ
D9EUUn4YaeLaS8AjSF/h7UkjOibNc4qVDiPP+rkehFWM66PVnP1Msh93tc+taIfC
EYVMxjh8zNbFuoc7fzvvrFILLe7ifvEIUqSVIC/AzplM/Jxw7buXFeGP1qVCBEHq
391d/9RAfaZ12zkwFsl+IKwE/OZxW8AHa9i1p4GO0YSNuczzEm4=
-----END CERTIFICATE-----"""

# Official distribution: http://nuc-cdp.digital.gov.ru/cdp/subca_ssl_rsa2024.crt
# Issued by the ROOT_CA_PEM above; valid until 2029-07-19.
# SHA-256: 2155785036c900dbb5f1bb2a1569c80c55595bd6bf94867a29bbddbc7d88a3f2
RUSSIAN_TRUSTED_SUB_CA_PEM: Final = """-----BEGIN CERTIFICATE-----
MIIG6DCCBNCgAwIBAgICEAUwDQYJKoZIhvcNAQELBQAwcDELMAkGA1UEBhMCUlUx
PzA9BgNVBAoMNlRoZSBNaW5pc3RyeSBvZiBEaWdpdGFsIERldmVsb3BtZW50IGFu
ZCBDb21tdW5pY2F0aW9uczEgMB4GA1UEAwwXUnVzc2lhbiBUcnVzdGVkIFJvb3Qg
Q0EwHhcNMjQwNzE1MTI1MDQxWhcNMjkwNzE5MTI1MDQxWjBvMQswCQYDVQQGEwJS
VTE/MD0GA1UECgw2VGhlIE1pbmlzdHJ5IG9mIERpZ2l0YWwgRGV2ZWxvcG1lbnQg
YW5kIENvbW11bmljYXRpb25zMR8wHQYDVQQDDBZSdXNzaWFuIFRydXN0ZWQgU3Vi
IENBMIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEA1j0rkZECOt1S8o7I
JY+4YKAxuEa5xaHKHXT2EpkuC/0krqMOjUy2oPIRNgR5g8X0Jl6jamxeGLc4Q1tf
ju6or9oSRYThIUhRsFDQNBiBBEXoBgWxTfiKB2eyT97+pz5TBtBiRCPaLGRHYLRb
9Jz2HkJlxbtNPjtDrF5DPHym+mZ1M1z3hIQYAqJwLpsEBnsw/VxWMlxqHoeewd0h
uJMd71KQ5vOKlz7KrIZ6EobNNa6wItuvsfj3kYCK7O78uLHGXXFxdr8Hae9lMUmC
8F7AFwa+bO1LRlTlqW7rE3rLf+jj70N01N8T3o22v14YBaFBWQWncAVYD2JuL3tH
252+kdNOERf1fLbLRigJAbd+hOhWYlNf963TFDgnNPliHNIW72SygVBnI2V3JwO1
dp1hVKpK/zt8ziGdHW4gmOLTsH50YKdR4jNqUgQv4wASlKn9OpN6zHYc5G8h86fY
BM+zxE5ikGI+I/vIqBuI0eaDU92AWN/YjFLpu8tMu9kLRSCf1vug6FIfDPWVo7iP
ac/SI2v8jnnpaW7ph/Pz3WkzaG7ZZJsfFs+8dploWc6LOoDtbFBhMdGMxu024msC
0PSjZb5ODXPIaO2NsA7fMiAtZcoK6anTUJh4zOP/stA9qsJGNxdrEmiPXSmBZY/N
Y0wkZgZ6JTDhw7038bPvctkblJkCAwEAAaOCAYswggGHMB0GA1UdDgQWBBR3Pdk5
r0K93FvKduru/c4+YSkwXzAfBgNVHSMEGDAWgBTh0YHlzlpfBKrS6badZrHF+qws
hzAOBgNVHQ8BAf8EBAMCAYYwEgYDVR0TAQH/BAgwBgEB/wIBADCBmAYIKwYBBQUH
AQEEgYswgYgwQAYIKwYBBQUHMAKGNGh0dHA6Ly9udWMtY2RwLnZvc2tob2QucnUv
Y2RwL3Jvb3RjYV9zc2xfcnNhMjAyMi5jcnQwRAYIKwYBBQUHMAKGOGh0dHA6Ly9u
dWMtY2RwLmRpZ2l0YWwuZ292LnJ1L2NkcC9yb290Y2Ffc3NsX3JzYTIwMjIuY3J0
MIGFBgNVHR8EfjB8MDqgOKA2hjRodHRwOi8vbnVjLWNkcC52b3NraG9kLnJ1L2Nk
cC9yb290Y2Ffc3NsX3JzYTIwMjIuY3JsMD6gPKA6hjhodHRwOi8vbnVjLWNkcC5k
aWdpdGFsLmdvdi5ydS9jZHAvcm9vdGNhX3NzbF9yc2EyMDIyLmNybDANBgkqhkiG
9w0BAQsFAAOCAgEAmsINXtQ7wwUWvIeOr80MdJS/5G4xhyZOVEmeUorThquT672y
cCg3XCxc4fwbiZqSSbBqntQ7RtiTAKMYMvBageKoVHbzz+R4jX01tKcTx8cDePrz
dJ73bLNUorE7RU9QsW4KyiUeRmjMDV23AUlEvuQFTwgkHXvbac1BBdPn9CrssQuF
5EGohZKcQPFiAAc4SHbRNhlr7uAwgpc/erzI9EAcvA6BVAXcVKoeGpV01uexUgZ6
St5RP9UmDWNA7T4yVXWJ233N0Q8bl+6AswINQ3PosPu6yQQHQjr65YS06epK+AeI
6j+oGR4xI7EhTQhQvaobnGmX/8QQ7XDRYCP2HXYxiffnn/CfZ/BVyKLYeY1ZipjE
nzqdQIC2+Q3WtY8jsVRQMP38WFRmtsIt5snehnPTs5bKGVIcYzj3o3Ex/K7agEz0
zAJ0JR5ivXZOvNkT0g9x1v+S1IkU3e/nX1a+tpRquMtnHX0L2lXArNHUbaOO9EJt
d57WaIpofV5cVhhwShOgAuBc9UMJF3/n4t4RKiPxtsK8P67gcmphMhslj7AMYrYM
ej2NvQZY4m3ub3CPC/PrTjDONvb+8g5xrKtxBjYqC74HSB4dg9G3WimSDUuP2Su6
G2y2TUeyJuCvCLz289VoO0vg7cNdMobE3KCqAiiNhN2VBFxHAUKmUoRcRdw=
-----END CERTIFICATE-----"""
"""Russian Trusted Sub CA needed when the gateway omits its intermediate."""

SBER_CA_BUNDLE_PEM: Final = f"{ROOT_CA_PEM}\n{RUSSIAN_TRUSTED_SUB_CA_PEM}"
"""Sber CA chain loaded in addition to the operating system's trusted CAs."""
