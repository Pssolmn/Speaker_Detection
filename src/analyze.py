"""CLI วิเคราะห์และ export โดยใช้ pipeline เดียวกับ GUI.

ตัวอย่าง: python -m src.analyze --video movie.mp4 --subtitles dialogue.srt --output-dir results
ใช้ --limit 1 เพื่อลองช่วงสั้นก่อน; Ctrl+C จะบันทึกผลที่เสร็จแล้ว
"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2

from src.core import config
from src.io.result_export import export_labelled_srt, export_results_json, load_results_json
from src.io.subtitle_io import parse_srt
from src.pipeline.video_analysis import analyze_segments, prepare_audio
from src.pipeline.visual_identification import VisualIdentifier
from src.vision.face_detect import DEFAULT_FACE_MODEL_PATH


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True, help="SRT or exported analysis JSON")
    parser.add_argument("--database", type=Path, default=config.DATABASE_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_FACE_MODEL_PATH)
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    parser.add_argument("--limit", type=int, help="Analyze only the first N segments")
    parser.add_argument("--no-audio", action="store_true", help="Leave audio/motion evidence unknown")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing analysis.json / labelled.srt")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    results = {}
    cancelled = False
    try:
        if not args.overwrite and any((args.output_dir / name).exists() for name in ("analysis.json", "labelled.srt")):
            raise ValueError("Output already exists; choose a new --output-dir or use --overwrite")
        if not args.video.is_file() or not args.model.is_file():
            raise FileNotFoundError("Video or anime-face weights file does not exist")
        if args.subtitles.suffix.lower() == ".json":
            segments, previous = load_results_json(args.subtitles)
            results = {result.segment_id: result for result in previous}
        else:
            segments = parse_srt(args.subtitles)
        if not segments or len({segment.id for segment in segments}) != len(segments):
            raise ValueError("Need nonempty subtitles with unique IDs")
        identifier = VisualIdentifier.from_database(args.database)
        cv2.setNumThreads(config.CV_THREADS)

        def receive(result):
            if result.segment_id in results:
                result.manual_character = results[result.segment_id].manual_character
            results[result.segment_id] = result
            print(f"{result.segment_id}: {result.status} · {result.detected_character} · score={result.confidence:.3f}", flush=True)

        with TemporaryDirectory(prefix="speaker-detection-cli-") as directory:
            try:
                audio = None if args.no_audio else prepare_audio(args.video, Path(directory) / "audio.wav", cancel=lambda: False)
                if audio and audio.get("warning"):
                    print(audio["warning"], flush=True)
                analyze_segments(args.video, segments[:args.limit], identifier, audio,
                                 model_path=args.model, on_result=receive)
            except KeyboardInterrupt:
                cancelled = True
                print("Interrupted; exporting completed results only (remaining rows: UNPROCESSED).", flush=True)
        json_path = export_results_json(segments, results.values(), args.output_dir / "analysis.json", source_path=args.subtitles)
        srt_path = export_labelled_srt(segments, results.values(), args.output_dir / "labelled.srt", source_path=args.subtitles)
        print(f"Saved {json_path}\nSaved {srt_path}")
        return 130 if cancelled else (1 if any(result.status == "ERROR" for result in results.values()) else 0)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
