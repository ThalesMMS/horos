#!/usr/bin/env python3
"""#367 inventory catalog is the single reusable suite pointer, not a second suite.

The catalog must name every ystarrev novelty, the 17 forwarded scopes, plugin
and DICOMweb contracts, and the existing host regressions. It must not copy
those suites, import ystarrev sources, or treat an issue number as proof.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
catalog_path = root / "docs/ystarrev-inventory-catalog.json"
matrix_path = root / "docs/ystarrev-inventory.md"
SOURCE_SHA = "23722fb552d96fa2d60c7f58a6d4ac2c27950f86"
PRESET_SHA = "ad9fbaeafc2072785f76a987ddd332592efa226c"
ALLOWED_DECISIONS = {"reuse", "adapt", "already_equivalent", "exclude"}
FORWARD_OWNERS = {
    111: 373, 255: 373, 273: 373, 294: 373, 295: 373, 297: 373,
    205: 374, 216: 374, 224: 374, 225: 374,
    209: 375, 214: 375, 215: 375,
    247: 377,
    237: 378,
    300: 380,
    34: 375,
}
PLUGIN_SELECTORS = (
    "filterImage:",
    "processFiles:",
    "report:action:",
    "initPlugin",
    "willUnload",
    "isCertifiedForMedicalImaging",
    "setMenus",
    "handleEvent:forViewer:",
    "httpResponseForPath:forConnection:",
)
PLUGIN_NOTIFICATIONS = (
    "OsirixROIChangeNotification",
    "OsirixAddToDBNotification",
    "OsirixPopulatedContextualMenuNotification",
    "OsirixViewerControllerDidLoadImagesNotification",
    "AppPluginDownloadInstallDidFinishNotification",
)
DICOMWEB_CLASSES = (
    "DICOMwebClient",
    "DICOMwebCredentials",
    "DICOMwebMultipart",
    "DICOMwebNodeEditor",
)
DICOMWEB_CAPABILITIES = (
    "qido_paged",
    "wado_rs_multipart",
    "credentials_https",
    "redirects_not_followed",
    "status_401",
    "status_403",
    "timeout",
    "cancel",
    "incompleteness",
    "query_retrieve_locations",
    "no_stow",
)
REUSE_IDS = ("A210", "A304", "R227", "R250", "R251", "R254", "A308", "I231", "C296", "C323")
REGRESSION_IDS = ("R197", "R233", "R351", "R355", "R360", "R362", "R364", "R034", "D269")
PRESERVE_PREFIXES = (
    "plugin", "api", "header", "alias", "hook", "notification",
    "catalog", "horoscloud", "report",
)


def load_catalog():
    assert catalog_path.is_file(), f"FAIL: missing {catalog_path.relative_to(root)}"
    return json.loads(catalog_path.read_text())


def existing(path):
    return (root / path).is_file()


def test_catalog_files_exist_and_name_the_issue():
    catalog = load_catalog()
    assert catalog["issue"] == 367
    assert catalog["copy_code"] is False
    assert catalog["source"]["sha"] == SOURCE_SHA
    assert catalog["source"]["path"] == "../ystarrev/horos"
    assert catalog["source"]["readonly"] is True
    assert catalog["environment"]["arch"] == "arm64"
    assert catalog["environment"]["intel_in_scope"] is False
    assert set(catalog["evidence"]["kinds"]) >= {"static", "unit", "mock", "runtime"}
    assert catalog["evidence"]["isolated_database"] is True
    assert catalog["evidence"]["fixtures"] == "synthetic_or_deidentified"
    assert matrix_path.is_file(), "FAIL: missing markdown matrix"


def test_source_sha_matches_local_ystarrev_when_present():
    source = (root / "../ystarrev/horos").resolve()
    if not (source / ".git").exists() and not (source / "Horos").exists():
        print("note: ../ystarrev/horos absent; catalog SHA is still pinned")
        return
    head = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    assert head == SOURCE_SHA, f"catalog SHA {SOURCE_SHA} != checkout {head}"


def test_seventeen_forwarded_scopes_have_unique_ids_and_owners():
    catalog = load_catalog()
    scopes = {item["id"]: item for item in catalog["forwarded_scopes"]}
    assert len(scopes) == 17
    seen_origins = []
    for origin, owner in FORWARD_OWNERS.items():
        criterion = f"A{origin:03d}" if origin != 34 else "A034"
        item = scopes[criterion]
        assert item["origin"] == origin
        assert item["owner"] == owner
        assert item["status"] in {"pending", "residual"}
        assert item["acceptance_on_legacy_path"] is True
        seen_origins.append(origin)
        if origin == 34:
            assert item["status"] == "residual"
            assert item["sha"] == PRESET_SHA
            assert item["owner"] == 375
        else:
            assert item["status"] == "pending"
    assert sorted(seen_origins) == sorted(FORWARD_OWNERS)
    owners = [item["owner"] for item in catalog["forwarded_scopes"]]
    assert 373 in owners and 374 in owners and 375 in owners
    assert 377 in owners and 378 in owners and 380 in owners


def test_every_criterion_has_one_owner_and_stable_id():
    catalog = load_catalog()
    ids = []
    for group in ("forwarded_scopes", "novelties", "exclusions", "regressions", "reuse"):
        for item in catalog[group]:
            assert re.fullmatch(r"[A-Z][A-Z0-9-]+", item["id"]), item
            assert isinstance(item["owner"], int)
            ids.append(item["id"])
    assert len(ids) == len(set(ids))
    for required in (*REUSE_IDS, *REGRESSION_IDS):
        assert any(item["id"] == required for group in ("regressions", "reuse")
                   for item in catalog[group]), required


def test_novelties_classify_ystarrev_only_sources_without_copying():
    catalog = load_catalog()
    classified = set()
    for item in catalog["novelties"] + catalog["exclusions"]:
        assert item["decision"] in ALLOWED_DECISIONS, item
        assert item.get("copy_code") is not True
        for path in item["files"]:
            assert not path.startswith("/") and ".." not in path.split("/"), path
            if path.startswith("Horos/"):
                classified.add(path)
            else:
                # An entry may also name the workbench files it touches - a DCM
                # Framework source, its tests, its documentation. Those are not
                # paths in ystarrev's Horos/Sources, so they are not classified
                # against that tree, but they do have to exist here.
                assert existing(path), path
    source = (root / "../ystarrev/horos").resolve()
    if not (source / "Horos/Sources").exists():
        assert classified, "catalog lists no ystarrev files"
        return
    workbench = {
        p.relative_to(root / "Horos").as_posix()
        for p in (root / "Horos/Sources").rglob("*")
        if p.is_file() and p.suffix in {".swift", ".m", ".mm", ".h", ".cpp", ".metal"}
    }
    # Moving a host implementation from Objective-C to Objective-C++ does not
    # create a newly missing donor feature. Keep each rename explicit and real.
    aliases = catalog.get("local_source_aliases", {})
    for original, replacement in aliases.items():
        assert (source / original).is_file(), original
        assert existing(replacement), replacement
        assert original[:-2] + ".mm" == replacement
        assert Path(replacement).name in (root / "Horos.xcodeproj/project.pbxproj").read_text()
    only = set()
    for path in (source / "Horos/Sources").rglob("*"):
        if not path.is_file() or path.suffix not in {".swift", ".m", ".mm", ".h", ".cpp", ".metal"}:
            continue
        relative = "Horos/" + path.relative_to(source / "Horos").as_posix()
        workbench_relative = path.relative_to(source / "Horos").as_posix()
        if workbench_relative not in workbench and relative not in aliases:
            only.add(relative)
    missing = sorted(only - classified)
    extra = sorted(classified - only - {"Horos/Sources/MetalViewer/MetalShaders.metal"})
    assert not missing, "ystarrev-only sources missing from catalog:\n" + "\n".join(missing)
    # Extra classified paths are allowed only when they exist in ystarrev.
    for path in extra:
        assert (source / path).is_file() or path.endswith("MetalShaders.metal"), path


def test_exclusions_block_plugin_api_and_report_authorship_removal():
    catalog = load_catalog()
    reasons = " ".join(item["reason"].lower() for item in catalog["exclusions"])
    for prefix in PRESERVE_PREFIXES:
        assert prefix in reasons, prefix
    for item in catalog["exclusions"]:
        assert item["decision"] == "exclude"
        assert item["copy_code"] is False


def test_plugin_inventory_points_at_existing_host_suites():
    catalog = load_catalog()
    plugins = catalog["plugins"]
    selectors = set(plugins["selectors"])
    for selector in PLUGIN_SELECTORS:
        assert selector in selectors, selector
    header = (root / "Horos/Sources/PluginFilter.h").read_text(encoding="latin1")
    for selector in ("filterImage:", "processFiles:", "initPlugin"):
        token = selector.split(":")[0] if selector.endswith(":") else selector
        assert token in header, selector
    notifications = set(plugins["notifications"])
    notice = (root / "Horos/Sources/Notifications.h").read_text(encoding="latin1")
    for name in PLUGIN_NOTIFICATIONS:
        assert name in notifications
        assert name in notice
    assert "HorosCloud" in plugins["horos_cloud"]
    assert existing("Horos/Sources/PluginManager.m")
    for suite in plugins["suites"]:
        assert existing(suite), suite
    for required in (
        "tests/test-plugin-bundle-loading.py",
        "tests/test-plugin-load-diagnostics.py",
        "tests/test-plugin-quarantine.py",
        "tests/test-plugin-install-preflight.py",
        "tests/test-plugin-catalog-transport.py",
        "docs/incompatible-plugin-startup.md",
        "docs/plugin-execution-validation.md",
    ):
        assert required in plugins["suites"], required


def test_dicomweb_catalog_points_at_client_credentials_multipart_and_editor():
    catalog = load_catalog()
    web = catalog["dicomweb"]
    assert set(web["classes"]) >= set(DICOMWEB_CLASSES)
    for name in DICOMWEB_CLASSES:
        matches = list((root / "Horos/Sources").glob(f"*{name}*"))
        assert matches, name
    capabilities = set(web["capabilities"])
    for capability in DICOMWEB_CAPABILITIES:
        assert capability in capabilities, capability
    assert web["stow"] is False
    for suite in web["suites"]:
        assert existing(suite), suite
    for required in (
        "tests/test-dicomweb-client.py",
        "tests/test-dicomweb-multipart.py",
        "docs/dicomweb-pilot-validation.md",
        "Horos/Sources/DICOMwebClient.swift",
        "Horos/Sources/DICOMwebCredentials.swift",
        "Horos/Sources/DICOMwebMultipart.swift",
        "Horos/Sources/DICOMwebNodeEditor.swift",
    ):
        assert required in web["suites"] or required in web["sources"], required


def test_regressions_are_preserved_not_declared_done_by_issue_number():
    catalog = load_catalog()
    items = {item["id"]: item for item in catalog["regressions"]}
    for required in REGRESSION_IDS:
        assert required in items, required
        item = items[required]
        assert item["decision"] in {"reuse", "already_equivalent"}
        assert item["complete_because_issue_exists"] is False
        for path in item["suites"]:
            assert existing(path), f"{required} missing {path}"
    assert items["R197"]["issue"] == 197
    assert items["R233"]["issue"] == 233
    assert items["R351"]["issue"] == 351
    assert items["R355"]["issue"] == 355
    assert items["R360"]["issue"] == 360
    assert items["R362"]["issue"] == 362
    assert items["R364"]["issue"] == 364
    assert items["R034"]["sha"] == PRESET_SHA
    assert items["D269"]["multimonitor_claimed"] is False
    assert "hardware" in items["D269"]["reason"].lower() or "hardware" in items["D269"]["limits"].lower()


def test_reuse_entries_point_at_existing_suites_without_copying_them():
    catalog = load_catalog()
    items = {item["id"]: item for item in catalog["reuse"]}
    for required in REUSE_IDS:
        item = items[required]
        assert item["copy_tests"] is False
        for path in item["suites"]:
            assert existing(path), f"{required} missing {path}"
    assert items["A210"]["issue"] == 210
    assert items["A304"]["issue"] == 304
    assert items["A304"]["catalog"] == "docs/scroll-baseline-catalog.json"
    assert items["R227"]["issue"] == 227
    assert items["R250"]["issue"] == 250
    assert items["R251"]["issue"] == 251
    assert items["R254"]["issue"] == 254
    assert items["A308"]["issue"] == 308
    assert items["I231"]["issue"] == 231
    assert items["C296"]["issue"] == 296
    assert items["C323"]["issue"] == 323
    localization = (root / "docs/host-localization-catalog-contract.md").read_text()
    assert "#367" in localization


def test_contracts_define_372_373_376_before_consumers():
    catalog = load_catalog()
    contracts = catalog["contracts"]
    decode = contracts["372"]
    volume = contracts["373"]
    roi = contracts["376"]
    assert decode["produces"] == "decoding_metadata_facade"
    assert decode["consumers"] == [373, 371]
    assert decode["thread"] in {"worker", "caller_specified"}
    assert volume["produces"] == "shared_volume_geometry_session"
    assert set(volume["consumers"]) >= {374, 375, 378}
    assert volume["thread"] == "main_for_views_worker_for_load"
    assert roi["produces"] == "roi_seg_identity_commands_persistence"
    assert set(roi["consumers"]) >= {377, 378, 381}
    assert roi["lifetime"] == "series_session_until_explicit_dispose"
    for contract in (decode, volume, roi):
        assert contract["owner"]
        assert contract["legacy_path_kept"] is True
        assert "interfaces" in contract


def test_markdown_matrix_lists_owner_and_decision_columns():
    text = matrix_path.read_text()
    for heading in ("file", "functionality", "owner", "decision"):
        assert heading in text.lower(), heading
    for token in ("#373", "#376", "HorosCloud", "DICOMweb", "A034", "D269"):
        assert token in text, token
    assert "Intel" in text or "intel" in text
    assert SOURCE_SHA in text
    assert "does not copy" in text.lower() or "não copia" in text.lower()


test_catalog_files_exist_and_name_the_issue()
test_source_sha_matches_local_ystarrev_when_present()
test_seventeen_forwarded_scopes_have_unique_ids_and_owners()
test_every_criterion_has_one_owner_and_stable_id()
test_novelties_classify_ystarrev_only_sources_without_copying()
test_exclusions_block_plugin_api_and_report_authorship_removal()
test_plugin_inventory_points_at_existing_host_suites()
test_dicomweb_catalog_points_at_client_credentials_multipart_and_editor()
test_regressions_are_preserved_not_declared_done_by_issue_number()
test_reuse_entries_point_at_existing_suites_without_copying_them()
test_contracts_define_372_373_376_before_consumers()
test_markdown_matrix_lists_owner_and_decision_columns()
print("PASS: ystarrev inventory catalog covers novelties, 17 forwarded scopes, plugins, DICOMweb and reuse")
