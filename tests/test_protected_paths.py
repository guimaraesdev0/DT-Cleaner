"""LAYER 3: paths the user registered as untouchable."""

from __future__ import annotations

import json
from pathlib import Path

from dtcleaner.core.config import AppConfig, ConfigStore
from dtcleaner.core.safety import SafetyEngine


def test_adding_a_path_protects_everything_inside(tmp_path: Path) -> None:
    project = tmp_path / "client-project"
    (project / "node_modules").mkdir(parents=True)

    config = AppConfig()
    assert config.add_protected(project) is True
    assert config.is_protected(project / "node_modules") is True


def test_sibling_with_a_shared_prefix_is_not_protected(tmp_path: Path) -> None:
    """`dev-old` must not count as living inside `dev`."""
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev-old").mkdir()

    config = AppConfig()
    config.add_protected(tmp_path / "dev")
    assert config.is_protected(tmp_path / "dev-old" / "node_modules") is False


def test_adding_a_child_of_an_existing_entry_is_a_noop(tmp_path: Path) -> None:
    (tmp_path / "dev" / "app").mkdir(parents=True)
    config = AppConfig()
    assert config.add_protected(tmp_path / "dev") is True
    assert config.add_protected(tmp_path / "dev" / "app") is False
    assert len(config.protected_paths) == 1


def test_adding_a_parent_absorbs_existing_children(tmp_path: Path) -> None:
    (tmp_path / "dev" / "app").mkdir(parents=True)
    config = AppConfig()
    config.add_protected(tmp_path / "dev" / "app")
    config.add_protected(tmp_path / "dev")
    assert len(config.protected_paths) == 1
    assert config.is_protected(tmp_path / "dev" / "app") is True


def test_engine_blocks_user_protected_paths(tmp_path: Path) -> None:
    target = tmp_path / "work" / "legacy" / "node_modules"
    target.mkdir(parents=True)

    engine = SafetyEngine()
    assert engine.check_path(target).allowed

    engine.reload_protected([str(tmp_path / "work")])
    verdict = engine.check_path(target)
    assert verdict.blocked
    assert verdict.reason_key == "safety.user_protected"


def test_removal_restores_access(tmp_path: Path) -> None:
    target = tmp_path / "work" / "node_modules"
    target.mkdir(parents=True)
    config = AppConfig()
    config.add_protected(tmp_path / "work")
    assert config.remove_protected(tmp_path / "work") is True
    assert config.is_protected(target) is False


def test_config_roundtrip_keeps_protected_paths(isolated_home: Path, tmp_path: Path) -> None:
    (tmp_path / "important").mkdir()
    store = ConfigStore(isolated_home)
    config = AppConfig()
    config.add_protected(tmp_path / "important")
    store.save(config)

    reloaded = store.load()
    assert reloaded.is_protected(tmp_path / "important" / "node_modules") is True


def test_corrupt_config_falls_back_to_safe_defaults(isolated_home: Path) -> None:
    store = ConfigStore(isolated_home)
    store.ensure_dirs()
    store.config_path.write_text("{ not valid json", encoding="utf-8")

    config = store.load()
    assert config.safe_mode is True
    assert config.delete_mode.value == "recycle_bin"
    assert config.confirm_high_risk is True


def test_import_export_protected_list(isolated_home: Path, tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    store = ConfigStore(isolated_home)

    source = AppConfig()
    source.add_protected(tmp_path / "a")
    source.add_protected(tmp_path / "b")
    export_file = tmp_path / "protected.json"
    assert store.export_protected(source, export_file) == 2

    target = AppConfig()
    assert store.import_protected(target, export_file) == 2
    assert target.is_protected(tmp_path / "a") is True
    assert json.loads(export_file.read_text(encoding="utf-8"))["protected_paths"]
