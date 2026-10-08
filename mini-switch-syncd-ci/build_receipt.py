#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Preserve truthful targeted compiler results, including unsuccessful attempts."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--ci", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()
    out, ci, source = args.output, args.ci, args.source
    out.mkdir(parents=True, exist_ok=True)
    dependencies = json.loads((ci / "dependencies.json").read_text())
    identity = json.loads((ci / "source.json").read_text())
    expected_packages = [{"component": artifact["component"], "official_build_id": artifact["build_id"],
                          "source_version": artifact["source_version"], **package}
                         for artifact in dependencies["azure_artifacts"] for package in artifact["packages"]]
    packages_path = out / "verified-packages.json"
    packages = json.loads(packages_path.read_text()) if packages_path.is_file() else []
    installed_path = out / "installed-package-identities.tsv"
    installed = {tuple(line.split("\t")) for line in installed_path.read_text().splitlines()} if installed_path.is_file() else set()
    installed_match = all(tuple(package["filename"][:-4].split("_")) in installed for package in expected_packages)
    export_path = out / "object-export.json"
    export = json.loads(export_path.read_text()) if export_path.is_file() else {}
    artifacts = export.get("artifacts", [])
    expected_artifacts = {"archives/libSyncd.a", "archives/libSaiRedis.a", "objects/syncd-main.o"}
    exported_match = len(artifacts) == 3 and {item.get("path") for item in artifacts} == expected_artifacts
    if exported_match:
        for item in artifacts:
            artifact = out / "object-export" / item["path"]
            original = source / item["source_path"]
            exported_match = exported_match and (artifact.is_file() and original.is_file()
                and sha(artifact) == item["stripped"]["sha256"] and sha(original) == item["original"]["sha256"]
                and artifact.stat().st_size == item["stripped"]["bytes"]
                and item["defined_and_undefined_symbols_preserved"] and item["original_unchanged"])
    archive_path = out / "mini-switch-arm64-syncd-objects.tar.gz"
    archive = export.get("archive", {})
    archive_match = (archive_path.is_file() and archive.get("filename") == archive_path.name
                     and archive.get("bytes") == archive_path.stat().st_size and archive.get("sha256") == sha(archive_path)
                     and archive_path.stat().st_size <= 32 * 1024**2)
    logs = ("source-inputs.log", "autogen.log", "preconfigure-public-loader.log", "configure.log", "configure-detail.log", "config.h.log",
            "metadata-generator.log", "redis-objects.log", "syncd-objects.log", "upstream-link-dry-run.log",
            "public-syncd-link.log", "object-export-command.log", "compiler-version.txt", "policy-unit.log")
    logs_match = all((out / name).is_file() and (out / name).stat().st_size > 0 for name in logs)
    checks = {"actual_linux_arm64": platform.system() == "Linux" and platform.machine() == "aarch64",
              "all_ten_official_packages_authenticated": packages == expected_packages and len(packages) == 10,
              "installed_package_identities_match": installed_match,
              "actual_three_production_relocatables_authenticated": exported_match,
              "bounded_archive_authenticated": archive_match,
              "actual_required_command_logs_present": logs_match,
              "exporter_checks_passed": export.get("status") == "PASS" and export.get("public_validation_link_executed") is True,
              "exact_production_translation_units": export.get("production_translation_units") == {"libSyncd": 44, "libSaiRedis": 22, "main": 1}}
    passed = args.exit_code == 0 and all(checks.values())
    commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True)
    report = {"schema_version": 1, "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "status": "PASS" if passed else "FAIL", "exit_code": args.exit_code,
              "scope": "Actual upstream production syncd/libSaiRedis objects and genuine public Redis-SAI validation link",
              "source_commit": identity["source_commit"], "sai_commit": identity["sai_commit"],
              "executed_checkout_commit": commit.stdout.strip() if commit.returncode == 0 else None,
              "image": dependencies["image"], "acceptance_checks": checks, "verified_packages": packages,
              "public_validation_link_executed": bool(passed), "private_vendor_link_executed": False,
              "sonic_startup_executed": False, "physical_or_rtl_traffic_executed": False,
              "target_interface_profile": json.loads((ci / "vendor-interface-profile.json").read_text()),
              "object_export": {"receipt_sha256": sha(export_path) if export_path.is_file() else None,
                                "archive": archive, "passed": bool(passed)},
              "cloud_source_files": [{"path": path.name, "sha256": sha(path)} for path in sorted(ci.iterdir()) if path.is_file()],
              "evidence_file_hashes": [{"path": path.relative_to(out).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
                                     for path in sorted(out.rglob("*")) if path.is_file() and path.name != "build-receipt.json"
                                     and path.suffix in {".json", ".log", ".txt", ".tsv"}]}
    (out / "build-receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"] + ": targeted public syncd compilation; local private link and SONiC startup remain pending")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
