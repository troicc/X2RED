from __future__ import annotations

import json
import shutil
import subprocess
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
}


class NativeSkillManager:
    """Install exact, pinned upstream Skills outside the X2RED source tree.

    The upstream repositories remain intact Git checkouts under data/native-skills.
    X2RED communicates with them through files and subprocesses, preserving their
    licenses and avoiding a misleading partial reimplementation.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.native_skill_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        self.definition(name)
        return self.root / name

    @staticmethod
    def definition(name: str) -> NativeSkillDefinition:
        definition = NATIVE_SKILLS.get(name)
        if definition is None:
            raise NativeSkillError(f"未知原生 Skill：{name}")
        return definition

    def status(self, name: str) -> dict[str, Any]:
        definition = self.definition(name)
        path = self.path_for(name)
        installed = path.is_dir() and (path / definition.entry_file).is_file()
        current_commit = ""
        clean = False
        if installed and (path / ".git").is_dir() and shutil.which("git"):
            current_commit = self._run(
                ["git", "rev-parse", "HEAD"],
                cwd=path,
                timeout=30,
                check=False,
            ).stdout.strip()
            dirty = self._run(
                ["git", "status", "--porcelain"],
                cwd=path,
                timeout=30,
                check=False,
            ).stdout.strip()
            clean = not dirty
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
        if not shutil.which("git"):
            raise NativeSkillError("系统没有 git，无法安装上游 Skill")
        target = self.path_for(name)
        staging = self.root / f".{name}.installing"
        if staging.exists():
            shutil.rmtree(staging)
        try:
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
            if not (staging / definition.entry_file).is_file():
                raise NativeSkillError(f"上游仓库缺少 {definition.entry_file}")
            if not (staging / definition.license_file).is_file():
                raise NativeSkillError(f"上游仓库缺少 {definition.license_file}")
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

    def _install_node_runtime(self, target: Path) -> None:
        if not shutil.which("npm") or not shutil.which("node"):
            raise NativeSkillError(
                "Guizang 原生 validator 需要 Node.js/npm。请先安装 Node.js，再重新点击安装。"
            )
        lock = target / "package-lock.json"
        command = ["npm", "ci"] if lock.is_file() else ["npm", "install"]
        self._run(command, cwd=target, timeout=600)

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
        (target / "X2RED-INTEGRATION.json").write_text(
            json.dumps(notice, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
