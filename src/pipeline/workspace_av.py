"""เพิ่มหลักฐานปากตามเวลาให้ track เดิม โดยไม่รัน YOLO/embedding หรือแก้กลุ่ม.

อ่านทีละหน้าต่าง 8 วินาทีที่ 8 fps และทำงานเฉพาะ track ที่ทับช่วงเสียงพูด.
ใช้กรอบเดิม interpolate ระหว่างตัวอย่างใกล้กัน; ไม่ลากกรอบข้ามฉาก/ช่วงหาย.
ผลเป็นหลักฐานสำหรับคนตรวจ ไม่ยืนยันคู่เสียง-ตัวละครโดยอัตโนมัติ.
"""
from bisect import bisect_left
import json

from src.core.control import check_cancel
from src.core.models import FaceTrack, TrackObservation
from src.pipeline.workspace_scan import ScanSettings, iter_video_windows
from src.vision.active_speaker import mouth_motion_series
from src.workspace.store import fingerprint, cache_key

VERSION = 2


def interpolated_box(boxes, timestamp):
    times = [item["time_ms"] for item in boxes]
    index = bisect_left(times, timestamp)
    if index < len(boxes) and times[index] == timestamp:
        return tuple(boxes[index]["box"])
    if not 0 < index < len(boxes):
        return None
    a, b = boxes[index - 1], boxes[index]
    gap = b["time_ms"] - a["time_ms"]
    if not 0 < gap <= 550:
        return None
    ratio = (timestamp - a["time_ms"]) / gap
    return tuple(round(x + (y - x) * ratio) for x, y in zip(a["box"], b["box"]))


def analyze_av(store, media_id, *, cancel=None, progress=None):
    """เติม mouth_activity ใน evidence; resume ข้าม track ที่มี cache key ตรงกัน.

    membership/name/manual labels/links ไม่ถูกแก้ และสีไม่ใช้ในการวิเคราะห์.
    เมื่อหยุด มีเพียงหน้าต่างที่จบแล้วถูก commit; track ที่ค้างคำนวณใหม่ได้.
    """
    voices = store.observations(media_id=media_id, kind="voice")
    visuals = store.observations(media_id=media_id, kind="visual")
    if not voices or not visuals:
        if progress:
            progress(1, 1, "ต้องมีทั้งช่วงเสียงพูดและภาพตัวละครก่อนวิเคราะห์คู่")
        return 0
    source = store.media_path(media_id)
    digest = store.rows("SELECT digest FROM media WHERE id=?", (media_id,))[0]["digest"]
    if fingerprint(source, cancel) != digest:
        raise ValueError("วิดีโอเปลี่ยนไปจากตอนสแกนเดิม กรุณานำเข้าเป็นตอนใหม่")
    runs = {row["key"]: json.loads(row["settings"]) for row in store.rows("SELECT key,settings FROM runs WHERE kind='visual'")}
    windows = {}
    for visual in visuals:
        check_cancel(cancel)
        boxes = sorted(visual["evidence"].get("boxes", []), key=lambda item: item["time_ms"])
        key = cache_key("av-motion", VERSION, digest, boxes, runs.get(visual["run_key"], {}).get("width", 640))
        if visual["evidence"].get("mouth_activity", {}).get("key") == key:
            continue
        if not boxes or not any(v["start_ms"] < visual["end_ms"] and v["end_ms"] > visual["start_ms"] for v in voices):
            continue  # ไม่มีเสียง ไม่ทำ dense mouth pass และไม่ตั้งชื่อจากการอยู่บนจอ
        settings = runs.get(visual["run_key"], {})
        width, span = settings.get("width", 640), settings.get("window_ms", 8000)
        start = visual["evidence"].get("window_start_ms", visual["start_ms"] // span * span)
        windows.setdefault((width, span, start), []).append((visual, boxes, key))
    # แยก decode ตามขนาด/หน้าต่างจากรอบเดิม (ปกติทุก track มีค่าเดียวกัน).
    done, total = 0, len(windows)
    for width, span in sorted({(w, s) for w, s, _ in windows}):
        targets = {start: entries for (w, s, start), entries in windows.items() if (w, s) == (width, span)}
        settings = ScanSettings(sample_fps=8, max_width=width, window_ms=span, device="cpu")
        iterator = iter_video_windows(source, settings, start_ms=min(targets), cancel=cancel)
        try:
            for start, end, samples, _ in iterator:
                check_cancel(cancel)
                if start > max(targets):
                    break
                if start not in targets:
                    continue
                updates = []
                for visual, boxes, key in targets[start]:
                    check_cancel(cancel)
                    track = FaceTrack(0, [])
                    for index, sample in enumerate(samples):
                        box = interpolated_box(boxes, sample.timestamp_ms)
                        if box is not None:
                            track.observations.append(TrackObservation(index, box))
                    evidence = dict(visual["evidence"])
                    evidence["mouth_activity"] = {"version": VERSION, "key": key, "fps": 8,
                        "pairs": mouth_motion_series(samples, track, localized=True),
                        "note": "Mouth motion at speech times; heuristic, not calibrated lip-sync probability"}
                    updates.append((json.dumps(evidence, ensure_ascii=False, allow_nan=False), visual["id"]))
                with store.db:
                    store.db.executemany("UPDATE observations SET evidence=? WHERE id=?", updates)
                done += 1
                if progress:
                    progress(done, total, f"ตรวจปากกับช่วงเสียง {done}/{total} · รักษากลุ่ม/ชื่อเดิม")
        finally:
            iterator.close()
    if progress and not total:
        progress(1, 1, "หลักฐานปากตามเวลามีใน cache แล้ว")
    return done
