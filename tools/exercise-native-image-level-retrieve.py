#!/usr/bin/env python3
"""A partly local study retrieved through the IMAGE level, in the app (#634).

For each scenario, a fresh private database first imports half of the synthetic
study that tools/serve-cget-fixture.py serves (--export), so that the query
window's retrieve, in smart mode, asks the IMAGE level for the missing instances;
tools/probe-image-level-retrieve.m, injected, runs it and watches the study's
local images until 8 s after the retrieve thread has finished.

  complete  the peer serves every level, 0.15 s per instance
  failure   the peer fails every sub-operation of an IMAGE-level C-GET: the move has to
            fall back to the STUDY/SERIES level and still bring the whole study
  cancel    the retrieve is cancelled as soon as its first image arrives, as the
            activity window's button does
  incomplete  the peer never sends one of the missing instances (#646)
  slow-import  the first received batch takes 15 s without committing, exceeding
               the retrieve's 10 s idle timeout while the import lock is held
  unsendable  the peer fails the sub-operation of one missing instance with 0xA702, as
              an OsiriX server does for a file it cannot read, and the failures are
              reported: the main thread must keep running its default run loop mode,
              the notices panel must show them, and that instance dropped into INCOMING
              afterwards must be imported while it does (#691). The study is retrieved
              twice first: the refused instance is remembered, so the second retrieve
              asks the peer for nothing and reports nothing (#692)

Checks: complete and failure end with all 30 instances local, none arriving after
the retrieve thread finished, and (failure) the peer saw the IMAGE-level refusal
followed by a STUDY or SERIES retrieve; cancel ends within 3 s of the cancel with no
image arriving after the thread finished. At efb2b0cef the IMAGE-level wait ended
before its images arrived (#634). The inventory the move leaves is complete, with
nothing to warn about, when every instance is local, and still warns when one never
came (incomplete); until #646 it was judged before the last received files were
indexed.

    local-validation/venv/bin/python tools/exercise-native-image-level-retrieve.py \\
        --app build/Variants/candidate/HorosDevelopment.app --out local-validation/delta4/634-app/candidate

Needs a Python with pydicom, pynetdicom and numpy. Everything stays under --out.
"""
import argparse
import json
import os
import plistlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native_app  # noqa: E402

INSTANCES = 30


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def records(path: Path):
    lines = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return lines


def run_scenario(app: Path, folder: Path, dylib: Path, scenario: str) -> dict:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    port = free_port()
    export = folder / "study"
    peer_arguments = [sys.executable, str(ROOT / "tools/serve-cget-fixture.py"), str(folder / "peer"), "--port", str(port),
                      "--instances", str(INSTANCES), "--instance-delay", "0.15", "--export", str(export)]
    if scenario == "failure":
        peer_arguments.append("--fail-image-retrieve")
    if scenario == "incomplete":
        # An even instance: the odd ones are imported before the retrieve.
        peer_arguments += ["--omit-instance", str(INSTANCES)]
    if scenario == "unsendable":
        peer_arguments += ["--fail-instance", str(INSTANCES), "--fail-status", "0xA702"]
    peer = subprocess.Popen(peer_arguments, stdout=open(folder / "peer.log", "w"), stderr=subprocess.STDOUT)
    result = {"scenario": scenario}
    try:
        native_app.wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", port)) == 0, 60, description="the C-GET peer")
        native_app.wait_for(lambda: len(list(export.glob("*.dcm"))) == INSTANCES, 30, description="the exported study")
        servers = folder / "servers.json"
        servers.write_text(json.dumps([{"Address": "127.0.0.1", "Port": port, "AETitle": "CGETFIX", "TransferSyntax": 0,
                                        "retrieveMode": 1, "Description": "synthetic C-GET peer"}]))
        log, trigger, root = folder / "retrieve.jsonl", folder / "go", folder / "database"
        environment = {"DYLD_INSERT_LIBRARIES": str(dylib), "HOROS_RETRIEVE_SERVERS": str(servers),
                       "HOROS_RETRIEVE_TRIGGER": str(trigger), "HOROS_RETRIEVE_LOG": str(log)}
        if scenario == "cancel":
            environment["HOROS_RETRIEVE_CANCEL_AFTER_ARRIVAL"] = "1"
        if scenario == "slow-import":
            environment["HOROS_RETRIEVE_IMPORT_DELAY"] = "15"
        if scenario == "unsendable":
            environment["HOROS_RETRIEVE_SHOW_ERRORS"] = "1"
            environment["HOROS_RETRIEVE_REPEAT"] = "1"
        launch_arguments = ["-STORESCP", "NO", "-USESTORESCP", "NO", "-TLSStoreSCP", "NO",
                            "-hideListenerError", "NO" if scenario == "unsendable" else "YES",
                            "-syncDICOMNodes", "NO", "-publishDICOMBonjour", "NO", "-searchDICOMBonjour", "NO",
                            "-AETITLE", "HOROSDEV", "-AEPORT", str(free_port()), "-DICOMTimeout", "8",
                            "-DICOMConnectionTimeout", "5", "-TryIMAGELevelDICOMRetrieveIfLocalImages", "YES"]
        native_app.stop_all(app)
        process = native_app.launch(root, folder / "horos.log", launch_arguments, app=app, environment=environment)
        try:
            data = native_app.database_folder(root)
            native_app.wait_for(lambda: (data / "INCOMING.noindex").is_dir(), 90, description="the database to open")
            native_app.wait_for(lambda: any(r.get("probe") == "loaded" for r in records(log)), 30, description="the probe")
            # Half of the study, already local: every other instance.
            local = sorted(export.glob("*.dcm"))[::2]
            for path in local:
                staging = data / "INCOMING.noindex" / f".{path.name}.part"
                shutil.copyfile(path, staging)
                os.rename(staging, data / "INCOMING.noindex" / path.name)
            native_app.wait_for(lambda: (native_app.image_count(root) or 0) >= len(local), 120, description="the partial import")
            time.sleep(2)
            trigger.write_text("go\n")
            native_app.wait_for(lambda: any("retrieve" in r for r in records(log)), 240, interval=0.5, description="the retrieve")
            if scenario == "unsendable":
                # The peer's record is rewritten on every DIMSE message: what the first retrieve asked.
                negotiation = folder / "peer" / "cget-negotiation.json"
                result["peer_retrievals_first"] = len(json.loads(negotiation.read_text()).get("retrievals", []))
                native_app.wait_for(lambda: any("retrieve_again" in r for r in records(log)), 240, interval=0.5,
                                    description="the second retrieve")
                # The instance the peer would not send, imported while its notice is up.
                import pydicom
                missing = next(p for p in export.glob("*.dcm")
                               if pydicom.dcmread(p, stop_before_pixels=True).InstanceNumber == INSTANCES)
                dropped = time.monotonic()
                staging = data / "INCOMING.noindex" / f".{missing.name}.part"
                shutil.copyfile(missing, staging)
                os.rename(staging, data / "INCOMING.noindex" / missing.name)
                def study_images():
                    # The study's own images: the SR the app archives for it is not one.
                    sql = native_app.database_folder(root) / "Database.sql"
                    try:
                        with sqlite3.connect(f"file:{sql}?mode=ro", uri=True, timeout=1) as connection:
                            # One row per frame of a multiframe instance: count instances.
                            return connection.execute("SELECT COUNT(DISTINCT i.ZCOMPRESSEDSOPINSTANCEUID) FROM ZIMAGE i "
                                                      "JOIN ZSERIES s ON i.ZSERIES = s.Z_PK "
                                                      "WHERE s.ZMODALITY IS NOT 'SR'").fetchone()[0]
                    except sqlite3.Error:
                        return 0
                try:
                    native_app.wait_for(lambda: not (data / "INCOMING.noindex" / missing.name).exists()
                                        and study_images() >= INSTANCES, 60, description="INCOMING")
                    result["incoming_import_seconds"] = time.monotonic() - dropped
                except TimeoutError:
                    result["incoming_import_seconds"] = -1
            result["app_running"] = process.poll() is None
        finally:
            native_app.stop(process)
        lines = records(log)
        result["started"] = next((r["started"] for r in lines if "started" in r), None)
        result["retrieve"] = next(r["retrieve"] for r in lines if "retrieve" in r)
        again = next((r["retrieve_again"] for r in lines if "retrieve_again" in r), None)
        if again is not None:
            result["retrieve_again"] = again
    finally:
        peer.terminate()
        try:
            peer.wait(timeout=10)
        except subprocess.TimeoutExpired:
            peer.kill()
    evidence = folder / "peer" / "cget-negotiation.json"
    peer_record = json.loads(evidence.read_text()) if evidence.exists() else {}
    result["peer_retrievals"] = [{"level": r["level"], "refused": r.get("refused", False), "requested": len(r["requestedUIDs"])}
                                 for r in peer_record.get("retrievals", [])]
    (folder / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    return result


def check(result: dict) -> list:
    problems = []
    retrieve, scenario = result["retrieve"], result["scenario"]
    if not result.get("app_running"):
        problems.append("the app did not survive")
    if "error" in retrieve:
        return problems + [retrieve["error"]]
    if not retrieve["finished"]:
        problems.append("the retrieve thread did not finish")
    late = retrieve["local_after"] - retrieve["local_at_finish"]
    if late:
        problems.append(f"{late} image(s) arrived after the retrieve had finished "
                        f"(the last {retrieve['last_arrival_after_finish']:.2f} s later)")
    # The retrieve inventory is judged while the last files may still wait in INCOMING (#646); the
    # study's images counted locally (the SR objects the app archives for it left out) are not.
    if scenario in ("complete", "failure", "slow-import") and retrieve["local_after"] != INSTANCES:
        problems.append(f"{retrieve['local_after']} of {INSTANCES} instances local at the end")
    inventory = retrieve.get("inventory") or {}
    if scenario in ("complete", "failure", "slow-import") and (not inventory.get("isComplete") or inventory.get("needsAttention")):
        problems.append(f"the inventory left is not complete, or warns: {inventory.get('summary')} "
                        f"(needs attention {inventory.get('needsAttention')})")
    if scenario == "slow-import" and not retrieve.get("import_delay_applied"):
        problems.append("the delayed batch was not exercised")
    if scenario == "unsendable":
        if retrieve["local_after"] != INSTANCES - 1:
            problems.append(f"{retrieve['local_after']} of {INSTANCES} instances local, {INSTANCES - 1} expected")
        if not 0 <= retrieve.get("main_default_mode_ms", -1) < 1000:
            problems.append(f"the main thread did not run its default mode ({retrieve.get('main_default_mode_ms')} ms): "
                            "a modal alert holds it")
        if retrieve.get("notices", 0) < 1 or not retrieve.get("notices_showing"):
            problems.append(f"the failure was not in the notices panel ({retrieve.get('notices')}, "
                            f"showing {retrieve.get('notices_showing')})")
        if result.get("incoming_import_seconds", -1) < 0:
            problems.append("an INCOMING import did not finish while the notice was up")
        if len(inventory.get("unsendableUIDs") or []) != 1:
            problems.append(f"the refused instance was not remembered: {inventory.get('summary')}")
        again = result.get("retrieve_again") or {}
        first = result.get("peer_retrievals_first", -1)
        if first < 1 or len(result["peer_retrievals"]) != first:
            problems.append(f"the second retrieve asked the peer again ({first} retrievals first, "
                            f"{result['peer_retrievals']} in all)")
        if not again.get("finished") or again.get("local_after") != INSTANCES - 1:
            problems.append(f"the second retrieve did not end with {INSTANCES - 1} instances local ({again})")
        if (again.get("inventory") or {}).get("needsAttention") or again.get("notices_posted") != retrieve.get("notices_posted"):
            problems.append(f"the second retrieve reported the known refusal again ({retrieve.get('notices_posted')} -> "
                            f"{again.get('notices_posted')} notices)")
    if scenario == "incomplete":
        if retrieve["local_after"] != INSTANCES - 1:
            problems.append(f"{retrieve['local_after']} of {INSTANCES} instances local, {INSTANCES - 1} expected")
        if inventory.get("isComplete") or not inventory.get("needsAttention"):
            problems.append(f"a retrieve missing an instance does not warn: {inventory.get('summary')}")
    levels = [r["level"] for r in result["peer_retrievals"]]
    if "IMAGE" not in levels:
        problems.append(f"the IMAGE level was never asked ({levels})")
    if scenario == "failure":
        refused = [i for i, r in enumerate(result["peer_retrievals"]) if r["refused"]]
        fallback = [r for r in result["peer_retrievals"][refused[0] + 1:]] if refused else []
        if not refused or not any(r["level"] in ("STUDY", "SERIES") for r in fallback):
            problems.append(f"no STUDY/SERIES retrieve after the IMAGE-level refusal ({result['peer_retrievals']})")
    if scenario == "cancel":
        if retrieve["cancelled_at"] < 0:
            problems.append("the retrieve finished before its first image arrived, or none arrived")
        elif retrieve["finish_after_cancel"] > 3:
            problems.append(f"the retrieve ended {retrieve['finish_after_cancel']:.2f} s after the cancel")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path, default=native_app.DEVELOPMENT_APP)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario", action="append",
                        choices=["complete", "failure", "cancel", "incomplete", "slow-import", "unsendable"])
    arguments = parser.parse_args()
    out = arguments.out.resolve()
    if "local-validation" not in out.parts:
        parser.error("--out must be under local-validation")
    out.mkdir(parents=True, exist_ok=True)
    app = arguments.app.resolve()
    entitlements = plistlib.loads((ROOT / "build/Development/entitlements.plist").read_bytes())
    entitlements["com.apple.security.cs.allow-dyld-environment-variables"] = True
    (out / "probe-entitlements.plist").write_bytes(plistlib.dumps(entitlements))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", "--options", "runtime", "--entitlements",
                    str(out / "probe-entitlements.plist"), str(app)], check=True, capture_output=True)
    dylib = out / "probe-image-level-retrieve.dylib"
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-fobjc-arc", "-framework", "Cocoa",
                    str(ROOT / "tools/probe-image-level-retrieve.m"), "-o", str(dylib)], check=True)
    summary = {"app": str(app), "scenarios": {}}
    failed = False
    for scenario in arguments.scenario or ["complete", "failure", "cancel", "incomplete", "slow-import", "unsendable"]:
        result = run_scenario(app, out / scenario, dylib, scenario)
        problems = check(result)
        summary["scenarios"][scenario] = {"result": result, "problems": problems}
        print(f"{scenario}: {'ok' if not problems else '; '.join(problems)} "
              f"(finished {result['retrieve'].get('seconds', -1):.2f} s, local {result['retrieve'].get('local_at_finish')}"
              f" -> {result['retrieve'].get('local_after')}, peer {[r['level'] for r in result['peer_retrievals']]})")
        failed |= bool(problems)
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
