"""Settings persistence + the automatic backup manager.

Backup policy the shop asked for:
  • pick a folder once (a Google Drive Desktop folder → it syncs to the cloud)
  • the DB is copied there automatically ONCE PER DAY
  • copies older than N days (default 3) are deleted from that folder
  • manual Export / Import always available, and never destructive
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta

from .config import (BACKUPS_DIR, DEFAULT_SETTINGS, SETTINGS_PATH,
                     BACKUP_INTERVAL_HOURS, BACKUP_RETENTION_DAYS,
                     BACKUP_TIME)

BACKUP_PREFIX = "bhumiraj_backup_"
BACKUP_GLOB_EXT = ".db"


class SettingsManager:
    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self.data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as fh:
                    saved = json.load(fh)
                if isinstance(saved, dict):
                    # keep unknown keys, fill in any new defaults
                    merged = dict(DEFAULT_SETTINGS)
                    merged.update(saved)
                    self.data = merged
        except (OSError, ValueError):
            self.data = dict(DEFAULT_SETTINGS)
        return self.data

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)      # atomic — never a truncated file
            return True
        except OSError:
            return False

    def get(self, key, default=None):
        val = self.data.get(key, default)
        return default if val is None else val

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def update(self, mapping):
        self.data.update(mapping or {})
        self.save()


class BackupManager:
    """Daily automatic backup into the user's chosen (cloud-synced) folder."""

    def __init__(self, db, settings: SettingsManager):
        self.db = db
        self.s = settings

    # ── helpers ─────────────────────────────────────────────────────
    def target_folder(self):
        """Chosen folder if it is usable, else the local data\\backups folder."""
        folder = (self.s.get("backup_folder", "") or "").strip()
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
                probe = os.path.join(folder, ".bhumiraj_write_test")
                with open(probe, "w") as fh:
                    fh.write("ok")
                os.remove(probe)
                return folder
            except OSError:
                pass          # drive unplugged / no permission → fall back
        return BACKUPS_DIR

    def retention_days(self):
        try:
            n = int(self.s.get("backup_retention_days", BACKUP_RETENTION_DAYS))
        except (TypeError, ValueError):
            n = BACKUP_RETENTION_DAYS
        return max(n, 1)

    def _stamp_name(self):
        return (BACKUP_PREFIX
                + datetime.now().strftime("%Y-%m-%d_%H%M%S")
                + BACKUP_GLOB_EXT)

    def last_backup_time(self):
        raw = self.s.get("last_backup", "")
        if not raw:
            return None
        for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, f)
            except ValueError:
                continue
        return None

    # ── nightly schedule ────────────────────────────────────────────
    def scheduled_time(self):
        """(hour, minute) the nightly backup should run at."""
        raw = str(self.s.get("backup_time", BACKUP_TIME) or BACKUP_TIME).strip()
        try:
            hh, mm = raw.split(":")
            hour, minute = int(hh), int(mm)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
        except (ValueError, AttributeError):
            pass
        hh, mm = BACKUP_TIME.split(":")
        return int(hh), int(mm)

    def last_slot(self, now=None):
        """The most recent scheduled run time that has already passed."""
        now = now or datetime.now()
        hour, minute = self.scheduled_time()
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return today if now >= today else today - timedelta(days=1)

    def next_slot(self, now=None):
        """The next scheduled run time in the future."""
        now = now or datetime.now()
        hour, minute = self.scheduled_time()
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return today if now < today else today + timedelta(days=1)

    def seconds_until_next(self, now=None):
        now = now or datetime.now()
        return max(int((self.next_slot(now) - now).total_seconds()), 1)

    def due(self, now=None):
        """True when tonight's scheduled backup has not been taken yet.

        Missing the exact minute (shop closed, PC off) does not skip the day —
        the run is caught up the next time the app is open.
        """
        if not self.s.get("auto_backup", True):
            return False
        now = now or datetime.now()
        last = self.last_backup_time()
        if last is None:
            return True
        return last < self.last_slot(now)

    # ── actions ─────────────────────────────────────────────────────
    def run(self, force=False):
        """Take a backup if due. Returns (ok, message, path_or_None)."""
        if not force and not self.due():
            return True, "Backup not due yet.", None

        folder = self.target_folder()
        dest = os.path.join(folder, self._stamp_name())
        try:
            self.db.backup(dest)
        except Exception as exc:
            return False, f"Backup failed: {exc}", None

        self.s.set("last_backup", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        removed = self.prune(folder)
        msg = f"Backed up to {folder}"
        if removed:
            msg += f"  ·  {removed} old copy(ies) removed"
        return True, msg, dest

    def prune(self, folder=None):
        """Delete our own backups older than the retention window.

        Only files matching our prefix are ever touched — the user's other
        files in that Google Drive folder are never at risk.
        """
        folder = folder or self.target_folder()
        cutoff = datetime.now() - timedelta(days=self.retention_days())
        removed = 0
        try:
            names = os.listdir(folder)
        except OSError:
            return 0
        for name in names:
            if not (name.startswith(BACKUP_PREFIX)
                    and name.endswith(BACKUP_GLOB_EXT)):
                continue
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            when = self._date_from_name(name)
            if when is None:
                try:
                    when = datetime.fromtimestamp(os.path.getmtime(path))
                except OSError:
                    continue
            if when < cutoff:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        return removed

    @staticmethod
    def _date_from_name(name):
        stem = name[len(BACKUP_PREFIX):-len(BACKUP_GLOB_EXT)]
        for f in ("%Y-%m-%d_%H%M%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(stem, f)
            except ValueError:
                continue
        return None

    def list_backups(self, folder=None):
        """[(name, path, size_bytes, datetime)] newest first."""
        folder = folder or self.target_folder()
        out = []
        try:
            names = os.listdir(folder)
        except OSError:
            return out
        for name in names:
            if not (name.startswith(BACKUP_PREFIX)
                    and name.endswith(BACKUP_GLOB_EXT)):
                continue
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            when = self._date_from_name(name)
            try:
                size = os.path.getsize(path)
                if when is None:
                    when = datetime.fromtimestamp(os.path.getmtime(path))
            except OSError:
                continue
            out.append((name, path, size, when))
        out.sort(key=lambda r: r[3], reverse=True)
        return out

    # ── manual export / import ──────────────────────────────────────
    def export_to(self, dest_path):
        """Explicit 'Export Database' — writes wherever the user points."""
        if not dest_path:
            raise ValueError("No destination chosen.")
        if not dest_path.lower().endswith(".db"):
            dest_path += ".db"
        self.db.backup(dest_path)
        return dest_path

    def import_from(self, src_path):
        """Explicit 'Import Database'. Validates, safety-copies, then swaps.

        Returns the path of the safety copy of the PREVIOUS database.
        """
        if not src_path or not os.path.exists(src_path):
            raise FileNotFoundError("Choose a valid .db backup file.")
        return self.db.restore(src_path)
