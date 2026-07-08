"""Tests for Phase K21.1: Entity System."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.entity_system import (
    AliasRegistry,
    DigitalEntity,
    Entity,
    EntityMergeManager,
    EventLog,
    HumanEntity,
    PhysicalEntity,
    Relation,
)


@pytest.fixture(autouse=True)
def clean_registry():
    AliasRegistry.reset()
    yield
    AliasRegistry.reset()


def test_entity_subclasses():
    # 1. Physical entity
    pe = PhysicalEntity(
        entity_id="uuid_phys",
        canonical_id="physical.device.laptop",
        entity_type="temp",  # Should be overridden by post_init
        location=(10.0, 20.0, 0.0),
        bounding_box=((0.0, 0.0, 0.0), (1.0, 1.0, 0.5))
    )
    assert pe.entity_type == "physical"
    assert pe.location == (10.0, 20.0, 0.0)
    assert pe.bounding_box == ((0.0, 0.0, 0.0), (1.0, 1.0, 0.5))

    # 2. Digital entity
    de = DigitalEntity(
        entity_id="uuid_dig",
        canonical_id="digital.file.settings",
        entity_type="temp",
        file_path="/etc/settings.conf"
    )
    assert de.entity_type == "digital"
    assert de.file_path == "/etc/settings.conf"


def test_alias_registry_resolution():
    # Register alias
    AliasRegistry.register_alias("processor", "self.hardware.cpu")
    assert AliasRegistry.resolve("processor") == "self.hardware.cpu"
    assert AliasRegistry.resolve("non_existent") == "non_existent"

    # Register UUID redirect
    AliasRegistry.register_uuid_redirect("uuid_old", "uuid_new")
    assert AliasRegistry.resolve("uuid_old") == "uuid_new"

    # Chained resolution: alias redirects to target
    AliasRegistry.register_uuid_redirect("uuid_dep", "uuid_act")
    AliasRegistry.register_alias("uuid_act", "canonical_final")
    assert AliasRegistry.resolve("uuid_dep") == "canonical_final"


def test_namespace_wildcard_matching():
    AliasRegistry.register_alias("cpu_alias", "self.hardware.cpu")
    AliasRegistry.register_alias("ram_alias", "self.hardware.ram")
    AliasRegistry.register_alias("disk_alias", "self.storage.disk")

    matches = AliasRegistry.match_namespace("self.hardware.*")
    assert "self.hardware.cpu" in matches
    assert "self.hardware.ram" in matches
    assert "self.storage.disk" not in matches


def test_entity_merge_resolution():
    # Primary entity
    e_primary = Entity(
        entity_id="uuid_primary",
        canonical_id="self.hardware.cpu",
        entity_type="self",
        properties={
            "frequency": {"value": "3.5GHz", "timestamp": 10.0},
            "status": "online"
        },
        relations=[
            Relation("uuid_primary", "uuid_parent", "child_of", 0.9, 10.0)
        ],
        history=[
            EventLog("evt_1", 10.0, "MODIFY", {"status": "online"}, "system")
        ],
        last_observed=15.0,  # Newer than secondary last_observed
        confidence=0.9
    )

    # Secondary entity (older status, newer frequency & cores)
    e_secondary = Entity(
        entity_id="uuid_secondary",
        canonical_id="self.processor",
        entity_type="self",
        properties={
            "frequency": {"value": "4.0GHz", "timestamp": 12.0},  # Newer -> Overwrites
            "cores": {"value": 8, "timestamp": 12.0},             # New -> Appends
            "status": "offline"                                   # No timestamp -> Overwritten by primary newer observations
        },
        relations=[
            Relation("uuid_secondary", "uuid_child", "parent_of", 0.95, 12.0)
        ],
        history=[
            EventLog("evt_2", 12.0, "MODIFY", {"cores": 8}, "system")
        ],
        last_observed=12.0,
        confidence=0.8
    )

    # Execute merge
    merged = EntityMergeManager.merge_entities(e_primary, e_secondary)

    # Assert properties
    assert merged.properties["cores"]["value"] == 8
    assert merged.properties["frequency"]["value"] == "4.0GHz"
    assert merged.properties["status"] == "online"  # Kept primary since primary last_observed was newer than raw key status
    
    # Assert relations re-mapped
    assert len(merged.relations) == 2
    remapped_rel = merged.relations[1]
    assert remapped_rel.source_uuid == "uuid_primary"  # Redirected from uuid_secondary
    assert remapped_rel.target_uuid == "uuid_child"

    # Assert chronological history logs
    assert len(merged.history) == 2
    assert merged.history[0].event_id == "evt_1"
    assert merged.history[1].event_id == "evt_2"

    # Assert Alias registry redirect
    assert AliasRegistry.resolve("uuid_secondary") == "uuid_primary"
    assert AliasRegistry.resolve("self.processor") == "self.hardware.cpu"
