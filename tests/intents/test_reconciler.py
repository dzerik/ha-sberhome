"""Tests for intents.reconciler — additive YAML → Sber sync."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.sberhome.aiosber.dto.union import UnionDto
from custom_components.sberhome.intents.marker import build_description
from custom_components.sberhome.intents.reconciler import (
    _resolve_home_id,
    reconcile_intents,
)
from custom_components.sberhome.intents.spec import IntentAction, IntentSpec


def _yaml_spec(name: str, slug: str, phrases=None, actions=None) -> IntentSpec:
    """YAML-loader-style IntentSpec с yaml_slug в raw_extras."""
    return IntentSpec(
        id=None,
        name=name,
        phrases=phrases or [f"фраза {slug}"],
        actions=actions or [IntentAction(type="ha_event_only", data={})],
        enabled=True,
        description="",
        raw_extras={"yaml_slug": slug},
    )


def _sber_spec(
    id_: str, name: str, slug: str | None = None, phrases=None, actions=None
) -> IntentSpec:
    """Sber-side IntentSpec — с HA-managed marker'ом в description если slug задан."""
    return IntentSpec(
        id=id_,
        name=name,
        phrases=phrases or [f"фраза {id_}"],
        actions=actions or [IntentAction(type="ha_event_only", data={})],
        enabled=True,
        description=build_description(slug) if slug else "",
    )


def _make_service(existing: list[IntentSpec]):
    """Mock IntentService — list/create/update."""
    svc = AsyncMock()
    svc.list_intents = AsyncMock(return_value=existing)
    svc.create_intent = AsyncMock(
        side_effect=lambda s: IntentSpec(
            id=f"created-{s.raw_extras.get('yaml_slug')}",
            name=s.name,
            phrases=s.phrases,
            actions=s.actions,
            enabled=s.enabled,
            description=s.description,
            raw_extras=s.raw_extras,
        )
    )
    svc.update_intent = AsyncMock()
    svc.delete_intent = AsyncMock()
    return svc


class TestReconcileCreatePath:
    @pytest.mark.asyncio
    async def test_creates_new_intents(self):
        """YAML с 2 intent'ами, Sber пустой → оба создаются."""
        svc = _make_service(existing=[])
        yamls = [_yaml_spec("Morning", "morning"), _yaml_spec("Evening", "evening")]
        report = await reconcile_intents(svc, yamls)
        assert sorted(report.created) == ["evening", "morning"]
        assert report.updated == []
        assert report.unchanged == []
        assert svc.create_intent.await_count == 2
        # Marker подставлен в description перед отправкой
        sent_descs = [c.args[0].description for c in svc.create_intent.await_args_list]
        assert all("slug=" in d for d in sent_descs)


class TestReconcileUpdatePath:
    @pytest.mark.asyncio
    async def test_updates_when_yaml_changed(self):
        """YAML отличается от Sber-версии → update."""
        existing = [
            _sber_spec("sber-1", "Morning OLD", "morning", phrases=["старая фраза"]),
        ]
        svc = _make_service(existing=existing)
        yamls = [_yaml_spec("Morning NEW", "morning", phrases=["новая фраза"])]
        report = await reconcile_intents(svc, yamls)
        assert report.updated == ["morning"]
        assert report.created == []
        svc.update_intent.assert_awaited_once()
        # ID существующего intent'а передаётся в update
        args = svc.update_intent.await_args
        assert args.args[0] == "sber-1"
        # Имя из YAML
        assert args.args[1].name == "Morning NEW"

    @pytest.mark.asyncio
    async def test_unchanged_skips_update(self):
        """YAML равен Sber → unchanged, никаких HTTP."""
        existing = [
            _sber_spec("sber-1", "Morning", "morning", phrases=["доброе утро"]),
        ]
        svc = _make_service(existing=existing)
        yamls = [_yaml_spec("Morning", "morning", phrases=["доброе утро"])]
        report = await reconcile_intents(svc, yamls)
        assert report.unchanged == ["morning"]
        assert report.updated == []
        assert report.created == []
        svc.update_intent.assert_not_awaited()


class TestReconcileOrphans:
    @pytest.mark.asyncio
    async def test_orphans_not_deleted(self):
        """HA-managed intent в Sber без YAML-counterpart → orphan (NOT deleted)."""
        existing = [
            _sber_spec("sber-orphan", "Old", "old_intent"),
        ]
        svc = _make_service(existing=existing)
        yamls: list[IntentSpec] = []  # пустой YAML
        report = await reconcile_intents(svc, yamls)
        assert report.orphans == ["old_intent"]
        assert report.created == []
        assert report.updated == []
        # Подтверждаем, что delete НЕ вызывался — additive mode.
        svc.delete_intent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_created_ignored(self):
        """Sber-intent без marker — не считается ни orphan'ом, ни managed."""
        user_intent = _sber_spec("sber-user", "User Intent", slug=None)
        svc = _make_service(existing=[user_intent])
        yamls = [_yaml_spec("New", "new_one")]
        report = await reconcile_intents(svc, yamls)
        assert report.orphans == []  # не в managed-by-slug, не orphan
        assert report.created == ["new_one"]


class TestReconcileFailureIsolation:
    @pytest.mark.asyncio
    async def test_failed_one_does_not_block_others(self):
        """Ошибка create в одном intent'е не блокирует обработку других."""
        svc = _make_service(existing=[])
        svc.create_intent.side_effect = [
            RuntimeError("boom"),  # первый — упал
            IntentSpec(id="ok-1", name="B", phrases=["b"], actions=[]),
        ]
        yamls = [_yaml_spec("A", "a"), _yaml_spec("B", "b")]
        report = await reconcile_intents(svc, yamls)
        assert ("a", "boom") in report.failed
        assert "b" in report.created

    @pytest.mark.asyncio
    async def test_list_failure_marks_all_as_failed(self):
        """list_intents упал → все YAML-specs идут в failed."""
        svc = _make_service(existing=[])
        svc.list_intents.side_effect = RuntimeError("list_failed")
        yamls = [_yaml_spec("A", "a"), _yaml_spec("B", "b")]
        report = await reconcile_intents(svc, yamls)
        assert len(report.failed) == 2
        assert all("list_intents failed" in reason for _, reason in report.failed)


# ---------------------------------------------------------------------------
# Home selector tests (YAML `home` / `home_id`)
# ---------------------------------------------------------------------------


HOMES = [
    UnionDto(id="home-main", name="Мой дом"),
    UnionDto(id="home-dacha", name="Дача"),
]


class TestResolveHomeId:
    def test_explicit_id_used_directly(self):
        spec = _yaml_spec("X", "x")
        spec.raw_extras["yaml_home_id"] = "home-explicit"
        home_id, warning = _resolve_home_id(spec, HOMES)
        assert home_id == "home-explicit"
        assert warning is None

    def test_name_resolves_by_exact_match(self):
        spec = _yaml_spec("X", "x")
        spec.raw_extras["yaml_home_name"] = "Дача"
        home_id, warning = _resolve_home_id(spec, HOMES)
        assert home_id == "home-dacha"
        assert warning is None

    def test_name_resolves_case_and_whitespace_tolerant(self):
        spec = _yaml_spec("X", "x")
        spec.raw_extras["yaml_home_name"] = "  ДАЧА  "
        home_id, warning = _resolve_home_id(spec, HOMES)
        assert home_id == "home-dacha"
        assert warning is None

    def test_name_not_found_returns_warning(self):
        spec = _yaml_spec("X", "x")
        spec.raw_extras["yaml_home_name"] = "Несуществующий дом"
        home_id, warning = _resolve_home_id(spec, HOMES)
        assert home_id is None
        assert warning is not None
        assert "Несуществующий дом" in warning

    def test_default_is_first_home(self):
        """Без явного home/home_id — берётся первый дом списка."""
        spec = _yaml_spec("X", "x")
        home_id, warning = _resolve_home_id(spec, HOMES)
        assert home_id == "home-main"
        assert warning is None

    def test_empty_homes_returns_none(self):
        """Если домов нет — пустой результат без warning'а
        (Sber подставит default сам)."""
        spec = _yaml_spec("X", "x")
        home_id, warning = _resolve_home_id(spec, [])
        assert home_id is None
        assert warning is None

    def test_explicit_id_priority_over_name(self):
        """Если оба заданы — id побеждает."""
        spec = _yaml_spec("X", "x")
        spec.raw_extras["yaml_home_id"] = "home-via-id"
        spec.raw_extras["yaml_home_name"] = "Мой дом"
        home_id, _ = _resolve_home_id(spec, HOMES)
        assert home_id == "home-via-id"


class TestReconcileWithHomes:
    @pytest.mark.asyncio
    async def test_default_home_applied_to_new_intent(self):
        svc = _make_service(existing=[])
        yamls = [_yaml_spec("X", "x")]
        await reconcile_intents(svc, yamls, homes=HOMES)
        # В create_intent должен попасть spec с home_id default-дома.
        sent_spec = svc.create_intent.await_args[0][0]
        assert sent_spec.home_id == "home-main"

    @pytest.mark.asyncio
    async def test_explicit_home_name_applied(self):
        svc = _make_service(existing=[])
        spec = _yaml_spec("X", "x")
        spec.raw_extras["yaml_home_name"] = "Дача"
        await reconcile_intents(svc, [spec], homes=HOMES)
        sent_spec = svc.create_intent.await_args[0][0]
        assert sent_spec.home_id == "home-dacha"

    @pytest.mark.asyncio
    async def test_unknown_home_marks_failed_skips_create(self):
        svc = _make_service(existing=[])
        spec = _yaml_spec("X", "x")
        spec.raw_extras["yaml_home_name"] = "Не существует"
        report = await reconcile_intents(svc, [spec], homes=HOMES)
        assert len(report.failed) == 1
        assert report.failed[0][0] == "x"
        assert "Не существует" in report.failed[0][1]
        svc.create_intent.assert_not_awaited()
