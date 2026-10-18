"""CLI สำหรับ Workspace เดียวกับ GUI; ย้ายงานหนักไปเครื่องอื่นได้โดยไม่เปลี่ยน schema."""

import argparse
import json
import signal
from threading import Event

from src.core.control import AnalysisCancelled

from src.io.result_export import export_results_json, export_labelled_srt
from src.io.subtitle_io import parse_srt
from src.pipeline.workspace_scan import ScanSettings, scan_visual
from src.workspace.attribution import subtitle_results
from src.workspace.store import WorkspaceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--video")
    parser.add_argument("--media-id")
    parser.add_argument("--subtitles")
    parser.add_argument("--import-review", help="Import subtitle/manual decisions from an exported JSON")
    parser.add_argument("--scan", choices=["visual", "voice", "all", "av"])
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "mps", "cuda"])
    parser.add_argument("--fps", type=float, default=4)
    parser.add_argument("--no-separation", action="store_true", help="Analyze original audio instead of separating vocals")
    parser.add_argument("--export", help="New output filename ending .json or .srt (never overwrites)")
    args = parser.parse_args()
    cancelled = Event()
    signal.signal(signal.SIGINT, lambda *unused: cancelled.set())
    with WorkspaceStore(args.workspace, create=args.create) as store:
        with store.lock:
            media_id = store.add_media(args.video, cancelled.is_set) if args.video else args.media_id
            if args.subtitles:
                if not media_id:
                    parser.error("--subtitles requires --video or --media-id")
                store.import_subtitles(media_id, parse_srt(args.subtitles))
            if args.import_review:
                if not media_id:
                    parser.error("--import-review requires --video or --media-id")
                store.import_review(media_id, args.import_review)
            def progress(done, total, message):
                print(f"{done}/{total} {message}", flush=True)
            if args.scan:
                if not media_id:
                    parser.error("--scan requires --video or --media-id")
                if args.scan in {"voice", "all"}:
                    from src.pipeline.workspace_audio import scan_audio
                    scan_audio(store, media_id, separate=not args.no_separation, device=args.device,
                               cancel=cancelled.is_set, progress=progress)
                if args.scan in {"visual", "all"}:
                    scan_visual(store, media_id, settings=ScanSettings(sample_fps=args.fps, device=args.device),
                                cancel=cancelled.is_set, progress=progress)
                from src.pipeline.workspace_av import analyze_av
                analyze_av(store, media_id, cancel=cancelled.is_set, progress=progress)
            if args.export:
                if not media_id:
                    parser.error("--export requires --video or --media-id")
                from pathlib import Path
                target = Path(args.export)
                if target.exists():
                    raise FileExistsError("Export refuses to overwrite an existing file")
                if target.suffix.lower() not in {".json", ".srt"}:
                    parser.error("--export must end in .json or .srt")
                segments, results = subtitle_results(store, media_id)
                exporter = export_results_json if target.suffix.lower() == ".json" else export_labelled_srt
                exporter(segments, results, target)
            print(json.dumps({"media": store.media(), "profiles": store.profiles()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except AnalysisCancelled:
        print("Stopped safely; completed checkpoints and manual reviews were preserved.")
        raise SystemExit(130)
