"""Tests for intents.reconciler — additive YAML → Sber sync."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.sberhome.intents.marker import build_description
from custom_components.sberhome.intents.reconciler import reconcile_intents
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
