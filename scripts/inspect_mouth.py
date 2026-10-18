"""Local diagnostic contact sheet and motion statistics, never changes a workspace."""
import argparse
import json
from pathlib import Path
import sqlite3
import cv2
import numpy as np
from src.pipeline.workspace_av import interpolated_box
from src.vision.active_speaker import _face_gray


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace")
    parser.add_argument("output")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(exist_ok=False, parents=True)
    database = (Path(args.workspace) / "workspace.sqlite3").resolve()
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT m.path,o.start_ms,o.end_ms,o.evidence,r.settings FROM observations o JOIN media m ON m.id=o.media_id JOIN runs r ON r.key=o.run_key WHERE o.kind='visual' ORDER BY start_ms").fetchall()
    for filename, start, end, evidence, settings in rows:
        if not 4000 <= start < 22000:
            continue
        boxes, width = json.loads(evidence)["boxes"], json.loads(settings)["width"]
        capture = cv2.VideoCapture(filename)
        previous, crops, stats = None, [], []
        for point in range(start, min(end, start + 2000), 125):
            box = interpolated_box(boxes, point)
            if box is None:
                continue
            capture.set(cv2.CAP_PROP_POS_MSEC, point)
            ok, frame = capture.read()
            if not ok:
                continue
            if frame.shape[1] > width:
                frame = cv2.resize(frame, (width, round(frame.shape[0] * width / frame.shape[1])))
            face = _face_gray(frame, box)
            if face is None:
                continue
            if len(crops) < 8:
                x, y, w, h = box
                crops.append(cv2.resize(frame[y:y+h, x:x+w], (128, 128)))
            if previous is not None:
                shift, response = cv2.phaseCorrelate(previous[:32], face[:32])
                if response > .2 and abs(shift[0]) <= 4 and abs(shift[1]) <= 4:
                    face = cv2.warpAffine(face, np.float32([[1,0,-shift[0]],[0,1,-shift[1]]]),(64,64),borderMode=cv2.BORDER_REPLICATE)
                delta = face - previous
                delta -= np.median(delta)
                delta = np.abs(delta)
                mouth, control = delta[36:56,16:48].ravel(), delta[4:30,8:56].ravel()
                stats.append([point, float(mouth.mean()), float(control.mean()),
                              float(np.sort(mouth)[-max(1,len(mouth)//5):].mean()),
                              float(np.sort(control)[-max(1,len(control)//5):].mean())])
            previous = face
        capture.release()
        if crops:
            cv2.imwrite(str(output / f"face-{start}.png"), np.hstack(crops))
        print(start, json.dumps(stats))


if __name__ == "__main__":
    main()
