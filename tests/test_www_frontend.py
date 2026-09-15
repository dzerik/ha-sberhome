"""Контрактные тесты панели без сборки (``custom_components/sberhome/www``).

JS-раннера у проекта нет, поэтому фронтенд проверяется снаружи, из Python
(и node, если он установлен):

* **Синтаксис** — каждый модуль разбирается как ES-модуль.
* **Классы** — ни один метод не объявлен дважды: второе объявление молча
  заменяет первое (так в мосте Sber MQTT Bridge пропала переподписка).
* **Импорты** — относительные импорты указывают на существующие файлы, а
  именованные импорты — на реальные экспорты.
* **Локализация** — ru и en содержат одинаковые ключи с одинаковыми
  плейсхолдерами, каждый ``this.t("…")`` существует, а каждый код причины
  из ``health.py`` переведён.
* **Настройки** — форма знает ровно те поля, что валидирует бэкенд.
* **Диалоги** — никаких нативных ``alert()`` / ``confirm()``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from custom_components.sberhome.health import HealthInputs, compute_health
from custom_components.sberhome.settings import SETTINGS_DEFAULTS

WWW = Path(__file__).resolve().parents[1] / "custom_components" / "sberhome" / "www"
NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _modules() -> list[Path]:
    """Собственные модули панели (vendored lit исключён)."""
    return sorted(p for p in WWW.rglob("*.js") if "vendor" not in p.parts)


def _ids(paths: list[Path]) -> list[str]:
    return [str(p.relative_to(WWW)) for p in paths]


def _strip_comments(src: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return "\n".join(
        re.sub(r"(?<![:\w\"'`])//.*$", "", line) for line in without_block.splitlines()
    )


def _dicts(tmp_path: Path) -> dict[str, dict[str, str]]:
    """Словари локализации, как их видит браузер."""
    (tmp_path / "dicts.mjs").write_text(
        (WWW / "i18n" / "dicts.js").read_text(encoding="utf-8"), encoding="utf-8"
    )
    driver = tmp_path / "driver.mjs"
    driver.write_text(
        'import { DICTS } from "./dicts.mjs";\nconsole.log(JSON.stringify(DICTS));\n',
        encoding="utf-8",
    )
    out = subprocess.run(
        [NODE, str(driver)], capture_output=True, text=True, check=True, timeout=60
    )  # noqa: S603
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def dicts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, str]]:
    if NODE is None:
        pytest.skip("node is not installed")
    return _dicts(tmp_path_factory.mktemp("i18n"))


# --------------------------------------------------------------------------- #
# Syntax, classes, imports
# --------------------------------------------------------------------------- #


@requires_node
@pytest.mark.parametrize("path", _modules(), ids=_ids(_modules()))
def test_module_parses(path: Path, tmp_path: Path) -> None:
    copy = tmp_path / (path.stem + ".mjs")
    copy.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    proc = subprocess.run([NODE, "--check", str(copy)], capture_output=True, text=True, timeout=60)  # noqa: S603
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("path", _modules(), ids=_ids(_modules()))
def test_no_method_is_declared_twice(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    # One file may hold several classes; methods are compared within each.
    bodies = re.split(r"^(?:export )?class \w+", src, flags=re.MULTILINE)[1:] or [src]
    for body in bodies:
        declarations = re.findall(
            r"^  (static )?(?:async )?(get |set )?(\w+)\(.*\) \{$", body, re.MULTILINE
        )
        duplicated = sorted(
            name for (*_, name), count in Counter(declarations).items() if count > 1
        )
        assert not duplicated, (
            f"{path.name} declares {duplicated} more than once — only the last one runs"
        )


_IMPORT = re.compile(r"""import\s*(?:\{([^}]*)\}\s*from\s*)?["'](\.{1,2}/[^"']+)["']""")


def _exports(src: str) -> set[str]:
    names = set(re.findall(r"export\s+(?:async\s+)?(?:function|class|const|let)\s+(\w+)", src))
    for group in re.findall(r"export\s*\{([^}]*)\}", src):
        names |= {part.split(" as ")[-1].strip() for part in group.split(",") if part.strip()}
    return names


@pytest.mark.parametrize("path", _modules(), ids=_ids(_modules()))
def test_relative_imports_resolve(path: Path) -> None:
    src = _strip_comments(path.read_text(encoding="utf-8"))
    for names, spec in _IMPORT.findall(src):
        target = (path.parent / spec).resolve()
        assert target.is_file(), f"{path.name}: imports {spec}, which does not exist"
        if names.strip():
            wanted = {n.split(" as ")[0].strip() for n in names.split(",") if n.strip()}
            missing = wanted - _exports(target.read_text(encoding="utf-8"))
            assert not missing, f"{path.name}: {spec} does not export {sorted(missing)}"


def test_every_rendered_element_is_defined_somewhere() -> None:
    defined: set[str] = set()
    rendered: dict[str, str] = {}
    for path in _modules():
        src = path.read_text(encoding="utf-8")
        defined |= set(re.findall(r"customElements\.define\(\s*[\"']([a-z0-9-]+)[\"']", src))
        for tag in re.findall(r"<(sberhome-[a-z0-9-]+)\b", src):
            rendered.setdefault(tag, path.name)
    missing = {tag: where for tag, where in rendered.items() if tag not in defined}
    assert not missing, f"rendered but never defined: {missing}"


@pytest.mark.parametrize("path", _modules(), ids=_ids(_modules()))
def test_no_native_dialogs(path: Path) -> None:
    offenders = re.findall(
        r"(?<![\w.$-])(alert|confirm)\s*\(", _strip_comments(path.read_text(encoding="utf-8"))
    )
    assert not offenders, (
        f"{path.name}: native {sorted(set(offenders))}() — use the panel toast/modal"
    )


# --------------------------------------------------------------------------- #
# Localization
# --------------------------------------------------------------------------- #


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_ru_and_en_have_the_same_keys(dicts: dict[str, dict[str, str]]) -> None:
    assert set(dicts["ru"]) == set(dicts["en"]), sorted(set(dicts["ru"]) ^ set(dicts["en"]))


def test_other_languages_only_translate_known_keys(dicts: dict[str, dict[str, str]]) -> None:
    for lang in ("be", "kk", "uz"):
        extra = set(dicts[lang]) - set(dicts["ru"])
        assert not extra, f"{lang} has keys missing from ru: {sorted(extra)}"


def test_placeholders_match_between_languages(dicts: dict[str, dict[str, str]]) -> None:
    for lang, dictionary in dicts.items():
        for key, text in dictionary.items():
            assert _placeholders(text) == _placeholders(dicts["ru"][key]), f"{lang}.{key}"


def test_every_literal_translation_key_exists(dicts: dict[str, dict[str, str]]) -> None:
    missing: list[str] = []
    for path in _modules():
        src = _strip_comments(path.read_text(encoding="utf-8"))
        for key in re.findall(r"\bthis\.t\(\s*[\"']([\w.]+)[\"']", src):
            if key not in dicts["ru"]:
                missing.append(f"{path.name}: {key}")
    assert not missing, missing


def test_every_health_code_and_score_is_translated(dicts: dict[str, dict[str, str]]) -> None:
    worst = compute_health(
        HealthInputs(
            last_update_success=False,
            ws_connected=False,
            consecutive_failures=5,
            token_expiries={"companion": 0.0, "sberid": 0.0, "smart_home": 0.0},
            disabled_polls=["OTA"],
            unresolved_selection=1,
            conflicts=["sberdevices"],
            registry_failures=1,
            now=10.0,
        )
    )
    keys = {f"health.issue.{issue['code']}" for issue in worst["issues"]}
    keys |= {f"health.score.{score}" for score in ("healthy", "degraded", "unhealthy")}
    keys |= {f"status.token_{name}" for name in ("companion", "sberid", "smart_home")}
    missing = sorted(k for k in keys if k not in dicts["ru"])
    assert not missing, missing
    for issue in worst["issues"]:
        text = dicts["ru"][f"health.issue.{issue['code']}"]
        assert _placeholders(text) <= set(issue["params"]), f"{issue['code']}: {text}"


# --------------------------------------------------------------------------- #
# Settings form
# --------------------------------------------------------------------------- #


def test_settings_form_fields_match_the_backend(dicts: dict[str, dict[str, str]]) -> None:
    src = (WWW / "components" / "sberhome-settings.js").read_text(encoding="utf-8")
    block = re.search(r"export const FIELDS = \[(.*?)\];", src, re.DOTALL).group(1)
    fields = re.findall(r'key: "(\w+)"', block)
    assert set(fields) == set(SETTINGS_DEFAULTS)
    for key in fields:
        assert f"settings.field.{key}" in dicts["ru"]
        assert f"settings.hint.{key}" in dicts["ru"]


def test_diagnose_suggests_devices() -> None:
    """Выбор устройства из подсказки вместо вставки device_id вручную."""
    src = (WWW / "components" / "sberhome-diagnose-view.js").read_text(encoding="utf-8")
    assert 'list="diagnose-devices"' in src
    assert '<datalist id="diagnose-devices">' in src
    assert '"sberhome/get_devices"' in src


@pytest.mark.parametrize(
    ("name", "table"),
    [
        ("sberhome-validation-view.js", "issue-table"),
        ("sberhome-replay-view.js", "replay-table"),
        ("sberhome-state-diff-view.js", "delta"),
    ],
)
def test_wide_tables_scroll_inside_their_card(name: str, table: str) -> None:
    """На телефоне таблицы прокручиваются внутри карточки, а не расширяют страницу."""
    src = (WWW / "components" / name).read_text(encoding="utf-8")
    tag = f'<table class="{table}">'
    assert src.count(f'<div class="table-scroll">{tag}') == src.count(tag) > 0
    assert ".table-scroll { overflow-x: auto; }" in src


def test_command_timeline_statuses_are_translated(dicts: dict[str, dict[str, str]]) -> None:
    """Каждый статус трекера, включая send_failed, имеет подпись в панели."""
    import typing

    from custom_components.sberhome.command_tracker import CommandStatus

    for status in typing.get_args(CommandStatus):
        assert f"commands.status.{status}" in dicts["ru"], status
    for via in ("ws_push", "polling"):
        assert f"commands.via.{via}" in dicts["ru"]


def _component(name: str) -> str:
    return (WWW / "components" / name).read_text(encoding="utf-8")


def test_json_block_copy_precedes_the_code() -> None:
    src = _component("sberhome-json-block.js")
    render = src[src.index("  render() {") :]
    assert render.index('this.t("json.copy")') < render.index("<pre")


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("sberhome-replay-view.js", "${this._truncate(m.payload)}"),
        ("sberhome-commands-view.js", "${formatValue(c.keys_sent[k])}"),
    ],
)
def test_cut_json_has_a_copy_button_in_front(name: str, shown: str) -> None:
    """Сокращённый JSON копируется целиком кнопкой, стоящей перед ним."""
    src = _component(name)
    cut = src.index(shown)
    button = src.rfind("<sberhome-copy-button", 0, cut)
    assert button != -1 and src.count("\n", button, cut) <= 1, name
    assert 'import "./sberhome-copy-button.js";' in src


def test_report_copy_opens_the_report() -> None:
    src = _component("sberhome-diagnose-view.js")
    report = src[src.index("  _renderReport(r) {") :]
    assert report.index("diagnose.copy_report") < report.index('class="verdict')
    assert src.count("diagnose.copy_report") == 1


def test_device_raw_json_is_a_block_with_copy_on_top() -> None:
    src = _component("sberhome-device-modal.js")
    raw = src[src.index("  _renderRaw(raw) {") :]
    assert "<sberhome-json-block" in raw.split("\n  }\n")[0]
    assert "Copy JSON</button>" not in src


# --------------------------------------------------------------------------- #
# Backend errors
# --------------------------------------------------------------------------- #


def _backend_error_messages(tmp_path: Path, script: str) -> list[str]:
    """Прогнать ``backendErrorMessage`` из ``i18n/index.js`` в node."""
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    for name in ("index.js", "dicts.js"):
        (tmp_path / name).write_text(
            (WWW / "i18n" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    driver = tmp_path / "driver.js"
    driver.write_text(
        'import { backendErrorMessage } from "./index.js";\n'
        f"{script}\n"
        "console.log(JSON.stringify(out));\n",
        encoding="utf-8",
    )
    proc = subprocess.run(  # noqa: S603
        [NODE, str(driver)], capture_output=True, text=True, check=True, timeout=60
    )
    return json.loads(proc.stdout)


@requires_node
def test_backend_error_is_shown_in_user_language(tmp_path: Path) -> None:
    """Сервис поднимает ошибку с ключом перевода — панель показывает перевод, а не английский."""
    out = _backend_error_messages(
        tmp_path,
        """
const calls = [];
const hass = {
  language: "ru",
  callWS: async (msg) => {
    calls.push(msg);
    return { resources: {
      "component.sberhome.exceptions.command_rejected.message":
        "Облако отклонило команду (HTTP {status}), {missing}",
    } };
  },
};
const out = [
  await backendErrorMessage(hass, {
    message: "The Sber cloud rejected the command (HTTP 400)",
    translation_domain: "sberhome",
    translation_key: "command_rejected",
    translation_placeholders: { status: "400" },
  }),
  await backendErrorMessage(hass, {
    message: "English fallback",
    translation_domain: "sberhome",
    translation_key: "unknown_key",
  }),
  await backendErrorMessage(hass, { message: "extra keys not allowed" }),
  await backendErrorMessage(
    { language: "ru", callWS: async () => { throw new Error("offline"); } },
    { message: "Server text", translation_domain: "sberhome", translation_key: "x" },
  ),
  JSON.stringify(calls[0]),
];
""",
    )

    assert out[0] == "Облако отклонило команду (HTTP 400), {missing}"
    assert out[1] == "English fallback"
    assert out[2] == "extra keys not allowed"
    assert out[3] == "Server text"
    assert json.loads(out[4]) == {
        "type": "frontend/get_translations",
        "language": "ru",
        "category": "exceptions",
        "integration": ["sberhome"],
    }


@requires_node
def test_debug_tab_shows_send_raw_command_error_in_user_language(tmp_path: Path) -> None:
    """Вкладка «Отладка» панели (``<sberhome-debug-view>``) показывает ошибку ``send_raw_command`` переводом.

    Сервис больше не отвечает ``{"ok": false}``, а поднимает исключение с
    ключом перевода; в ``message`` сервер кладёт английский текст. Настоящий
    модуль вкладки запускается в node с заглушками lit и дочерних компонентов.
    """
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "i18n").mkdir()
    (tmp_path / "components").mkdir()
    for name in ("index.js", "dicts.js"):
        (tmp_path / "i18n" / name).write_text(
            (WWW / "i18n" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    view = "components/sberhome-debug-view.js"
    (tmp_path / view).write_text((WWW / view).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "lit-base.js").write_text(
        "export class LitElement {}\nexport const html = () => '';\nexport const css = () => '';\n",
        encoding="utf-8",
    )
    (tmp_path / "mobile-css.js").write_text("export const mobileBase = '';\n", encoding="utf-8")
    for stub in ("sberhome-json-block.js", "sberhome-attr-form.js"):
        (tmp_path / "components" / stub).write_text("export {};\n", encoding="utf-8")
    driver = tmp_path / "driver.js"
    driver.write_text(
        """
const defined = {};
globalThis.customElements = { define: (name, cls) => { defined[name] = cls; } };
globalThis.setTimeout = () => 0;
await import("./components/sberhome-debug-view.js");
const View = defined["sberhome-debug-view"];

function makeView(callService) {
  const view = new View();
  view.hass = {
    language: "ru",
    callService,
    callWS: async () => ({ resources: {
      "component.sberhome.exceptions.command_rejected.message":
        "Облако Сбера отклонило команду (HTTP {status}).",
    } }),
  };
  view._selectedId = "dev1";
  view._payload = '[{"key": "on_off", "type": "BOOL", "bool_value": true}]';
  return view;
}

const failing = makeView(async () => {
  throw {
    code: "service_validation_error",
    message: "Validation error: Sber cloud rejected the command as invalid (HTTP 400).",
    translation_domain: "sberhome",
    translation_key: "command_rejected",
    translation_placeholders: { status: "400" },
  };
});
await failing._send();

const ok = makeView(async () => ({ response: { ok: true, device_id: "dev1" } }));
await ok._send();

console.log(JSON.stringify({
  error: failing._error,
  failingToast: failing._toast,
  sending: failing._sending,
  okError: ok._error,
  okToast: ok._toast,
  okResponse: ok._response,
}));
""",
        encoding="utf-8",
    )
    proc = subprocess.run(  # noqa: S603
        [NODE, str(driver)], capture_output=True, text=True, check=True, timeout=60
    )
    out = json.loads(proc.stdout)

    assert out["error"] == "Облако Сбера отклонило команду (HTTP 400)."
    assert out["failingToast"] == ""
    assert out["sending"] is False
    assert out["okError"] == ""
    assert out["okToast"] == "Отправлено"
    assert out["okResponse"] == {"ok": True, "device_id": "dev1"}
