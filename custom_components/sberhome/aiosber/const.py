"""Constants for aiosber.

Endpoints, client IDs, root CA. Источник истины — реверс APK
`com.salute.smarthome.prod` v26.03.1.18015 (см. research_docs/01-rest-api.md).
"""

from __future__ import annotations

from typing import Final

# =============================================================================
# Endpoints
# =============================================================================
# OAuth — рабочие endpoints из ha-sberdevices (sister project).
# `id.sber.ru` отдаёт «Этот сервис не настроен для работы со Сбер ID» для
# нашего CLIENT_ID (Salute). Sber разделил identity providers — companion
# OAuth остался на старом online.sberbank.ru.
AUTH_BASE_URL: Final = "https://online.sberbank.ru"
AUTHORIZE_ENDPOINT: Final = f"{AUTH_BASE_URL}/CSAFront/oidc/authorize.do"
TOKEN_ENDPOINT: Final = "https://online.sberbank.ru:4431/CSAFront/api/service/oidc/v3/token"

# Companion token exchange (Sber ID access → smarthome companion token).
# Endpoint: companion.devices.sberbank.ru — отдельный сервис, не gateway.
# Подтверждено через рабочую sister-integration ha-sberdevices.
COMPANION_BASE_URL: Final = "https://companion.devices.sberbank.ru"
COMPANION_TOKEN_PATH: Final = "/v13/smarthome/token"

# Gateway REST + WebSocket
GATEWAY_BASE_URL: Final = "https://gateway.iot.sberdevices.ru/gateway/v1"
WEBSOCKET_BASE_URL: Final = "wss://ws.iot.sberdevices.ru"

# =============================================================================
# Client IDs
# =============================================================================
# Основной — совпадает с приложением Sber Салют.
DEFAULT_CLIENT_ID: Final = "b1f0f0c6-fcb0-4ece-8374-6b614ebe3d42"
# Альтернативный (на случай блокировки основного)
ALT_CLIENT_ID: Final = "197b98ad-8de4-4a11-a23c-dd5f29caaaea"

# Redirect URI для OAuth (custom scheme приложения)
DEFAULT_REDIRECT_URI: Final = "companionapp://host"

# OAuth scopes
DEFAULT_SCOPES: Final = ("openid", "profile", "offline_access")

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
