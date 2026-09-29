"""Scan reachable Git blobs without printing or persisting credential values."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from bench.common import BACKEND, ROOT, command, write_json

PATTERNS = {
    "github_token": rb"gh[pousr]_[A-Za-z0-9]{30,}",
    "groq_token": rb"gsk_[A-Za-z0-9]{30,}",
    "openai_project_token": rb"sk-proj-[A-Za-z0-9_-]{40,}",
    "openrouter_token": rb"sk-or-v1-[A-Za-z0-9]{32,}",
    "aws_access_key": rb"AKIA[0-9A-Z]{16}",
    "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}


def main():
    from dotenv import dotenv_values
    settings = dotenv_values(BACKEND / ".env")
    names = ("GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "OPENROUTER_API_KEY", "ADMIN_API_KEY")
    placeholder = re.compile(r"your[_-]|replace|example|changeme|change.me|placeholder|xxx", re.I)
    templates = [name for name in names if settings.get(name) and placeholder.search(settings[name])]
    known = {name: settings[name].encode() for name in names if settings.get(name) and len(settings[name]) >= 16 and name not in templates}
    objects = command(["git", "rev-list", "--objects", "--all"]).splitlines()
    found, scanned, scanned_bytes = [], 0, 0
    with subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
        for row in objects:
            object_id, _, path = row.partition(" ")
            proc.stdin.write((object_id + "\n").encode())
            proc.stdin.flush()
            header = proc.stdout.readline().decode().split()
            if len(header) != 3:
                raise RuntimeError("Unexpected Git object header")
            size = int(header[2])
            remaining, overlap = size, b""
            matches = set()
            while remaining:
                block = proc.stdout.read(min(1024 * 1024, remaining))
                if not block:
                    raise RuntimeError("Truncated Git object")
                remaining -= len(block)
                if header[1] == "blob":
                    buffer = overlap + block
                    matches.update(name for name, value in known.items() if value in buffer)
                    matches.update(name for name, pattern in PATTERNS.items() if re.search(pattern, buffer))
                    overlap = buffer[-2048:]
            if proc.stdout.read(1) != b"\n":
                raise RuntimeError("Git object framing failed")
            if header[1] == "blob":
                scanned += 1
                scanned_bytes += size
            if matches:
                found.append({"object": object_id, "path_hint": path, "credential_kinds": sorted(matches)})
        proc.stdin.close()
        proc.wait(timeout=20)
    copies = []
    for rel in ("backend/.env", "desktop/dist/win-unpacked/backend/.env"):
        path = ROOT / rel
        if path.is_file():
            data = path.read_bytes()
            copies.append({"path": rel, "credential_kinds": [k for k, v in known.items() if v in data],
                           "tracked": bool(command(["git", "ls-files", "--", rel]))})
    report = {"scope": "All blobs reachable from all local refs; known current credentials plus token signatures.",
              "blobs_scanned": scanned, "bytes_scanned": scanned_bytes, "template_values_excluded": templates,
              "history_findings": found, "current_env_copies": copies,
              "limitations": ["Remote-only and unreachable/deleted objects not scanned.",
                              "Git LFS pointers scanned, not remote LFS payloads or compressed archive contents.",
                              "No-match is not proof that every unknown credential is absent."],
              "secret_values_saved": False}
    write_json(ROOT / "bench/results/security-scan.json", report)
    print(f"Scanned {scanned} Git blobs; {len(found)} objects matched credential signatures. Values omitted.")


if __name__ == "__main__":
    main()
