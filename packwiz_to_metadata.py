#!/usr/bin/env python3
"""
Modrinth + CurseForge API -> mod-metadata YAML generator for packwiz repos.

What it does
- Scans mods/*.pw.toml (packwiz) to find Modrinth or CurseForge update metadata.
- For Modrinth entries, optionally calls Modrinth API to fetch project metadata:
  slug, title, categories, client_side, server_side.
- For CurseForge entries, optionally calls CurseForge API to fetch project metadata:
  title, categories, clientSide, serverSide, website URL.
- Produces a machine-readable YAML file (suggestions) you can commit and then manually curate.

Why "suggestions" only?
- Modrinth categories/tags are not a strict contract; treat them as hints.
- Your repo-owned mod-metadata.yml should be the source of truth.

References
- Modrinth API: GET /project/{id|slug} (categories, client_side, server_side)
  https://docs.modrinth.com/api/operations/getproject/
- CurseForge API: GET /v1/mods/{modId}
  https://docs.curseforge.com/
- packwiz mod.pw.toml Modrinth update fields (mod-id, version)
  https://packwiz.infra.link/reference/pack-format/mod-toml/
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import json
import tomllib
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


MODRINTH_BASE = "https://api.modrinth.com/v2"
CURSEFORGE_BASE = "https://api.curseforge.com"

# ---- Heuristic mappings (edit freely) ----
# Modrinth category -> our "group" suggestion
CATEGORY_TO_GROUP = {
    # performance & optimization
    "optimization": "perf",
    "performance": "perf",
    # QoL / utility
    "utility": "qol",
    "management": "qol",
    "tools": "qol",
    # UI / map / client experience
    "gui": "ui-map",
    "map": "ui-map",
    "minimap": "ui-map",
    "hud": "ui-map",
    # visuals
    "decoration": "visual",
    "cosmetic": "visual",
    "shaders": "visual",
    "audio": "visual",
    # content
    "technology": "content-tech",
    "magic": "content-magic",
    "adventure": "content",
    "mobs": "content",
    # worldgen (high risk)
    "worldgen": "worldgen",
    "biomes": "worldgen",
    "structures": "worldgen",
    "dimensions": "worldgen",
    # libraries / loaders
    "library": "core",
    "fabric": "core",
    "neoforge": "core",
    "forge": "core",
}

# categories implying high risk for saves/world compatibility
HIGH_RISK_CATEGORIES = {"worldgen", "biomes", "structures", "dimensions"}

# side support mapping
def suggest_side(client_side: str, server_side: str) -> str:
    """
    client_side/server_side values: required|optional|unsupported|unknown
    Returns: client|server|both|unknown
    """
    c = (client_side or "unknown").lower()
    s = (server_side or "unknown").lower()

    def is_yes(v: str) -> bool:
        return v in {"required", "optional"}

    def is_no(v: str) -> bool:
        return v == "unsupported"

    if is_yes(c) and is_yes(s):
        return "both"
    if is_yes(c) and is_no(s):
        return "client"
    if is_yes(s) and is_no(c):
        return "server"
    return "unknown"


def http_get_json(
    url: str,
    *,
    timeout: int = 20,
    user_agent: str = "packwiz-to-metadata/1.0",
    headers: dict[str, str] | None = None,
) -> dict:
    req_headers = {"User-Agent": user_agent, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data)


def find_modrinth_project_id(pw_toml: dict) -> str | None:
    # packwiz format: [update.modrinth] mod-id="..." version="..."
    upd = pw_toml.get("update") or {}
    mr = upd.get("modrinth") or {}
    mid = mr.get("mod-id")
    if isinstance(mid, str) and mid.strip():
        return mid.strip()
    return None


def find_curseforge_ids(pw_toml: dict) -> tuple[int, int] | None:
    # packwiz format: [update.curseforge] project-id=... file-id=...
    upd = pw_toml.get("update") or {}
    cf = upd.get("curseforge") or {}
    pid = cf.get("project-id")
    fid = cf.get("file-id")
    if isinstance(pid, int) and isinstance(fid, int):
        return pid, fid
    return None


def curseforge_side_to_mr(v: object) -> str:
    """
    CurseForge clientSide/serverSide values can be strings or ints depending on API/version.
    Normalize into required|optional|unsupported|unknown (Modrinth-compatible) for suggest_side().
    """
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"required", "optional", "unsupported", "unknown"}:
            return s
        # sometimes "Required", etc
        if s in {"required (client)", "required (server)"}:
            return "required"
        return "unknown"
    if isinstance(v, int):
        # Best-effort mapping based on common enum ordering used by CF:
        # 0=required, 1=optional, 2=unsupported, 3=unknown
        return {0: "required", 1: "optional", 2: "unsupported", 3: "unknown"}.get(v, "unknown")
    return "unknown"


def curseforge_fetch_project(
    project_id: int,
    *,
    api_key: str,
    timeout: int = 20,
    base: str = CURSEFORGE_BASE,
) -> dict:
    url = f"{base}/v1/mods/{project_id}"
    data = http_get_json(url, timeout=timeout, headers={"x-api-key": api_key})
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return {}


def best_group_from_categories(categories: list[str]) -> str:
    # choose the first mapped group, preferring specific ones
    for cat in categories:
        g = CATEGORY_TO_GROUP.get(cat.lower())
        if g:
            return g
    return "unknown"


def suggest_layer_from_group(group: str) -> str:
    if group in {"core"}:
        return "core"
    if group in {"perf", "qol"}:
        return "core"   # usually core-ish (safe default)
    if group in {"ui-map", "visual"}:
        return "client-only"
    if group in {"worldgen", "content", "content-tech", "content-magic"}:
        return "content"
    return "unknown"


def risk_from_categories(categories: list[str]) -> str:
    cats = {c.lower() for c in categories}
    if cats & HIGH_RISK_CATEGORIES:
        return "high"
    return "low"


def risk_from_freeform_categories(categories: list[str]) -> str:
    cats = " ".join(c.lower() for c in categories)
    if any(k in cats for k in ["worldgen", "world gen", "biome", "structure", "dimension"]):
        return "high"
    return "low" if categories else "unknown"


def yaml_escape(s: str) -> str:
    # minimal safe quoting
    if s == "" or any(ch in s for ch in [":", "{", "}", "[", "]", "#", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`"]):
        return json.dumps(s, ensure_ascii=False)  # JSON string is valid YAML scalar
    if re.search(r"\s", s):
        return json.dumps(s, ensure_ascii=False)
    return s


def dump_yaml(mapping: dict) -> str:
    """
    Very small YAML emitter (no dependencies).
    Output format:
      key:
        field: value
    """
    lines: list[str] = []
    for key in sorted(mapping.keys()):
        lines.append(f"{yaml_escape(key)}:")
        obj = mapping[key]
        for field, val in obj.items():
            if isinstance(val, dict):
                lines.append(f"  {field}:")
                for k2, v2 in val.items():
                    lines.append(f"    {k2}: {yaml_escape(str(v2))}")
            elif isinstance(val, list):
                lines.append(f"  {field}:")
                for it in val:
                    lines.append(f"    - {yaml_escape(str(it))}")
            else:
                lines.append(f"  {field}: {yaml_escape(str(val))}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate mod-metadata suggestions from Modrinth API for a packwiz repo.")
    ap.add_argument("--repo", default=".", help="Path to packwiz repo root (contains pack.toml).")
    ap.add_argument("--mods-dir", default="mods", help="Mods metadata dir (default: mods).")
    ap.add_argument("--out", default="mod-metadata.generated.yml", help="Output YAML filename.")
    ap.add_argument("--sleep", type=float, default=0.15, help="Delay between API calls (avoid rate limits).")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="Do not make network calls (Modrinth/CurseForge entries will be generated from local metadata only).",
    )
    ap.add_argument(
        "--curseforge-api-key",
        default=os.environ.get("CURSEFORGE_API_KEY", ""),
        help="CurseForge API key (or set env CURSEFORGE_API_KEY). Required to fetch CurseForge categories/sides.",
    )
    ap.add_argument(
        "--curseforge-base",
        default=CURSEFORGE_BASE,
        help="CurseForge API base URL (default: https://api.curseforge.com).",
    )
    ap.add_argument("--only-missing", action="store_true", help="Only output entries that are not present in an existing mod-metadata.yml")
    ap.add_argument("--existing", default="mod-metadata.yml", help="Existing metadata YAML (for only-missing). Parsed as keys only.")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    mods_dir = (repo / args.mods_dir).resolve()
    out_path = repo / args.out

    if not (repo / "pack.toml").exists():
        print(f"[ERR] pack.toml not found in repo root: {repo}", file=sys.stderr)
        return 2
    if not mods_dir.exists():
        print(f"[ERR] mods dir not found: {mods_dir}", file=sys.stderr)
        return 2

    existing_keys: set[str] = set()
    if args.only_missing:
        ex = repo / args.existing
        if ex.exists():
            # Parse top-level YAML keys only (simple, dependency-free).
            for line in ex.read_text(encoding="utf-8", errors="ignore").splitlines():
                if re.match(r"^[^\\s:#][^:#]*:\\s*$", line):
                    existing_keys.add(line.split(":", 1)[0].strip().strip('"').strip("'"))
        else:
            print(f"[WARN] --only-missing set but existing file not found: {ex}", file=sys.stderr)

    suggestions: dict[str, dict] = {}
    pw_files = sorted(mods_dir.glob("*.pw.toml"))
    if not pw_files:
        print(f"[ERR] No *.pw.toml found under {mods_dir}. Are you using packwiz?", file=sys.stderr)
        return 2

    for pw in pw_files:
        data = tomllib.loads(pw.read_text(encoding="utf-8"))
        pw_name = data.get("name") if isinstance(data.get("name"), str) else pw.stem.replace(".pw", "")
        pw_side = data.get("side") if isinstance(data.get("side"), str) else "unknown"
        pid = find_modrinth_project_id(data)
        cf_ids = find_curseforge_ids(data)

        key = pw.stem.replace(".pw", "")

        if args.only_missing and key in existing_keys:
            continue

        if pid:
            proj: dict | None = None
            if not args.offline:
                try:
                    proj = http_get_json(f"{MODRINTH_BASE}/project/{pid}")
                except HTTPError as e:
                    print(f"[WARN] HTTP error for {pw.name} (project {pid}): {e}", file=sys.stderr)
                except URLError as e:
                    print(f"[WARN] Network error for {pw.name} (project {pid}): {e}", file=sys.stderr)
                except Exception as e:
                    print(f"[WARN] Unexpected error for {pw.name} (project {pid}): {e}", file=sys.stderr)

            slug = (proj or {}).get("slug") or key
            title = (proj or {}).get("title") or pw_name or slug
            categories = (proj or {}).get("categories") or []
            if not isinstance(categories, list):
                categories = []
            categories = [str(c) for c in categories]

            group = best_group_from_categories(categories)
            layer = suggest_layer_from_group(group)
            side = (
                suggest_side(str((proj or {}).get("client_side", "unknown")), str((proj or {}).get("server_side", "unknown")))
                if proj
                else ("both" if pw_side == "both" else ("client" if pw_side == "client" else ("server" if pw_side == "server" else "unknown")))
            )
            risk = risk_from_categories(categories) if proj else "unknown"

            suggestions[str(slug)] = {
                "title": title,
                "layer_suggest": layer,
                "group_suggest": group,
                "side_suggest": side,
                "risk_suggest": risk,
                "modrinth": {
                    "project_id": pid,
                },
                "categories": sorted(set(categories)),
                "note": "auto-suggested from Modrinth/local metadata; please review and curate",
            }

            if not args.offline:
                time.sleep(max(args.sleep, 0.0))
            continue

        if cf_ids:
            cf_project_id, cf_file_id = cf_ids
            cf_proj: dict | None = None
            if not args.offline:
                if not args.curseforge_api_key:
                    print(
                        f"[WARN] CurseForge API key missing; cannot fetch categories for {pw.name} (project {cf_project_id}). "
                        f"Set --curseforge-api-key or env CURSEFORGE_API_KEY.",
                        file=sys.stderr,
                    )
                else:
                    try:
                        cf_proj = curseforge_fetch_project(
                            cf_project_id,
                            api_key=args.curseforge_api_key,
                            base=args.curseforge_base,
                        )
                    except HTTPError as e:
                        print(f"[WARN] HTTP error for {pw.name} (CurseForge project {cf_project_id}): {e}", file=sys.stderr)
                    except URLError as e:
                        print(f"[WARN] Network error for {pw.name} (CurseForge project {cf_project_id}): {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"[WARN] Unexpected error for {pw.name} (CurseForge project {cf_project_id}): {e}", file=sys.stderr)

            title = (cf_proj or {}).get("name") or pw_name
            categories: list[str] = []
            raw_categories = (cf_proj or {}).get("categories") or []
            if isinstance(raw_categories, list):
                for c in raw_categories:
                    if isinstance(c, dict):
                        slug = c.get("slug")
                        name = c.get("name")
                        if isinstance(slug, str) and slug.strip():
                            categories.append(slug.strip())
                        elif isinstance(name, str) and name.strip():
                            categories.append(name.strip())

            group = best_group_from_categories(categories)
            layer = suggest_layer_from_group(group)

            # Side info: prefer API if present; otherwise fall back to packwiz "side".
            if cf_proj:
                cs = curseforge_side_to_mr(cf_proj.get("clientSide"))
                ss = curseforge_side_to_mr(cf_proj.get("serverSide"))
                side_suggest = suggest_side(cs, ss)
            else:
                side_suggest = pw_side if pw_side in {"client", "server", "both"} else "unknown"

            suggestions[key] = {
                "title": title,
                "layer_suggest": layer,
                "group_suggest": group,
                "side_suggest": side_suggest,
                "risk_suggest": risk_from_freeform_categories(categories),
                "curseforge": {
                    "project_id": cf_project_id,
                    "file_id": cf_file_id,
                },
                "categories": sorted(set(categories)),
                "note": (
                    "auto-suggested from CurseForge API + local metadata; please review and curate"
                    if cf_proj
                    else "auto-suggested from CurseForge packwiz metadata only; please review and curate"
                ),
            }
            if cf_proj and not args.offline:
                time.sleep(max(args.sleep, 0.0))
            continue

        # Not Modrinth or CurseForge; skip quietly
        continue

    if not suggestions:
        print("[INFO] No suggestions generated (maybe no Modrinth mods found, or all are already present).")
        return 0

    out_path.write_text(dump_yaml(suggestions), encoding="utf-8")
    print(f"[OK] Wrote {len(suggestions)} entries -> {out_path}")
    print("[TIP] Commit this file, then copy reviewed fields into mod-metadata.yml (source of truth).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
