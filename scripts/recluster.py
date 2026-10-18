"""จัดกลุ่มใหม่ (re-cluster) โดยไม่ต้องสแกนวิดีโอ/เสียงซ้ำ — ใช้ embedding ที่คำนวณไว้แล้ว.

กลุ่มที่ "ยืนยันแล้ว" (confirmed) จะไม่ถูกแตะเลย; แก้เฉพาะข้อเสนอ AI ที่ยังไม่ยืนยัน
ใช้แก้ปัญหาแบบ "แยกมากไป" (threshold เข้มไป) หรือ "รวมผิดคนไป" (threshold หลวมไป)
โดยไม่ต้องรัน YOLO/CCIP/diarization ใหม่ทั้งตอน (ขั้นตอนที่หนักและช้าที่สุด)

ค่าเริ่มต้น (ใช้ตอนสแกนปกติ): visual=encoder.threshold (จาก metrics.json), voice=0.45, margin=0.05

ตัวอย่าง:
  # ดูก่อนว่าจะเกิดอะไรขึ้น (ไม่เขียนอะไรลงฐานข้อมูล)
  venv/bin/python -m scripts.recluster data/output/oshi-no-ko-s3e02 --kind visual --threshold 0.30

  # ใช้จริง
  venv/bin/python -m scripts.recluster data/output/oshi-no-ko-s3e02 --kind visual --threshold 0.30 --apply
  venv/bin/python -m scripts.recluster data/output/oshi-no-ko-s3e02 --kind voice --threshold 0.35 --margin 0.08 --apply
"""

import argparse

from src.workspace.clustering import cluster_observations, cosine_distances
from src.workspace.store import WorkspaceStore


def reset_unlocked(store, kind, media_id=None):
    """คืนค่า observation ที่ยังไม่ล็อกกลับเป็นยังไม่จัดกลุ่ม; ไม่แตะอันที่ยืนยัน/ล็อกแล้วเด็ดขาด"""
    clause = "o.kind=?" + (" AND o.media_id=?" if media_id else "")
    parameters = (kind, media_id) if media_id else (kind,)
    affected = store.rows(
        "SELECT m.observation_id FROM memberships m JOIN observations o ON o.id=m.observation_id "
        f"WHERE {clause} AND m.locked=0 AND m.profile_id IS NOT NULL", parameters)
    with store.db:
        store.db.execute(
            f"UPDATE memberships SET profile_id=NULL,score=NULL,state='pending' WHERE observation_id IN "
            f"(SELECT o.id FROM observations o WHERE {clause} AND o.id IN "
            "(SELECT observation_id FROM memberships WHERE locked=0))", parameters)
        # เก็บกวาดโปรไฟล์ที่ไม่มีสมาชิกเหลือแล้วและยังไม่ยืนยัน ไม่แตะโปรไฟล์ที่ยืนยันแล้วแม้จะว่าง
        empty = store.rows(
            "SELECT p.id FROM profiles p LEFT JOIN memberships m ON m.profile_id=p.id "
            "WHERE p.kind=? AND p.confirmed=0 GROUP BY p.id HAVING COUNT(m.observation_id)=0", (kind,))
        for row in empty:
            store.db.execute("DELETE FROM links WHERE voice_id=? OR visual_id=?", (row["id"], row["id"]))
            store.db.execute("DELETE FROM profiles WHERE id=?", (row["id"],))
    return len(affected)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workspace")
    parser.add_argument("--kind", required=True, choices=["visual", "voice"])
    parser.add_argument("--threshold", type=float, required=True,
                        help="ต่ำ = เข้มงวดขึ้น (แยกมากขึ้น); สูง = หลวมขึ้น (รวมมากขึ้น)")
    parser.add_argument("--margin", type=float, default=.05)
    parser.add_argument("--media-id", default=None, help="จำกัดเฉพาะตอนนี้; ไม่ใส่ = ทั้งโปรเจกต์")
    parser.add_argument("--apply", action="store_true", help="ไม่ใส่ = dry-run แสดงผลกระทบอย่างเดียว ไม่เขียนอะไร")
    args = parser.parse_args()

    with WorkspaceStore(args.workspace) as store:
        before = {p["id"]: p["count"] for p in store.profiles(args.kind)}
        locked_count = len(store.rows(
            "SELECT 1 FROM memberships m JOIN observations o ON o.id=m.observation_id "
            "WHERE o.kind=? AND m.locked=1", (args.kind,)))
        print(f"กลุ่มตอนนี้ ({args.kind}): {len(before)} กลุ่ม, "
              f"ยืนยัน/ล็อกแล้ว {locked_count} observation (จะไม่ถูกแตะ)")

        if not args.apply:
            affected = len(store.rows(
                "SELECT m.observation_id FROM memberships m JOIN observations o ON o.id=m.observation_id "
                "WHERE o.kind=? AND m.locked=0 AND m.profile_id IS NOT NULL" +
                (" AND o.media_id=?" if args.media_id else ""),
                (args.kind, args.media_id) if args.media_id else (args.kind,)))
            print(f"[dry-run] จะล้างการจัดกลุ่มของ {affected} observation ที่ยังไม่ล็อก แล้วจัดใหม่ด้วย "
                  f"threshold={args.threshold} margin={args.margin}")
            print("เพิ่ม --apply เพื่อให้ทำจริง")
            return

        reset = reset_unlocked(store, args.kind, args.media_id)
        print(f"ล้างการจัดกลุ่มเดิมของ {reset} observation แล้ว")

        if args.kind == "voice":
            distance_fn = cosine_distances
        else:
            from src.vision.character_embedding import CharacterEncoder
            distance_fn = CharacterEncoder().distances

        with store.lock:
            cluster_observations(store, args.kind, distance_fn, args.threshold, margin=args.margin)

        after = store.profiles(args.kind)
        print(f"จัดกลุ่มใหม่เสร็จ: {len(before)} → {len(after)} กลุ่ม")
        for profile in sorted(after, key=lambda p: -p["count"])[:15]:
            print(f"  {profile['name']:<16} {profile['count']:>3} ช่วง"
                  + (" · ยืนยันแล้ว" if profile["confirmed"] else ""))


if __name__ == "__main__":
    main()
