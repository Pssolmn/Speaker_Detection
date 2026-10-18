"""ใช้หลักฐานปากขยับ (จากคู่เสียง-ภาพที่ยืนยันแล้ว) ช่วยแก้เสียงที่คล้ายกันมากจนถูกจัดกลุ่มผิด.

การจัดกลุ่มเสียงปกติ (cluster_observations) เทียบแค่ "เสียงคล้ายเสียง" อย่างเดียว จึงพลาดได้เวลา
สองตัวละครเสียงสูง/โทนใกล้กันมาก สคริปต์นี้ใช้หลักฐานอีกชนิด: ถ้าช่วงเสียงหนึ่งมีภาพปากขยับตรงกับ
กลุ่มภาพที่ "ยืนยันแล้วและเชื่อมกับกลุ่มเสียงอื่น" อย่างชัดเจน ก็น่าจะเป็นเสียงของคนนั้นจริง ไม่ใช่กลุ่มเดิม

อ่าน evidence ที่คำนวณไว้แล้วในฐานข้อมูลเท่านั้น ไม่รันโมเดล ไม่อ่านวิดีโอ/เสียงซ้ำ — เร็วมาก
แม่นขึ้นถ้าเคยรัน "ตรวจคู่ภาพ-เสียง" ในแอปมาก่อน (มี mouth_activity ละเอียด); ถ้ายังไม่เคยรันจะใช้
motion หยาบแทนได้ แต่ความมั่นใจต่ำกว่า (คะแนนตัดที่ 0.4 กรองความมั่นใจต่ำแบบนี้ออกไปแล้วโดยปริยาย)

ไม่แตะช่วงที่ล็อก/ยืนยันแล้ว; ย้ายเฉพาะช่วงที่ยังไม่ยืนยันและหลักฐานปากขยับชี้ไปคนละกลุ่มชัดเจน

เงื่อนไขก่อนใช้: ต้องมีคู่เสียง-ภาพที่ยืนยันแล้วอย่างน้อย 1 คู่ (Dashboard → ยืนยันคู่เสียง-ภาพ)
ไม่งั้นไม่มี "ความจริง" ให้เทียบเลย

ตัวอย่าง:
  venv/bin/python -m scripts.voice_av_correction data/output/oshi-no-ko-s3e02
  venv/bin/python -m scripts.voice_av_correction data/output/oshi-no-ko-s3e02 --apply
"""

import argparse
from collections import defaultdict
from pathlib import Path

from src.workspace.attribution import _overlap, _speech_motion
from src.workspace.store import WorkspaceStore

DEFAULT_MIN_SCORE = 0.4   # ต่ำกว่านี้ไม่น่าเชื่อถือพอจะย้าย (คะแนน legacy แบบหยาบอยู่ที่ 0.25 จึงถูกกรองออกเอง)
DEFAULT_MIN_MARGIN = 0.1  # ต้องชนะคู่แข่ง (กลุ่มภาพอื่นที่ทับเวลาเดียวกัน) ขาดลอยพอจะเชื่อได้


def find_corrections(store, min_score=DEFAULT_MIN_SCORE, min_margin=DEFAULT_MIN_MARGIN):
    links = store.rows("SELECT * FROM links")
    confirmed_visual = {p["id"] for p in store.profiles("visual") if p["confirmed"]}
    voice_profiles = {p["id"]: p for p in store.profiles("voice")}
    # เชื่อถือเฉพาะคู่ที่ภาพฝั่งนั้นยืนยันแล้ว ไม่งั้นเอาข้อเสนอที่ยังไม่ตรวจมาแก้เสียงอื่นจะยิ่งพาไปผิดทาง
    trusted = {row["voice_id"]: row["visual_id"] for row in links if row["visual_id"] in confirmed_visual}

    by_media_visual = defaultdict(list)
    for item in store.observations(kind="visual"):
        if item["profile_id"] in confirmed_visual:
            by_media_visual[item["media_id"]].append(item)

    corrections = []
    for voice in store.observations(kind="voice"):
        if voice["locked"]:
            continue
        candidates = {}
        for visual in by_media_visual.get(voice["media_id"], []):
            if _overlap(voice, visual) < min(350, (voice["end_ms"] - voice["start_ms"]) * .4):
                continue
            measurement = _speech_motion(voice, visual)
            if measurement and measurement["score"] > candidates.get(visual["profile_id"], 0):
                candidates[visual["profile_id"]] = measurement["score"]
        if not candidates:
            continue
        ranked = sorted(candidates.items(), key=lambda pair: -pair[1])
        best_visual_id, best_score = ranked[0]
        margin = best_score - (ranked[1][1] if len(ranked) > 1 else 0)
        if best_score < min_score or margin < min_margin:
            continue
        suggested_voice_id = next((voice_id for voice_id, visual_id in trusted.items()
                                   if visual_id == best_visual_id), None)
        if not suggested_voice_id or suggested_voice_id == voice["profile_id"]:
            continue
        corrections.append((voice, suggested_voice_id, best_score))
    return corrections, voice_profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--apply", action="store_true", help="ไม่ใส่ = dry-run แสดงผลกระทบอย่างเดียว ไม่เขียนอะไร")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE,
                        help=f"ต่ำกว่านี้ไม่ย้าย ยิ่งต่ำยิ่งจับได้เยอะแต่เสี่ยงผิดมากขึ้น (ค่าเริ่มต้น {DEFAULT_MIN_SCORE})")
    parser.add_argument("--min-margin", type=float, default=DEFAULT_MIN_MARGIN,
                        help=f"ต้องชนะคู่แข่งอย่างน้อยเท่านี้ (ค่าเริ่มต้น {DEFAULT_MIN_MARGIN})")
    args = parser.parse_args()

    with WorkspaceStore(args.workspace) as store:
        if not store.rows("SELECT 1 FROM links LIMIT 1"):
            print("ยังไม่มีคู่เสียง-ภาพที่ยืนยันเลย ต้องไปยืนยันคู่ใน Dashboard ก่อนอย่างน้อย 1 คู่")
            return
        corrections, voice_profiles = find_corrections(store, args.min_score, args.min_margin)

        if not corrections:
            print("ไม่พบช่วงเสียงที่หลักฐานปากขยับชี้ไปคนละกลุ่มชัดเจน (หรือถูกจัดกลุ่มถูกอยู่แล้วทั้งหมด)")
            return

        print(f"พบ {len(corrections)} ช่วงเสียงที่หลักฐานปากขยับชี้ไปคนละกลุ่มกับปัจจุบัน:")
        for voice, suggested, score in corrections[:20]:
            current_name = voice_profiles[voice["profile_id"]]["name"] if voice["profile_id"] else "(ยังไม่จัดกลุ่ม)"
            print(f"  {voice['start_ms']/1000:7.1f}s  {current_name:<16} -> {voice_profiles[suggested]['name']:<16} "
                  f"(คะแนน {score:.2f})")
        if len(corrections) > 20:
            print(f"  ... อีก {len(corrections) - 20} ช่วง")

        if not args.apply:
            print("\n[dry-run] เพิ่ม --apply เพื่อย้ายจริง")
            return

        by_target = defaultdict(list)
        for voice, suggested, _ in corrections:
            by_target[suggested].append(voice["id"])
        for target, ids in by_target.items():
            store.move(ids, target)
        print(f"\nย้ายแล้ว {len(corrections)} ช่วง (ล็อกไว้เหมือนย้ายด้วยมือ)")


if __name__ == "__main__":
    main()
