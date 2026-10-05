
import modules.pacman_maintenance as pacman_maintenance


def test_empty_community_section_is_detected(tmp_path, monkeypatch):
    conf = tmp_path / "pacman.conf"
    conf.write_text(
        "[core]\n"
        "Include = /etc/pacman.d/mirrorlist\n"
        "[community]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pacman_maintenance, "PACMAN_CONF", conf)
    assert pacman_maintenance._empty_community_section() is True


def test_community_with_include_is_not_empty(tmp_path, monkeypatch):
    conf = tmp_path / "pacman.conf"
    conf.write_text(
        "[community]\n"
        "Include = /etc/pacman.d/mirrorlist\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pacman_maintenance, "PACMAN_CONF", conf)
    assert pacman_maintenance._empty_community_section() is False


def test_community_with_server_is_not_empty(tmp_path, monkeypatch):
    conf = tmp_path / "pacman.conf"
    conf.write_text(
        "[community]\n"
        "Server = https://mirror.example/$repo/os/$arch\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pacman_maintenance, "PACMAN_CONF", conf)
    assert pacman_maintenance._empty_community_section() is False


def test_no_community_section_is_not_empty(tmp_path, monkeypatch):
    conf = tmp_path / "pacman.conf"
    conf.write_text(
        "[core]\n"
        "Include = /etc/pacman.d/mirrorlist\n"
        "[extra]\n"
        "Include = /etc/pacman.d/mirrorlist\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pacman_maintenance, "PACMAN_CONF", conf)
    assert pacman_maintenance._empty_community_section() is False


def test_scan_reports_missing_pacman_prerequisites(monkeypatch):
    monkeypatch.setattr(pacman_maintenance.shutil, "which", lambda name: {
        "pacman": "/usr/bin/pacman",
        "fuser": None,
        "pacman-mirrors": None,
    }.get(name))
    monkeypatch.setattr(pacman_maintenance, "_pacman_running", lambda: False)
    class MissingPath:
        def exists(self):
            return False

    monkeypatch.setattr(pacman_maintenance, "LOCK", MissingPath())
    monkeypatch.setattr(pacman_maintenance, "MIRRORLIST", MissingPath())
    monkeypatch.setattr(pacman_maintenance, "_empty_community_section", lambda: False)

    result = pacman_maintenance.PacmanMaintenanceModule().scan()
    titles = {finding.title for finding in result.findings}

    assert "fuser غير موجود" in titles
    assert "pacman-mirrors غير موجود" in titles
