"""กู้คืน log "AI เสนอผิด -> คนแก้" ย้อนหลังจากตาราง history (undo) ของแอป

**คำเตือนความถูกต้อง ต้องอ่านก่อนใช้ตัวเลขจากสคริปต์นี้ไปอ้างอิง:**

ระบบนี้ไม่ได้ถูกออกแบบมาเพื่อเก็บ log แบบนี้ตั้งแต่แรก — มันคือระบบ undo ของแอป (บันทึก
"สถานะก่อนหน้า" ไว้ทุกครั้งที่มีคนเรียก move/split, merge, rename, confirm, link,
delete profile ผ่าน store.edit()) เราเอามันมากู้ใช้ย้อนหลังเท่าที่ทำได้ ข้อจำกัดจริงมีดังนี้:

1. **auto_assign() (การจัดกลุ่มอัตโนมัติตอนสแกน) ไม่ถูกบันทึกเลย** — คือทุกครั้งที่ AI เสนอ
   กลุ่มตอนสแกนครั้งแรก ไม่มีร่องรอยในนี้ ตารางนี้เห็นแค่ตอน "คน(หรือสคริปต์) มาแก้ไขภายหลัง"
   เท่านั้น ไม่เห็น "ตอน AI เสนอครั้งแรก" คู่กัน ดังนั้นจำนวนที่นับได้คือ "จำนวนครั้งที่มีการแก้ไข"
   ไม่ใช่ "จำนวนครั้งที่ AI ผิด" (AI อาจผิดมากกว่านี้แต่ยังไม่มีใครไปแก้)
2. **ไม่มีคอลัมน์ระบุว่าใคร/อะไรเป็นคนสั่ง** — move/split ที่มาจากคนกดในแอป กับที่มาจากสคริปต์
   แก้อัตโนมัติ (เช่น voice_av_correction.py) หน้าตาในตารางนี้เหมือนกันทุกประการ แยกไม่ออกจาก
   ข้อมูลอย่างเดียว สคริปต์นี้จึงไม่เดา ไม่ใส่ป้าย "คน" หรือ "สคริปต์" ให้ — รายงานแค่ข้อเท็จจริงว่า
   "สถานะเปลี่ยนจาก A เป็น B" เท่านั้น
3. reject_observations()/unassign_observations() (ฟีเจอร์ "ตัดออก"/"ส่งกลับไปไม่จัดกลุ่ม" ที่สร้าง
   เพิ่มทีหลังในเซสชันนี้) ก็ไม่ถูกบันทึกเช่นกัน (ไม่ได้ครอบด้วย store.edit() ตอนที่เขียน)

เรียก:
  venv/bin/python -m scripts.ai_correction_log data/output/workspace-demo
  venv/bin/python -m scripts.ai_correction_log data/output/workspace-demo --out correction_log.csv
"""

import argparse
import csv
import json
from pathlib import Path

from src.workspace.store import WorkspaceStore


def profile_name_map(snapshot_profiles):
    return {p["id"]: p["name"] for p in snapshot_profiles}


def membership_map(snapshot_memberships):
    return {m["observation_id"]: m for m in snapshot_memberships}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--out", type=Path, default=Path("correction_log.csv"))
    args = parser.parse_args()

    with WorkspaceStore(args.workspace) as store:
        history = store.rows("SELECT id,action,snapshot FROM history ORDER BY id")
        live_profiles = profile_name_map(store.rows("SELECT id,name FROM profiles"))
        live_memberships = membership_map(
            store.rows("SELECT observation_id,profile_id,locked,score,state FROM memberships"))

    parsed = [(row["id"], row["action"], json.loads(row["snapshot"])) for row in history]

    events = []
    for index, (history_id, action, before) in enumerate(parsed):
        before_names = profile_name_map(before["profiles"])
        before_members = membership_map(before["memberships"])

        if index + 1 < len(parsed):
            after = parsed[index + 1][2]
            after_names = profile_name_map(after["profiles"])
            after_members = membership_map(after["memberships"])
        else:
            after_names = live_profiles
            after_members = live_memberships

        if action == "move/split":
            for observation_id, before_member in before_members.items():
                after_member = after_members.get(observation_id)
                if after_member is None:
                    continue
                if before_member["profile_id"] != after_member["profile_id"]:
                    before_name = before_names.get(before_member["profile_id"], "(ยังไม่จัดกลุ่ม)")
                    after_name = after_names.get(after_member["profile_id"], "(ยังไม่จัดกลุ่ม)")
                    events.append({
                        "history_id": history_id, "action": action, "observation_id": observation_id,
                        "from": before_name, "to": after_name,
                    })
        elif action == "merge":
            before_ids = set(before_names)
            after_ids = set(after_names)
            removed = before_ids - after_ids
            for profile_id in removed:
                moved = [oid for oid, member in before_members.items()
                         if member["profile_id"] == profile_id]
                for observation_id in moved:
                    after_member = after_members.get(observation_id)
                    target_name = after_names.get(after_member["profile_id"], "?") if after_member else "?"
                    events.append({
                        "history_id": history_id, "action": action, "observation_id": observation_id,
                        "from": before_names[profile_id], "to": target_name,
                    })
        elif action == "delete profile":
            before_ids = set(before_names)
            after_ids = set(after_names)
            removed = before_ids - after_ids
            for profile_id in removed:
                count = sum(1 for member in before_members.values() if member["profile_id"] == profile_id)
                events.append({
                    "history_id": history_id, "action": action, "observation_id": "",
                    "from": before_names[profile_id], "to": f"(ลบโปรไฟล์ทิ้ง · เคยมี {count} ช่วงผูกอยู่)",
                })

    print(f"ทั้งหมด {len(history)} เหตุการณ์ใน history, แตกออกมาได้ {len(events)} การเปลี่ยนสถานะระดับช่วงเสียง/ภาพ/โปรไฟล์\n")

    move_events = [e for e in events if e["action"] == "move/split"]
    merge_events = [e for e in events if e["action"] == "merge"]
    delete_events = [e for e in events if e["action"] == "delete profile"]

    print(f"move/split ที่กู้คืนรายละเอียดได้: {len(move_events)} ช่วง")
    for event in move_events[:40]:
        print(f"  #{event['history_id']:>4}  {event['from']:<20} -> {event['to']:<20}  obs={event['observation_id'][:12]}...")
    if len(move_events) > 40:
        print(f"  ... อีก {len(move_events) - 40} ช่วง (ดูไฟล์ CSV)")

    print(f"\nmerge ที่กู้คืนรายละเอียดได้: {len(merge_events)} ช่วง")
    for event in merge_events[:10]:
        print(f"  #{event['history_id']:>4}  {event['from']:<20} -> {event['to']:<20}")

    print(f"\nลบโปรไฟล์ถาวร: {len(delete_events)} ครั้ง")
    for event in delete_events:
        print(f"  #{event['history_id']:>4}  {event['from']:<20}  {event['to']}")

    with open(args.out, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["history_id", "action", "observation_id", "from", "to"])
        writer.writeheader()
        writer.writerows(events)
    print(f"\nบันทึกทั้งหมด {len(events)} เหตุการณ์ไว้ที่: {args.out}")


if __name__ == "__main__":
    main()
