from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings


class NativeSkillError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeSkillDefinition:
    name: str
    repository: str
    commit: str
    license: str
    license_file: str
    entry_file: str
    description: str
    vendor_subdir: str = ""
    required_paths: tuple[str, ...] = ()


NATIVE_SKILLS: dict[str, NativeSkillDefinition] = {
    "guizang-social-card-skill": NativeSkillDefinition(
        name="guizang-social-card-skill",
        repository="https://github.com/op7418/guizang-social-card-skill.git",
        commit="cf4b810fac1c73fb65a2bb31d8c9278d82cbc4c5",
        license="AGPL-3.0",
        license_file="LICENSE",
        entry_file="SKILL.md",
        description="Guizang Editorial / Swiss social-card production system",
    ),
    "gc-minimal-zine-poster-v0-1": NativeSkillDefinition(
        name="gc-minimal-zine-poster-v0-1",
        repository="https://github.com/LiamGvchi/gc-minimal-zine-poster.git",
        commit="4cb0396ad4e834019f753b37e1c4f415f5e02026",
        license="MIT",
        license_file="LICENSE",
        entry_file="SKILL.md",
        description="GC minimal zine poster prompt and image workflow",
    ),
    "gc-minimal-zine-poster-v0-3": NativeSkillDefinition(
        name="gc-minimal-zine-poster-v0-3",
        repository="https://github.com/LiamGvchi/gc-minimal-zine-poster.git",
        commit="342b5c11d6fa9be261841ec722c12a683a9fa5e9",
        license="MIT",
        license_file="LICENSE",
        entry_file="SKILL.md",
        description="GC Minimal Zine v0.3 prompt compiler, references, and eval suite",
        vendor_subdir="gc-minimal-zine-poster-v0-3",
        required_paths=("SKILL.md", "LICENSE", "references", "evals/evals.json"),
    ),
}


class NativeSkillManager:
    """Install exact, pinned upstream Skills outside the X2RED source tree."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.native_skill_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        self.definition(name)
        return self.root / name

    @staticmethod
    def vendor_path(definition: NativeSkillDefinition) -> Path | None:
        if not definition.vendor_subdir:
            return None
        return (
            Path(__file__).resolve().parents[1]
            / "vendor"
            / "native-skills"
            / definition.vendor_subdir
        ).resolve()

    @staticmethod
    def definition(name: str) -> NativeSkillDefinition:
        definition = NATIVE_SKILLS.get(name)
        if definition is None:
            raise NativeSkillError(f"未知原生 Skill：{name}")
        return definition

    def status(self, name: str) -> dict[str, Any]:
        definition = self.definition(name)
        path = self.path_for(name)
        installed = path.is_dir() and self._definition_complete(path, definition)
        current_commit = ""
        clean = False
        if installed and (path / ".git").is_dir() and shutil.which("git"):
            current_commit = self._run(
                ["git", "rev-parse", "HEAD"], cwd=path, timeout=30, check=False
            ).stdout.strip()
            dirty = self._run(
                ["git", "status", "--porcelain"], cwd=path, timeout=30, check=False
            ).stdout.strip()
            clean = not dirty
        elif installed and definition.vendor_subdir:
            manifest = self._read_vendor_manifest(path)
            current_commit = str(manifest.get("commit") or "")
            clean = self._vendor_snapshot_matches(path, definition)
        validator_ready = False
        if name == "guizang-social-card-skill":
            validator_ready = bool(
                installed
                and (path / "validate-social-deck.mjs").is_file()
                and (path / "node_modules" / "playwright").is_dir()
                and shutil.which("node")
            )
        return {
            **asdict(definition),
            "path": str(path),
            "installed": installed,
            "current_commit": current_commit,
            "pinned_commit_match": current_commit == definition.commit,
            "clean_checkout": clean,
            "vendor_complete": bool(
                definition.vendor_subdir and installed and clean
            ),
            "validator_ready": validator_ready,
            "source_offer": definition.repository.removesuffix(".git"),
        }

    def statuses(self) -> list[dict[str, Any]]:
        return [self.status(name) for name in NATIVE_SKILLS]

    def ensure_installed(self, name: str, *, install_runtime: bool = True) -> Path:
        status = self.status(name)
        if status["installed"] and status["pinned_commit_match"]:
            if name == "guizang-social-card-skill" and install_runtime and not status["validator_ready"]:
                self._install_node_runtime(self.path_for(name))
            return self.path_for(name)
        return self.install(name, install_runtime=install_runtime)

    def install(self, name: str, *, install_runtime: bool = True) -> Path:
        definition = self.definition(name)
        target = self.path_for(name)
        staging = self.root / f".{name}.installing"
        if staging.exists():
            shutil.rmtree(staging)
        try:
            vendor = self.vendor_path(definition)
            if vendor is not None:
                if not self._definition_complete(vendor, definition):
                    raise NativeSkillError(
                        f"内置 Skill 快照不完整：{definition.name}"
                    )
                shutil.copytree(vendor, staging)
            else:
                if not shutil.which("git"):
                    raise NativeSkillError("系统没有 git，无法安装上游 Skill")
                self._run(
                    ["git", "clone", "--no-checkout", definition.repository, str(staging)],
                    cwd=self.root,
                    timeout=300,
                )
                self._run(
                    ["git", "fetch", "--depth", "1", "origin", definition.commit],
                    cwd=staging,
                    timeout=300,
                )
                self._run(
                    ["git", "checkout", "--detach", definition.commit],
                    cwd=staging,
                    timeout=120,
                )
            if not self._definition_complete(staging, definition):
                raise NativeSkillError(f"上游 Skill 文件不完整：{definition.name}")
            if target.exists():
                backup = self.root / f".{name}.previous"
                if backup.exists():
                    shutil.rmtree(backup)
                target.rename(backup)
                staging.rename(target)
                shutil.rmtree(backup)
            else:
                staging.rename(target)
            self._write_integration_notice(target, definition)
            if name == "guizang-social-card-skill" and install_runtime:
                self._install_node_runtime(target)
            return target
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

    def read_text(self, name: str, relative_path: str, *, max_chars: int = 200_000) -> str:
        root = self.ensure_installed(name)
        path = (root / relative_path).resolve()
        if root not in path.parents and path != root:
            raise NativeSkillError("禁止读取 Skill 目录之外的文件")
        if not path.is_file():
            raise NativeSkillError(f"Skill 文件不存在：{relative_path}")
        return path.read_text(encoding="utf-8")[:max_chars]

    @staticmethod
    def _definition_complete(
        path: Path,
        definition: NativeSkillDefinition,
    ) -> bool:
        required = definition.required_paths or (
            definition.entry_file,
            definition.license_file,
        )
        return all((path / relative).exists() for relative in required)

    @staticmethod
    def _read_vendor_manifest(path: Path) -> dict[str, Any]:
        manifest = path / "X2RED-UPSTREAM.json"
        if not manifest.is_file():
            return {}
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _vendor_snapshot_matches(
        self,
        target: Path,
        definition: NativeSkillDefinition,
    ) -> bool:
        vendor = self.vendor_path(definition)
        if vendor is None or not vendor.is_dir():
            return False
        for source in vendor.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(vendor)
            candidate = target / relative
            try:
                if not candidate.is_file() or candidate.read_bytes() != source.read_bytes():
                    return False
            except OSError:
                return False
        return True

    def _install_node_runtime(self, target: Path) -> None:
        if not shutil.which("npm") or not shutil.which("node"):
            raise NativeSkillError(
                "Guizang 原生 validator 需要 Node.js/npm。请先安装 Node.js，再重新点击安装。"
            )
        lock = target / "package-lock.json"
        command = ["npm", "ci"] if lock.is_file() else ["npm", "install"]
        self._run(command, cwd=target, timeout=600)
        node_playwright = target / "node_modules" / ".bin" / "playwright"
        if not node_playwright.is_file():
            raise NativeSkillError("Guizang 上游 Node Playwright 安装不完整")
        self._run([str(node_playwright), "install", "chromium"], cwd=target, timeout=900)
        self._run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            cwd=target,
            timeout=900,
        )
        self._exclude_runtime_files(target)

    def _write_integration_notice(
        self,
        target: Path,
        definition: NativeSkillDefinition,
    ) -> None:
        notice = {
            "installed_by": "X2RED native Skill adapter",
            "installed_at": datetime.now(UTC).isoformat(),
            "repository": definition.repository.removesuffix(".git"),
            "commit": definition.commit,
            "license": definition.license,
            "license_file": definition.license_file,
            "integration": "separate pinned checkout; file and subprocess adapter",
            "modified_upstream_checkout": False,
        }
        notice_path = target / "X2RED-INTEGRATION.json"
        notice_path.write_text(
            json.dumps(notice, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._exclude_runtime_files(target)

    @staticmethod
    def _exclude_runtime_files(target: Path) -> None:
        exclude = target / ".git" / "info" / "exclude"
        if not exclude.parent.is_dir():
            return
        current = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        lines = current.splitlines()
        for value in ("X2RED-INTEGRATION.json", "node_modules/"):
            if value not in lines:
                lines.append(value)
        exclude.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    @staticmethod
    def _run(
        command: list[str],
        *,
        cwd: Path,
        timeout: int,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NativeSkillError(f"命令执行失败：{' '.join(command)}") from exc
        if check and completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-1200:]
            raise NativeSkillError(f"命令失败：{' '.join(command)}\n{detail}")
        return completed
