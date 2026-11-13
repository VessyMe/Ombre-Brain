"""备份年龄：pulse 永远报一行，breath 只在过期 / 从没成功 / 没配置时开口。

备份曾经静默停掉三个多月没人发现——这几条锁住的是「不再静默」。
"""

from datetime import datetime, timedelta, timezone

import pytest

import github_sync
from github_sync import GitHubSync, backup_stale_warning, backup_status_line

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _config_on_a_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("OMBRE_CONFIG_PATH", str(tmp_path / "config.yaml"))
    return tmp_path


def _sync(last_success=None):
    inst = GitHubSync(token="token", repo="owner/repo")
    inst.last_success = last_success
    return inst


def test_新鲜的备份_breath保持干净_pulse报年龄():
    inst = _sync((NOW - timedelta(hours=3)).isoformat())
    assert backup_stale_warning(inst, now=NOW) == ""
    assert backup_status_line(inst, now=NOW) == (
        "GitHub backup: last success 3 hours ago (2026-11-13 09:00 UTC)."
    )


def test_过期的备份_breath开头大声说():
    inst = _sync((NOW - timedelta(days=3, hours=2)).isoformat())
    warning = backup_stale_warning(inst, now=NOW)
    assert warning.startswith("⚠️ BACKUP STALE")
    assert "3 days ago (2026-11-10 10:00 UTC)" in warning
    assert "3 days ago" in backup_status_line(inst, now=NOW)


def test_从没成功过():
    inst = _sync(None)
    assert "no successful" in backup_stale_warning(inst, now=NOW)
    assert backup_status_line(inst, now=NOW) == (
        "GitHub backup: no successful sync since the last restart."
    )


def test_没配置_breath不吵_pulse照说():
    assert backup_stale_warning(None, now=NOW) == ""
    assert backup_status_line(None, now=NOW) == "GitHub backup: not configured."


def test_连续失败也写进pulse那一行():
    inst = _sync((NOW - timedelta(minutes=30)).isoformat())
    inst.consecutive_failures = 2
    assert backup_status_line(inst, now=NOW) == (
        "GitHub backup: last success 30 minutes ago (2026-11-13 11:30 UTC)."
        " Last 2 attempt(s) failed."
    )


@pytest.mark.asyncio
async def test_成功时间落盘_重启后还认得(_config_on_a_disk, monkeypatch):
    inst = GitHubSync(token="token", repo="owner/repo")
    assert inst.last_success is None

    async def fake_commit(self, files):
        return len(files)

    monkeypatch.setattr(GitHubSync, "_batch_commit", fake_commit)
    buckets = _config_on_a_disk / "buckets"
    (buckets / "dynamic").mkdir(parents=True)
    (buckets / "dynamic" / "a.md").write_text("---\nid: a\n---\nhi\n", encoding="utf-8")
    result = await inst.sync(str(buckets))
    assert result["ok"]

    marker = _config_on_a_disk / github_sync._LAST_SUCCESS_FILENAME
    assert marker.read_text(encoding="utf-8").strip() == inst.last_success
    # 「重启」：新实例从盘上读回同一个时间
    assert GitHubSync(token="token", repo="owner/repo").last_success == inst.last_success


def test_配置在代码目录里时不落盘(monkeypatch):
    monkeypatch.delenv("OMBRE_CONFIG_PATH", raising=False)
    monkeypatch.setattr(
        github_sync, "config_file_path",
        lambda: str(github_sync._project_root() + "/config.yaml"),
    )
    assert github_sync._last_success_path() is None
    github_sync._write_last_success("2026-11-13T12:00:00+00:00")  # 不抛、不写
