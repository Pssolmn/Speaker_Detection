"""วัดผลกับคำตอบที่มนุษย์ติดป้ายเอง; ไม่สร้าง ground truth จากคำทำนายของระบบ."""

import argparse
import json
from collections import Counter
from pathlib import Path

from src.audio.vad import detect_speech_ranges, merge_ranges, speech_overlap_ratio
from src.core.models import SubtitleSegment
from src.io.result_export import _write_atomic, load_results_json


def evaluate_speakers(results, labels) -> dict:
    """รายงาน precision ของ ACCEPTED และ coverage แยกกัน ไม่ซ่อนการงดตอบ.

    labels เป็น list ของ {segment_id, speaker}; ชื่อแก้มือไม่ถูกนับเป็นคำทำนาย
    """
    lookup = {result.segment_id: result for result in results}
    seen, accepted, correct, statuses = set(), 0, 0, Counter()
    mismatches = []
    for label in labels:
        segment_id, expected = label["segment_id"], label["speaker"]
        if segment_id in seen or segment_id not in lookup:
            raise ValueError("Ground truth IDs must be unique and present in predictions")
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError("Each ground truth speaker must be labelled by a human")
        seen.add(segment_id)
        result = lookup[segment_id]
        statuses[result.status] += 1
        if result.status == "ACCEPTED":
            accepted += 1
            match = result.detected_character.strip().casefold() == expected.strip().casefold()
            correct += int(match)
            if not match:
                mismatches.append({"segment_id": segment_id, "expected": expected,
                                   "predicted": result.detected_character})
    return {"labelled_segments": len(seen), "automatic_acceptances": accepted,
            "accepted_precision": correct / accepted if accepted else None,
            "acceptance_coverage": accepted / len(seen) if seen else None,
            "statuses": dict(statuses), "wrong_acceptances": mismatches}


def evaluate_audio_ranges(ranges, labels) -> dict:
    """วัด false positive/negative เป็นระยะเวลา ms บนช่วง speech/music/noise/silence ที่ติดป้าย.

    ไม่ประเมินช่วงว่างที่ไม่มี label และห้าม label ซ้อนกันเพื่อไม่ให้นับซ้ำ
    """
    ranges = merge_ranges(ranges)
    totals = {"true_positive_ms": 0, "false_negative_ms": 0,
              "false_positive_ms": 0, "true_negative_ms": 0}
    previous_end = -1
    for index, label in enumerate(sorted(labels, key=lambda item: item["start_ms"])):
        segment = SubtitleSegment(index, label["start_ms"], label["end_ms"], "")
        if segment.start_ms < previous_end:
            raise ValueError("Audio ground truth intervals must not overlap")
        previous_end = segment.end_ms
        if label["kind"] not in {"speech", "music", "noise", "silence"}:
            raise ValueError("Unknown audio label kind")
        duration = segment.end_ms - segment.start_ms
        detected = round(speech_overlap_ratio(segment, ranges) * duration)
        if label["kind"] == "speech":
            totals["true_positive_ms"] += detected
            totals["false_negative_ms"] += duration - detected
        else:
            totals["false_positive_ms"] += detected
            totals["true_negative_ms"] += duration - detected
    speech = totals["true_positive_ms"] + totals["false_negative_ms"]
    other = totals["false_positive_ms"] + totals["true_negative_ms"]
    return {**totals, "false_negative_rate": totals["false_negative_ms"] / speech if speech else None,
            "false_positive_rate": totals["false_positive_ms"] / other if other else None,
            "method": "rms_energy (not speech-specific)"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--wav", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        labels = json.loads(args.labels.read_text(encoding="utf-8"))
        report = {}
        if args.predictions:
            _, results = load_results_json(args.predictions)
            report["speakers"] = evaluate_speakers(results, labels["speakers"])
        if args.wav:
            report["audio"] = evaluate_audio_ranges(detect_speech_ranges(args.wav), labels["audio_intervals"])
        if not report:
            raise ValueError("Provide --predictions and/or --wav")
        text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            if args.output.resolve() in {p.resolve() for p in (args.labels, args.predictions, args.wav) if p is not None}:
                raise ValueError("Evaluation output must not overwrite an input")
            _write_atomic(args.output, text + "\n")
        print(text)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
