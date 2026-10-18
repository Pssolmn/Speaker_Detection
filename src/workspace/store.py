"""SQLite workspace: ID ไม่เปลี่ยนตามชื่อ; การตรวจแก้บันทึกทันทีและย้อนกลับได้.

หนึ่ง connection ต่อ thread (worker เปิด Store ของตัวเอง) ใช้ transaction/WAL
เพื่อไม่ให้การปิดโปรแกรมระหว่าง scan ทำให้ชื่อที่ผู้ใช้ตรวจแล้วเสียหาย.
ไฟล์วิดีโอต้นฉบับไม่ถูกคัดลอก/เขียนทับ; ย้ายเครื่องแล้ว relink ด้วย SHA256.
"""

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import numpy as np
from filelock import FileLock

from src.core.control import check_cancel


def fingerprint(path, cancel=None):
    """อ่านทีละ 1 MiB ไม่โหลดวิดีโอทั้งไฟล์เข้า RAM; ใช้เนื้อหาไม่ใช่ชื่อไฟล์."""
    digest = sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(block)
    return digest.hexdigest()


def cache_key(*values):
    return sha256(json.dumps(values, sort_keys=True, ensure_ascii=False,
                             allow_nan=False).encode()).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE media(id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL,
 path TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE profiles(id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('visual','voice')),
 name TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE runs(key TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id),
 kind TEXT NOT NULL, settings TEXT NOT NULL, cursor_ms INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'running');
CREATE TABLE observations(id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id),
 run_key TEXT NOT NULL REFERENCES runs(key), kind TEXT NOT NULL,
 start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL CHECK(end_ms>start_ms),
 model_key TEXT NOT NULL, features BLOB, preview TEXT, evidence TEXT NOT NULL);
CREATE TABLE memberships(observation_id TEXT PRIMARY KEY REFERENCES observations(id),
 profile_id TEXT REFERENCES profiles(id), locked INTEGER NOT NULL DEFAULT 0,
 score REAL, state TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE links(voice_id TEXT NOT NULL REFERENCES profiles(id),
 visual_id TEXT NOT NULL REFERENCES profiles(id), PRIMARY KEY(voice_id,visual_id));
CREATE TABLE subtitles(media_id TEXT NOT NULL REFERENCES media(id), segment_id INTEGER NOT NULL,
 segment TEXT NOT NULL, manual_profile_id TEXT REFERENCES profiles(id),
 manual_name TEXT, PRIMARY KEY(media_id,segment_id));
CREATE TABLE history(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE INDEX obs_media_time ON observations(media_id,kind,start_ms,end_ms);
CREATE INDEX member_profile ON memberships(profile_id);
"""


class WorkspaceStore:
    def __init__(self, directory, *, create=False, name=None):
        self.root = Path(directory).expanduser().resolve()
        database = self.root / "workspace.sqlite3"
        if create:
            # ไม่เปลี่ยนโฟลเดอร์ข้อมูลเดิมให้กลายเป็น workspace โดยเงียบ ๆ
            if self.root.exists() and any(self.root.iterdir()):
                raise ValueError("Create a workspace in a new or empty folder")
            self.root.mkdir(parents=True, exist_ok=True)
        elif not database.is_file():
            raise FileNotFoundError("This folder has no workspace.sqlite3")
        self.db = sqlite3.connect(database, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        try:
            if create:
                self.db.executescript(SCHEMA)
                self.db.executemany("INSERT INTO meta VALUES (?,?)", [
                    ("schema_version", "1"), ("id", uuid4().hex),
                    ("name", name or self.root.name)])
                self.db.commit()
            version = self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if not version or version[0] != "1":
                raise ValueError("Unsupported workspace schema; original database was not migrated")
        except Exception:
            self.db.close()
            raise
        (self.root / "cache").mkdir(exist_ok=True)
        (self.root / "evidence").mkdir(exist_ok=True)
        # ใช้ lock ตัวเดียวต่อ Store จึงเรียก edit ซ้อนใน CLI/worker ได้
        self.lock = FileLock(str(self.root / ".scan.lock"), timeout=0)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def rows(self, sql, parameters=()):
        return [dict(row) for row in self.db.execute(sql, parameters)]

    def media(self):
        return self.rows("SELECT * FROM media ORDER BY rowid")

    def project_name(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='name'").fetchone()
        return row[0] if row else self.root.name

    def rename_project(self, name):
        name = name.strip()
        if not name or len(name) > 200 or any(char in name for char in "\n\r\x00"):
            raise ValueError("ใช้ชื่อโปรเจกต์ 1–200 ตัวอักษรในบรรทัดเดียว")
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('name',?)", (name,))

    def create_profile(self, kind, name):
        name = name.strip()
        if not name or len(name) > 200 or any(char in name for char in "\n\r\x00"):
            raise ValueError("ใช้ชื่อโปรไฟล์ 1–200 ตัวอักษรในบรรทัดเดียว")
        with self.edit("create profile"):
            return self._new_profile(kind, name)

    def delete_profile(self, identifier):
        profile = self.profile(identifier)
        with self.edit("delete profile"):
            # เก็บหลักฐานและชื่อที่คนยืนยันบนซับไว้ ไม่เอา AI มาเปลี่ยนแทน.
            from src.workspace.appearance import canonical_profile
            resolved_name = self.profile(canonical_profile(self, identifier))["name"]
            self.db.execute("UPDATE subtitles SET manual_name=?,manual_profile_id=NULL WHERE manual_profile_id=?",
                            (resolved_name, identifier))
            if profile["kind"] == "visual":
                linked_voices = self.rows("SELECT voice_id FROM links WHERE visual_id=? AND voice_id IN "
                    "(SELECT voice_id FROM links GROUP BY voice_id HAVING COUNT(*)=1)", (identifier,))
                self.db.executemany("UPDATE subtitles SET manual_name=?,manual_profile_id=NULL WHERE manual_profile_id=?",
                                    [(profile["name"], item["voice_id"]) for item in linked_voices])
            self.db.execute("UPDATE memberships SET profile_id=NULL,locked=1,score=NULL,state='pending' WHERE profile_id=?",
                            (identifier,))
            self.db.execute("DELETE FROM links WHERE voice_id=? OR visual_id=?", (identifier, identifier))
            self.db.execute("DELETE FROM profiles WHERE id=?", (identifier,))

    def add_media(self, path, cancel=None):
        path = Path(path).expanduser().resolve(strict=True)
        digest = fingerprint(path, cancel)
        # lock ครอบทั้ง SELECT+INSERT กัน race ตอนสองฝั่ง (เช่น CLI กับ GUI) เพิ่มไฟล์ใหม่ไฟล์เดียวกันพร้อมกัน
        with self.lock, self.db:
            old = self.db.execute("SELECT id FROM media WHERE digest=?", (digest,)).fetchone()
            identifier = old[0] if old else uuid4().hex
            self.db.execute("INSERT INTO media VALUES (?,?,?,?) ON CONFLICT(digest) "
                            "DO UPDATE SET path=excluded.path", (identifier, digest, str(path), path.name))
        return identifier

    def media_path(self, identifier):
        row = self.db.execute("SELECT path FROM media WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        return Path(row[0])

    def relink_media(self, identifier, path, cancel=None):
        row = self.db.execute("SELECT digest FROM media WHERE id=?", (identifier,)).fetchone()
        path = Path(path).resolve(strict=True)
        if row is None or fingerprint(path, cancel) != row[0]:
            raise ValueError("The selected file is not the original media (SHA256 differs)")
        with self.db:
            self.db.execute("UPDATE media SET path=? WHERE id=?", (str(path), identifier))

    def begin_run(self, media_id, kind, settings, cancel=None):
        media = self.db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        if media is None or fingerprint(media["path"], cancel) != media["digest"]:
            raise ValueError("Media changed or is missing; add the new version as a new episode")
        key = cache_key(media["digest"], kind, settings)
        active_name = f"active:{media_id}:{kind}"
        previous = self.db.execute("SELECT value FROM meta WHERE key=?", (active_name,)).fetchone()
        if previous and previous[0] != key:
            locked = self.db.execute("SELECT 1 FROM observations o JOIN memberships m ON m.observation_id=o.id "
                                     "WHERE o.run_key=? AND m.locked=1 LIMIT 1", (previous[0],)).fetchone()
            if locked:
                raise ValueError("Model/settings changed after manual review. Keep the existing settings or use a new workspace; reviews are preserved")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO runs(key,media_id,kind,settings) VALUES (?,?,?,?)",
                            (key, media_id, kind, _json(settings)))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (active_name, key))
        return dict(self.db.execute("SELECT * FROM runs WHERE key=?", (key,)).fetchone())

    def checkpoint(self, key, cursor_ms, state="running"):
        if state not in {"running", "complete", "cancelled", "error"}:
            raise ValueError("Invalid run state")
        with self.db:
            self.db.execute("UPDATE runs SET cursor_ms=?,state=? WHERE key=?", (cursor_ms, state, key))

    def put_observation(self, *, identifier, media_id, run_key, kind, start_ms, end_ms,
                        model_key, features=None, preview=None, evidence=None):
        if kind not in {"visual", "voice"} or start_ms < 0 or end_ms <= start_ms:
            raise ValueError("Invalid observation")
        vector = None
        if features is not None:
            values = np.asarray(features, dtype="<f4")
            if values.ndim != 1 or not values.size or not np.isfinite(values).all():
                raise ValueError("Features must be a finite nonempty vector")
            vector = values.tobytes()
        if preview:
            resolved = (self.root / preview).resolve()
            if not resolved.is_relative_to(self.root):
                raise ValueError("Preview must be inside this workspace")
        # INSERT OR IGNORE ทำให้ resume ไม่ลบ membership ที่ตรวจด้วยมือแล้ว
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (identifier, media_id, run_key, kind, int(start_ms), int(end_ms),
                             model_key, vector, preview, _json(evidence or {})))
            self.db.execute("INSERT OR IGNORE INTO memberships(observation_id) VALUES (?)", (identifier,))

    def observations(self, *, media_id=None, profile_id=None, kind=None):
        clauses = ["o.run_key=COALESCE((SELECT value FROM meta WHERE key='active:'||o.media_id||':'||o.kind),o.run_key)"]
        parameters = []
        for column, value in (("o.media_id", media_id), ("m.profile_id", profile_id), ("o.kind", kind)):
            if value is not None:
                clauses.append(column + "=?")
                parameters.append(value)
        sql = ("SELECT o.*,m.profile_id,m.locked,m.score,m.state FROM observations o "
               "JOIN memberships m ON m.observation_id=o.id")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        records = self.rows(sql + " ORDER BY o.media_id,o.start_ms,o.id", parameters)
        for record in records:
            record["evidence"] = json.loads(record["evidence"])
            if record["features"] is not None:
                record["features"] = np.frombuffer(record["features"], dtype="<f4").copy()
        return records

    def profiles(self, kind=None):
        sql = ("SELECT p.*,COUNT(o.id) AS count FROM profiles p "
               "LEFT JOIN memberships m ON m.profile_id=p.id "
               "LEFT JOIN observations o ON o.id=m.observation_id AND "
               "o.run_key=COALESCE((SELECT value FROM meta WHERE key='active:'||o.media_id||':'||o.kind),o.run_key)")
        parameters = ()
        if kind:
            sql += " WHERE p.kind=?"
            parameters = (kind,)
        return self.rows(sql + " GROUP BY p.id ORDER BY p.rowid", parameters)

    def profile(self, identifier):
        row = self.db.execute("SELECT * FROM profiles WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        return dict(row)

    def _new_profile(self, kind, name=None):
        if kind not in {"visual", "voice"}:
            raise ValueError("Unknown profile kind")
        counter = f"counter:{kind}"
        previous = self.db.execute("SELECT value FROM meta WHERE key=?", (counter,)).fetchone()
        number = int(previous[0]) + 1 if previous else len(self.profiles(kind)) + 1
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (counter, str(number)))
        identifier = uuid4().hex
        self.db.execute("INSERT INTO profiles VALUES (?,?,?,0)",
                        (identifier, kind, name or f"{'ตัวละคร' if kind == 'visual' else 'ผู้พูด'} {number:03d}"))
        from src.workspace.appearance import palette
        colors = palette(self)
        color_index = self.db.execute("SELECT rowid FROM profiles WHERE id=?", (identifier,)).fetchone()[0] - 1
        self.db.execute("INSERT INTO meta VALUES (?,?)", ("appearance:color:" + identifier,
                        colors[color_index % len(colors)]))
        return identifier

    def auto_assign(self, observation_id, profile_id=None, *, new=False, score=None, state="proposed"):
        row = self.db.execute("SELECT m.locked,o.kind FROM memberships m JOIN observations o "
                              "ON o.id=m.observation_id WHERE o.id=?", (observation_id,)).fetchone()
        if row is None or row["locked"]:
            return
        if score is not None and (not np.isfinite(score) or not 0 <= score <= 1):
            raise ValueError("Invalid similarity score")
        with self.db:
            if new:
                profile_id = self._new_profile(row["kind"])
            if profile_id and self.profile(profile_id)["kind"] != row["kind"]:
                raise ValueError("Cannot assign a voice observation to a visual profile")
            self.db.execute("UPDATE memberships SET profile_id=?,score=?,state=? WHERE observation_id=?",
                            (profile_id, score, state, observation_id))
        return profile_id

    @contextmanager
    def edit(self, action):
        """บันทึกเฉพาะข้อมูลแก้มือ ไม่สำเนาภาพ/เวกเตอร์ขนาดใหญ่ลง undo history."""
        with self.lock, self.db:
            snapshot = {table: self.rows(f"SELECT * FROM {table}")
                        for table in ("profiles", "memberships", "links", "subtitles")}
            snapshot["appearance"] = self.rows("SELECT * FROM meta WHERE key LIKE 'appearance:%'")
            self.db.execute("INSERT INTO history(action,snapshot) VALUES (?,?)", (action, _json(snapshot)))
            yield

    def rename(self, profile_id, name):
        name = name.strip()
        if not name or len(name) > 200 or any(character in name for character in "\r\n\x00"):
            raise ValueError("Use a name of 1–200 characters on one line")
        self.profile(profile_id)
        with self.edit("rename"):
            self.db.execute("UPDATE profiles SET name=? WHERE id=?", (name, profile_id))

    def confirm(self, profile_id):
        self.profile(profile_id)
        with self.edit("confirm"):
            self.db.execute("UPDATE profiles SET confirmed=1 WHERE id=?", (profile_id,))
            self.db.execute("UPDATE memberships SET locked=1,state='confirmed' WHERE profile_id=?", (profile_id,))

    def move(self, observation_ids, target_id=None):
        identifiers = list(dict.fromkeys(observation_ids))
        if not identifiers:
            raise ValueError("Select at least one observation")
        records = [self.db.execute("SELECT kind FROM observations WHERE id=?", (item,)).fetchone()
                   for item in identifiers]
        if any(row is None for row in records) or len({row[0] for row in records}) != 1:
            raise ValueError("Select observations of one kind")
        kind = records[0][0]
        if target_id and self.profile(target_id)["kind"] != kind:
            raise ValueError("Target has a different kind")
        with self.edit("move/split"):
            target_id = target_id or self._new_profile(kind)
            self.db.executemany("UPDATE memberships SET profile_id=?,locked=1,state='confirmed',score=NULL "
                                "WHERE observation_id=?", [(target_id, item) for item in identifiers])
        return target_id

    def merge(self, source_id, target_id):
        if source_id == target_id or self.profile(source_id)["kind"] != self.profile(target_id)["kind"]:
            raise ValueError("Choose two different profiles of the same kind")
        if self.profile(source_id)["kind"] == "voice":
            targets = self.rows("SELECT DISTINCT visual_id FROM links WHERE voice_id IN (?,?)", (source_id, target_id))
            if len(targets) > 1:
                raise ValueError("กลุ่มเสียงผูกกับคนละตัวละคร ให้ตรวจ/ยกเลิกคู่ที่ผิดก่อนรวม")
        with self.edit("merge"):
            self.db.execute("UPDATE memberships SET profile_id=?,locked=1,state='confirmed',score=NULL WHERE profile_id=?",
                            (target_id, source_id))
            self.db.execute("UPDATE subtitles SET manual_profile_id=? WHERE manual_profile_id=?", (target_id, source_id))
            for link in self.rows("SELECT * FROM links WHERE voice_id=? OR visual_id=?", (source_id, source_id)):
                voice = target_id if link["voice_id"] == source_id else link["voice_id"]
                visual = target_id if link["visual_id"] == source_id else link["visual_id"]
                self.db.execute("INSERT OR IGNORE INTO links VALUES (?,?)", (voice, visual))
            self.db.execute("DELETE FROM links WHERE voice_id=? OR visual_id=?", (source_id, source_id))
            self.db.execute("DELETE FROM profiles WHERE id=?", (source_id,))

    def link(self, voice_id, visual_id, *, replace=False):
        if self.profile(voice_id)["kind"] != "voice" or self.profile(visual_id)["kind"] != "visual":
            raise ValueError("Link a voice profile to a visual profile")
        with self.edit("link voice to character"):
            previous = self.rows("SELECT visual_id FROM links WHERE voice_id=?", (voice_id,))
            if any(item["visual_id"] != visual_id for item in previous) and not replace:
                raise ValueError("เสียงนี้ผูกกับตัวละครอื่นแล้ว ต้องยืนยันเปลี่ยนคู่ก่อน")
            # หนึ่งกลุ่มเสียงมีตัวละครปลายทางเดียว; หลายโทนเสียงอาจเป็นคนเดียวกันได้.
            if replace:
                self.db.execute("DELETE FROM links WHERE voice_id=?", (voice_id,))
            self.db.execute("INSERT OR IGNORE INTO links VALUES (?,?)", (voice_id, visual_id))

    def unlink(self, voice_id, visual_id):
        with self.edit("unlink"):
            self.db.execute("DELETE FROM links WHERE voice_id=? AND visual_id=?", (voice_id, visual_id))

    def undo(self):
        with self.lock:
            return self._undo()

    def _undo(self):
        row = self.db.execute("SELECT * FROM history ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return False
        snapshot = json.loads(row["snapshot"])
        # UI ปิดการแก้มือระหว่าง scan; undo ไม่ควรลบหลักฐานที่ scan เพิ่มภายหลัง
        with self.db:
            self.db.execute("DELETE FROM links")
            self.db.execute("DELETE FROM subtitles")
            for record in snapshot["profiles"]:
                self.db.execute("INSERT INTO profiles VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                                "name=excluded.name,confirmed=excluded.confirmed", tuple(record.values()))
            for record in snapshot["memberships"]:
                self.db.execute("UPDATE memberships SET profile_id=?,locked=?,score=?,state=? WHERE observation_id=?",
                                (record["profile_id"], record["locked"], record["score"], record["state"], record["observation_id"]))
            for record in snapshot["links"]:
                self.db.execute("INSERT INTO links VALUES (?,?)", tuple(record.values()))
            for record in snapshot["subtitles"]:
                self.db.execute("INSERT OR REPLACE INTO subtitles VALUES (?,?,?,?,?)", tuple(record.values()))
            old_ids = {item["id"] for item in snapshot["profiles"]}
            for profile in self.profiles():
                if profile["id"] not in old_ids and not profile["count"]:
                    used = self.db.execute("SELECT 1 FROM memberships WHERE profile_id=? UNION ALL "
                                           "SELECT 1 FROM links WHERE voice_id=? OR visual_id=? UNION ALL "
                                           "SELECT 1 FROM subtitles WHERE manual_profile_id=?",
                                           (profile["id"],) * 4).fetchone()
                    if not used:
                        self.db.execute("DELETE FROM profiles WHERE id=?", (profile["id"],))
            if "appearance" in snapshot:
                # รักษาสีของกลุ่มที่ค้นพบหลัง snapshot; undo เก่าไม่มีสีไม่ไปล้างสีใหม่.
                current = {item["id"] for item in self.profiles()}
                for key in [row["key"] for row in self.rows("SELECT key FROM meta WHERE key LIKE 'appearance:%'")]:
                    identifier = key.removeprefix("appearance:color:")
                    if not key.startswith("appearance:color:") or identifier in old_ids or identifier not in current:
                        self.db.execute("DELETE FROM meta WHERE key=?", (key,))
                self.db.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)",
                                    [(item["key"], item["value"]) for item in snapshot["appearance"]])
            self.db.execute("DELETE FROM history WHERE id=?", (row["id"],))
        return True

    def import_subtitles(self, media_id, segments):
        from dataclasses import asdict
        segments = list(segments)
        if len({item.id for item in segments}) != len(segments):
            raise ValueError("Duplicate subtitle IDs")
        with self.edit("import subtitles"):
            for segment in segments:
                # ID เดิมแต่ข้อความ/เวลาต่าง: ไม่เอาคำตอบเก่าไปแปะผิดบรรทัด
                existing = self.db.execute("SELECT segment FROM subtitles WHERE media_id=? AND segment_id=?",
                                           (media_id, segment.id)).fetchone()
                encoded = _json(asdict(segment))
                if existing is None:
                    self.db.execute("INSERT INTO subtitles VALUES (?,?,?,NULL,NULL)", (media_id, segment.id, encoded))
                elif existing[0] != encoded:
                    raise ValueError("Subtitle IDs changed contents; import into a separate media/project to preserve reviews")

    def import_editor_session(self, media_id, segments, manual_labels):
        """รับงานจากหน้าตรวจ reference เดิม; ไม่เลื่อนข้อเสนอ AI เก่าเป็นคำยืนยัน.

        เป็นการย้ายเข้าระบบกลางครั้งเดียว ไม่ sync สองหน้าต่างที่แก้คนละ state.
        ถ้า cue ID ขัดกับงานปลายทาง ให้หยุดและเก็บข้อมูลเดิมทั้งสองฝั่ง.
        """
        from dataclasses import asdict
        segments = list(segments)
        if len({item.id for item in segments}) != len(segments):
            raise ValueError("Duplicate subtitle IDs")
        with self.edit("import legacy editor session"):
            for segment in segments:
                name = (manual_labels.get(segment.id) or "").strip() or None
                if name and (len(name) > 200 or any(char in name for char in "\n\r\x00")):
                    raise ValueError("Invalid manual name")
                encoded = _json(asdict(segment))
                old = self.db.execute("SELECT * FROM subtitles WHERE media_id=? AND segment_id=?",
                                      (media_id, segment.id)).fetchone()
                if old and old["segment"] != encoded:
                    raise ValueError("ซับปลายทางมีเนื้อหาต่างกัน กรุณาเลือก Workspace ใหม่เพื่อไม่ทับงานเดิม")
                if old and (old["manual_profile_id"] or old["manual_name"]):
                    old_name = self.profile(old["manual_profile_id"])["name"] if old["manual_profile_id"] else old["manual_name"]
                    if name and old_name != name:
                        raise ValueError("คำตอบแก้มือขัดกับ Workspace ปลายทาง — ยังไม่เปลี่ยนข้อมูล")
                    continue
                self.db.execute("INSERT INTO subtitles VALUES (?,?,?,NULL,?) ON CONFLICT(media_id,segment_id) "
                                "DO UPDATE SET manual_name=excluded.manual_name",
                                (media_id, segment.id, encoded, name))

    def label_subtitle(self, media_id, segment_id, *, profile_id=None, name=None):
        if not self.db.execute("SELECT 1 FROM subtitles WHERE media_id=? AND segment_id=?", (media_id, segment_id)).fetchone():
            raise KeyError("Unknown subtitle")
        if profile_id:
            self.profile(profile_id)
        if name and (len(name) > 200 or any(char in name for char in '\n\r\x00')):
            raise ValueError("Invalid manual name")
        with self.edit("label subtitle"):
            self.db.execute("UPDATE subtitles SET manual_profile_id=?,manual_name=? WHERE media_id=? AND segment_id=?",
                            (profile_id, (name or '').strip() or None, media_id, segment_id))

    def subtitle(self, media_id, segment_id):
        """อ่าน cue ตาม ID คงที่ ไม่ใช้เลขแถวที่เปลี่ยนเมื่อเรียงเวลา."""
        from src.core.models import SubtitleSegment
        row = self.db.execute("SELECT segment FROM subtitles WHERE media_id=? AND segment_id=?",
                              (media_id, segment_id)).fetchone()
        if row is None:
            raise KeyError("Unknown subtitle")
        return SubtitleSegment(**json.loads(row[0]))

    def update_subtitle(self, media_id, segment):
        """แก้ข้อความ/เวลาโดยคง manual profile ID; ไม่แก้ observations ของ AI.

        attribution จะคำนวณ overlap จากเวลาปัจจุบันทุกครั้งที่อ่าน จึงไม่ต้อง
        สแกนวิดีโอซ้ำเมื่อเลื่อนเวลาเข้าออก. ผู้ใช้ย้อนการแก้นี้ได้เหมือน rename.
        """
        from dataclasses import asdict
        from src.core.models import SubtitleSegment
        segment = SubtitleSegment(**asdict(segment))  # ตรวจแม้ผู้เรียกแก้ dataclass หลังสร้าง
        with self.edit("edit subtitle"):
            self.subtitle(media_id, segment.id)
            self.db.execute("UPDATE subtitles SET segment=? WHERE media_id=? AND segment_id=?",
                            (_json(asdict(segment)), media_id, segment.id))

    def _next_subtitle_id(self, media_id):
        # counter อยู่นอก snapshot ของ undo เพื่อไม่ใช้ ID ของ cue ที่ลบไปแล้วซ้ำ.
        key = f"counter:subtitle:{media_id}"
        counter = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        maximum = self.db.execute("SELECT COALESCE(MAX(segment_id),0) FROM subtitles WHERE media_id=?",
                                 (media_id,)).fetchone()[0]
        value = max(maximum, int(counter[0]) if counter else 0) + 1
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))
        return value

    def add_subtitle(self, media_id, start_ms, end_ms, text=""):
        from dataclasses import asdict
        from src.core.models import SubtitleSegment
        with self.edit("add subtitle"):
            segment = SubtitleSegment(self._next_subtitle_id(media_id), start_ms, end_ms, text)
            self.db.execute("INSERT INTO subtitles VALUES (?,?,?,NULL,NULL)",
                            (media_id, segment.id, _json(asdict(segment))))
        return segment.id

    def delete_subtitles(self, media_id, segment_ids):
        identifiers = list(dict.fromkeys(segment_ids))
        if not identifiers:
            raise ValueError("เลือกบรรทัดที่จะลบก่อน")
        with self.edit("delete subtitles"):
            for identifier in identifiers:
                self.subtitle(media_id, identifier)
            self.db.executemany("DELETE FROM subtitles WHERE media_id=? AND segment_id=?",
                                [(media_id, identifier) for identifier in identifiers])

    def split_subtitle(self, media_id, segment_id, position_ms, text_offset):
        """แยก ณ playhead และตำแหน่งเคอร์เซอร์ข้อความ; คงชื่อแก้มือทั้งสองส่วน."""
        from dataclasses import asdict, replace
        with self.edit("split subtitle"):
            original = self.subtitle(media_id, segment_id)
            if not original.start_ms < position_ms < original.end_ms:
                raise ValueError("วางตำแหน่งเล่นไว้ภายในช่วงซับที่จะแยก")
            if not 0 <= text_offset <= len(original.text):
                raise ValueError("ตำแหน่งแบ่งข้อความไม่ถูกต้อง")
            left = replace(original, end_ms=position_ms, text=original.text[:text_offset].rstrip())
            right = replace(original, id=self._next_subtitle_id(media_id), start_ms=position_ms,
                            text=original.text[text_offset:].lstrip())
            self.db.execute("UPDATE subtitles SET segment=? WHERE media_id=? AND segment_id=?",
                            (_json(asdict(left)), media_id, segment_id))
            self.db.execute("INSERT INTO subtitles SELECT media_id,?,?,manual_profile_id,manual_name "
                            "FROM subtitles WHERE media_id=? AND segment_id=?",
                            (right.id, _json(asdict(right)), media_id, segment_id))
        return right.id

    def join_subtitles(self, media_id, segment_ids):
        """รวม cue ติดกันตามเวลา; ไม่ยุบคำตอบคนละคนเข้าด้วยกันโดยเงียบ ๆ."""
        from dataclasses import asdict, replace
        identifiers = set(segment_ids)
        if len(identifiers) < 2:
            raise ValueError("เลือกอย่างน้อยสองบรรทัดที่อยู่ติดกัน")
        with self.edit("join subtitles"):
            rows = self.rows("SELECT * FROM subtitles WHERE media_id=? "
                             "ORDER BY json_extract(segment,'$.start_ms'),segment_id", (media_id,))
            indices = [i for i, row in enumerate(rows) if row["segment_id"] in identifiers]
            if len(indices) != len(identifiers) or indices != list(range(indices[0], indices[-1] + 1)):
                raise ValueError("เลือกบรรทัดที่อยู่ติดกันเท่านั้น")
            selected = [rows[i] for i in indices]
            segments = [self.subtitle(media_id, row["segment_id"]) for row in selected]
            labels = {(row["manual_profile_id"], row["manual_name"], segment.script_character)
                      for row, segment in zip(selected, segments)}
            if len(labels) > 1:
                raise ValueError("ชื่อที่กำหนดไว้ต่างกัน กรุณาตรวจและกำหนดชื่อให้ตรงก่อนรวม")
            joined = replace(segments[0], end_ms=max(item.end_ms for item in segments),
                             text="\n".join(item.text for item in segments if item.text))
            self.db.execute("UPDATE subtitles SET segment=? WHERE media_id=? AND segment_id=?",
                            (_json(asdict(joined)), media_id, joined.id))
            self.db.executemany("DELETE FROM subtitles WHERE media_id=? AND segment_id=?",
                                [(media_id, item.id) for item in segments[1:]])
        return joined.id

    def import_review(self, media_id, path):
        """JSON เป็นผลตรวจ ไม่ใช่ backup โมเดล: นำเข้าซับ/คำตอบแก้มือเท่านั้น.

        ID โปรไฟล์ใช้ต่อเมื่อเป็น Workspace เดียวกัน; ข้าม Workspace เก็บชื่อแทน
        และไม่เอาผล AI ที่ export ไปแล้วกลับมายืนยันเป็นคำตอบของคน.
        """
        from dataclasses import asdict
        from src.io.result_export import load_results_json
        segments, results = load_results_json(path)
        digest = self.db.execute("SELECT digest FROM media WHERE id=?", (media_id,)).fetchone()
        if digest is None:
            raise KeyError("Unknown media")
        workspace_id = self.db.execute("SELECT value FROM meta WHERE key='id'").fetchone()[0]
        profiles = {item["id"] for item in self.profiles()}
        with self.edit("import review JSON"):
            for segment, result in zip(segments, results):
                if result.evidence.get("media_digest", digest[0]) != digest[0]:
                    raise ValueError("Review belongs to different media (SHA256 differs)")
                encoded = _json(asdict(segment))
                existing = self.db.execute("SELECT * FROM subtitles WHERE media_id=? AND segment_id=?",
                                           (media_id, segment.id)).fetchone()
                if existing and existing["segment"] != encoded:
                    raise ValueError("Subtitle contents differ; existing reviews were preserved")
                profile_id = result.evidence.get("manual_profile_id")
                if result.evidence.get("workspace_id") != workspace_id or profile_id not in profiles:
                    profile_id = None
                name = None if profile_id else result.manual_character
                if name and (len(name) > 200 or any(char in name for char in '\n\r\x00')):
                    raise ValueError("Invalid manual name")
                if existing and (existing["manual_profile_id"] or existing["manual_name"]):
                    if (profile_id or name) and (profile_id, name) != (existing["manual_profile_id"], existing["manual_name"]):
                        raise ValueError("Conflicting manual review; clear the old label explicitly before importing")
                    continue
                self.db.execute("INSERT INTO subtitles VALUES (?,?,?,?,?) ON CONFLICT(media_id,segment_id) "
                                "DO UPDATE SET manual_profile_id=excluded.manual_profile_id,manual_name=excluded.manual_name",
                                (media_id, segment.id, encoded, profile_id, name))
