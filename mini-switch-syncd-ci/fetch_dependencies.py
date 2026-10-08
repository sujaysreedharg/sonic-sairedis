#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate selected official ARM64 packages without a full artifact ZIP."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
import urllib.parse
import urllib.request


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for artifact in manifest["azure_artifacts"]:
        base = "https://dev.azure.com/mssonic/build/_apis/build/builds/" + str(artifact["build_id"])
        build = get_json(base + "?api-version=7.1")
        if build["sourceVersion"] != artifact["source_version"] or build["result"] != artifact["build_result"]:
            raise RuntimeError("Official build identity drift")
        query = urllib.parse.urlencode({"artifactName": artifact["artifact_name"], "api-version": "7.1", "x": time.time_ns()})
        resource = get_json(base + "/artifacts?" + query)["resource"]
        if resource["data"] != artifact["artifact_resource_data"] or resource["properties"]["RootId"] != artifact["artifact_root_id"]:
            raise RuntimeError("Official artifact identity drift")
        for package in artifact["packages"]:
            name = package["filename"]
            if name != PurePosixPath(name).name or not name.endswith("_arm64.deb") or package["size"] > 4 * 1024**2:
                raise RuntimeError("Unsafe or oversized package")
            url = urllib.parse.urlsplit(resource["downloadUrl"])
            params = dict(urllib.parse.parse_qsl(url.query))
            params.update(format="file", subPath="/" + package["archive_path"].split("/", 1)[1], x=str(time.time_ns()))
            download = urllib.parse.urlunsplit(url._replace(query=urllib.parse.urlencode(params)))
            with urllib.request.urlopen(download, timeout=90) as response:
                data = response.read(package["size"] + 1)
            if len(data) != package["size"] or hashlib.sha256(data).hexdigest() != package["sha256"]:
                raise RuntimeError("Official package bytes differ: " + name)
            with (args.output / name).open("xb") as stream:
                stream.write(data)
            rows.append({"component": artifact["component"], "official_build_id": artifact["build_id"],
                         "source_version": artifact["source_version"], **package})
            (args.output / "verified-packages.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(artifact["component"] + ": exact source/artifact/package identities authenticated", flush=True)


if __name__ == "__main__":
    main()
