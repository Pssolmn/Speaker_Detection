"""สีเป็น presentation metadata ไม่ใช้ตัดสินว่า embedding เป็นคนเดียวกัน.

เก็บใน meta ของ schema เดิม จึงไม่ต้องเปลี่ยนตารางตัวตน/ชื่อของ Workspace เก่า.
เสียงที่ผูกแล้ว resolve สีผ่านภาพ เช่นเดียวกับชื่อ ไม่สำเนาสีไปทุก cue.
"""
import json
import re

PALETTES = {
    "Studio": ["#7C8CFF", "#F26D98", "#45CDB0", "#F2BF68", "#54B8DB", "#BC8CEB", "#EE8D69", "#B8CD70"],
    "Pastel": ["#B8B2FF", "#F2B6CF", "#9EDDCB", "#F1D695", "#9FCFE9", "#DBB1EC", "#EDB79D", "#C8D7A2"],
    "Contrast": ["#56B4E9", "#E69F00", "#009E73", "#CC79A7", "#F0E442", "#D55E00", "#8F9EFF", "#ECECEC"],
}


def valid_color(color):
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("สีต้องอยู่ในรูป #RRGGBB")
    return color.upper()


def palette(store):
    row = store.db.execute("SELECT value FROM meta WHERE key='appearance:palette'").fetchone()
    return json.loads(row[0]) if row else list(PALETTES["Studio"])


def canonical_profile(store, identifier):
    if store.profile(identifier)["kind"] == "voice":
        links = store.rows("SELECT visual_id FROM links WHERE voice_id=?", (identifier,))
        if len(links) == 1:
            return links[0]["visual_id"]
    return identifier


def profile_color(store, identifier, *, resolve=True):
    if resolve:
        identifier = canonical_profile(store, identifier)
    row = store.db.execute("SELECT value FROM meta WHERE key=?", ("appearance:color:" + identifier,)).fetchone()
    if row:
        return row[0]
    # Workspace เก่าได้สีทันทีโดยไม่เขียนไฟล์เมื่อแค่เปิดดู; rowid ไม่เปลี่ยนตอน rename.
    rowid = store.db.execute("SELECT rowid FROM profiles WHERE id=?", (identifier,)).fetchone()[0]
    colors = palette(store)
    return colors[(rowid - 1) % len(colors)]


def set_profile_color(store, identifier, color):
    color = valid_color(color)
    identifier = canonical_profile(store, identifier)
    with store.edit("profile color"):
        store.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("appearance:color:" + identifier, color))


def set_palette(store, colors, *, recolor=False):
    colors = list(dict.fromkeys(valid_color(color) for color in colors))
    if not 1 <= len(colors) <= 64:
        raise ValueError("ใช้สีในชุด 1–64 สี")
    with store.edit("palette"):
        if not recolor:
            # Freeze fallback colors of legacy profiles before changing the palette.
            # Otherwise "future groups only" would silently recolor old workspaces.
            for profile in store.profiles():
                color = profile_color(store, profile["id"], resolve=False)
                store.db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)",
                                 ("appearance:color:" + profile["id"], color))
        store.db.execute("INSERT OR REPLACE INTO meta VALUES ('appearance:palette',?)", (json.dumps(colors),))
        if recolor:
            for index, profile in enumerate(store.profiles()):
                store.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                                 ("appearance:color:" + profile["id"], colors[index % len(colors)]))
