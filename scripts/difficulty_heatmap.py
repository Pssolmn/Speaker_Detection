"""Heatmap วินิจฉัย: จุดที่ระบบตรวจยาก (สถานะ/คะแนนก้ำกึ่ง) เทียบกับเวลาประมวลผลภาพจริง.

อ่านผลตรวจที่มีอยู่แล้วแบบ read-only (ไม่เขียนทับ ไม่ auto_assign ไม่ checkpoint) แล้ว
วัดเวลา detect_faces จริงต่อหน้าต่างวิดีโอเพื่อดูว่า "ช่วงที่ยาก" กับ "ช่วงที่ช้า" เป็นจุดเดียวกันหรือไม่
(โมเดลที่ใช้เป็น fixed-cost forward pass จึงมักไม่สัมพันธ์กันโดยตรง — สคริปต์นี้พิสูจน์/หักล้างข้อสมมติฐานนั้นด้วยข้อมูลจริง)

เรียก: venv/bin/python -m scripts.difficulty_heatmap data/output/workspace-demo
       venv/bin/python -m scripts.difficulty_heatmap data/output/workspace-demo --media-id <id> --out out.png
"""

import argparse
import csv
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

matplotlib.rcParams["font.family"] = "Sarabun"  # DejaVu Sans เริ่มต้นไม่มีสระ/วรรณยุกต์ไทย

from src.pipeline.workspace_scan import ScanSettings, iter_video_windows
from src.vision.face_detect import DEFAULT_FACE_MODEL_PATH, detect_faces
from src.workspace.attribution import subtitle_results
from src.workspace.store import WorkspaceStore

STATUS_SEVERITY = {
    "MANUAL": 0.0,
    "PROPOSED": 0.2,
    "AMBIGUOUS": 0.7,
    "UNKNOWN": 0.8,
    "MULTIPLE_SPEAKERS": 1.0,
}


def pairing_volatility(av_candidates):
    """ยิ่งคะแนนผู้สมัครจับคู่อันดับ 1-2 ใกล้กัน ยิ่งก้ำกึ่ง/แกว่ง; มีผู้สมัครเดียวหรือไม่มีถือว่านิ่ง"""
    scores = sorted((candidate["score"] for group in av_candidates.values() for candidate in group), reverse=True)
    if len(scores) < 2:
        return 0.0
    margin = scores[0] - scores[1]
    return float(np.clip(1 - margin / 0.3, 0, 1))


def difficulty_score(result):
    base = STATUS_SEVERITY.get(result.status, 0.5)
    volatility = pairing_volatility(result.evidence.get("av_candidates", {}))
    return min(1.0, 0.7 * base + 0.3 * volatility)


def benchmark_visual_timing(video_path, settings, cancel=None):
    """รัน detect_faces จริงต่อหน้าต่าง จับเวลาแต่ละหน้าต่าง ไม่เขียนผลลง store ใด ๆ"""
    timings = []
    for start, end, samples, _ in iter_video_windows(video_path, settings, cancel=cancel):
        began = time.perf_counter()
        for sample in samples:
            detect_faces(sample.frame, model_path=DEFAULT_FACE_MODEL_PATH, device=settings.device)
        timings.append((start, end, time.perf_counter() - began))
    return timings


def overlapping_duration(start_ms, end_ms, timings):
    hits = [seconds for w_start, w_end, seconds in timings if w_start < end_ms and w_end > start_ms]
    return float(np.mean(hits)) if hits else 0.0


def build_rows(store, media_id, timings):
    segments, results = subtitle_results(store, media_id)
    results_by_id = {result.segment_id: result for result in results}
    rows = []
    for segment in segments:
        result = results_by_id[segment.id]
        rows.append({
            "id": segment.id, "start_ms": segment.start_ms, "end_ms": segment.end_ms,
            "text": segment.text.replace("\n", " ")[:40], "status": result.status,
            "difficulty": difficulty_score(result),
            "seconds_per_window": overlapping_duration(segment.start_ms, segment.end_ms, timings),
        })
    return rows


def plot_heatmap(rows, title, out_path):
    fig, ax = plt.subplots(figsize=(12, 2.6))
    cmap_difficulty, cmap_timing = plt.get_cmap("YlOrRd"), plt.get_cmap("Blues")
    max_seconds = max((row["seconds_per_window"] for row in rows), default=0) or 1.0
    for row in rows:
        start_s, duration_s = row["start_ms"] / 1000, max((row["end_ms"] - row["start_ms"]) / 1000, 0.05)
        ax.broken_barh([(start_s, duration_s)], (1, 0.8), facecolors=cmap_difficulty(row["difficulty"]))
        ax.broken_barh([(start_s, duration_s)], (0, 0.8),
                       facecolors=cmap_timing(row["seconds_per_window"] / max_seconds))
    ax.set_yticks([0.4, 1.4])
    ax.set_yticklabels(["เวลาประมวลผล/หน้าต่าง", "ความยาก (สถานะ+ความก้ำกึ่ง)"])
    ax.set_xlabel("เวลาในตอน (วินาที)")
    ax.set_title(title)
    ax.set_xlim(0, max((row["end_ms"] for row in rows), default=1000) / 1000 + 1)
    fig.colorbar(plt.cm.ScalarMappable(cmap=cmap_difficulty, norm=plt.Normalize(0, 1)),
                ax=ax, pad=0.01, fraction=0.025, label="ความยาก 0-1")
    fig.colorbar(plt.cm.ScalarMappable(cmap=cmap_timing, norm=plt.Normalize(0, max_seconds)),
                ax=ax, pad=0.08, fraction=0.025, label="วินาที/หน้าต่าง")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def report_correlation(rows):
    difficulty = np.array([row["difficulty"] for row in rows])
    timing = np.array([row["seconds_per_window"] for row in rows])
    if len(rows) < 2 or np.std(difficulty) == 0 or np.std(timing) == 0:
        print("ข้อมูลไม่พอ/ไม่มีความแปรปรวนสำหรับคำนวณสหสัมพันธ์")
        return
    correlation = float(np.corrcoef(difficulty, timing)[0, 1])
    print(f"สหสัมพันธ์ (Pearson r) ระหว่างความยากกับเวลาประมวลผล = {correlation:.3f}")
    print("หมายเหตุ: ใกล้ 0 แปลว่าเวลาประมวลผลไม่ใช่ตัวบ่งชี้ความยากที่ดี (คาดได้ เพราะโมเดลเป็น fixed-cost forward pass)")


def write_csv(rows, out_path):
    with open(out_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "start_ms", "end_ms", "text", "status",
                                                      "difficulty", "seconds_per_window"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--media-id", default=None, help="ค่าเริ่มต้นใช้วิดีโอแรกในโปรเจกต์")
    parser.add_argument("--device", default="cpu", help="cpu เพื่อให้เวลาวัดซ้ำได้เสถียร ไม่ปนสัญญาณจาก GPU scheduling")
    parser.add_argument("--out", type=Path, default=Path("difficulty_heatmap.png"))
    parser.add_argument("--csv", type=Path, default=Path("difficulty_heatmap.csv"))
    args = parser.parse_args()

    with WorkspaceStore(args.workspace) as store:
        media_id = args.media_id or store.media()[0]["id"]
        video_path = store.media_path(media_id)

        settings = ScanSettings(device=args.device)
        print(f"กำลังวัดเวลา detect_faces จริงต่อหน้าต่างจาก {video_path.name} (device={args.device}) ...")
        timings = benchmark_visual_timing(video_path, settings)

        rows = build_rows(store, media_id, timings)

    rows.sort(key=lambda row: row["start_ms"])
    hardest = sorted(rows, key=lambda row: -row["difficulty"])[:5]
    slowest = sorted(rows, key=lambda row: -row["seconds_per_window"])[:5]

    print(f"\nบรรทัดที่ยากที่สุด (status + ความก้ำกึ่ง):")
    for row in hardest:
        print(f"  #{row['id']:>3} {row['start_ms']/1000:6.1f}s  difficulty={row['difficulty']:.2f}  "
              f"status={row['status']:<16} \"{row['text']}\"")

    print(f"\nบรรทัดที่ประมวลผลภาพช้าที่สุด:")
    for row in slowest:
        print(f"  #{row['id']:>3} {row['start_ms']/1000:6.1f}s  {row['seconds_per_window']:.3f}s/window  "
              f"\"{row['text']}\"")

    print()
    report_correlation(rows)

    plot_heatmap(rows, f"Heatmap: จุดที่ระบบมีปัญหา vs. เวลาประมวลผลภาพ — {video_path.name}", args.out)
    write_csv(rows, args.csv)
    print(f"\nบันทึกภาพ: {args.out}")
    print(f"บันทึกตาราง: {args.csv}")


if __name__ == "__main__":
    main()
