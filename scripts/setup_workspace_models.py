"""ดาวน์โหลดโมเดลจากผู้เผยแพร่ต้นทางแบบ explicit; ตัว GUI ไม่ดาวน์โหลดเอง.

เรียก: venv/bin/python -m scripts.setup_workspace_models
ไม่ส่งวิดีโอ/เสียงผู้ใช้ขึ้นเครือข่าย เก็บ source/revision/SHA256 เพื่อทำ cache.
"""

import argparse
import json
from pathlib import Path
import tarfile

import requests

from src.core.config import DATA_DIR
from src.workspace.store import fingerprint


def download(url, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size:
        return
    temporary = target.with_suffix(target.suffix + ".download")
    with requests.get(url, stream=True, timeout=(20, 60)) as response:
        response.raise_for_status()
        with temporary.open("wb") as stream:
            for block in response.iter_content(1024 * 1024):
                stream.write(block)
    temporary.replace(target)
    print(f"Downloaded {target.name}: {target.stat().st_size / 1e6:.1f} MB", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-vocals", action="store_true")
    parser.add_argument("--verify-only", action="store_true", help="Check local hashes without network/downloads")
    args = parser.parse_args()
    root = DATA_DIR / "models"
    manifest_path = root / "workspace-models.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.is_file() else []
    known = {item["file"]: item for item in previous}
    for record in previous:
        path = (root / record["file"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Invalid model manifest path")
        if path.is_file() and fingerprint(path) != record["sha256"]:
            raise ValueError(f"Model changed: {record['file']}; preserving local file, refusing silent replacement")
        if args.verify_only and not path.is_file():
            raise FileNotFoundError(path)
    if args.verify_only:
        if not previous:
            raise FileNotFoundError("No model manifest; run setup first")
        print(f"Verified {len(previous)} local model/metadata files; no network used")
        return
    manifest = []
    response = requests.get("https://huggingface.co/api/models/deepghs/ccip_onnx", timeout=30)
    response.raise_for_status()
    revision = response.json()["sha"]
    variant = "ccip-caformer-6-randaug-pruned_fp32"
    for name in ("model_feat.onnx", "model_metrics.onnx", "metrics.json"):
        url = f"https://huggingface.co/deepghs/ccip_onnx/resolve/{revision}/{variant}/{name}"
        target = root / "ccip" / name
        # setup รอบใหม่ต้องไม่เปลี่ยน provenance ของ weight เก่าที่ไม่ได้ดาวน์โหลดใหม่
        record = known.get(str(target.relative_to(root)))
        if record:
            url = record["url"]
        download(url, target)
        manifest.append({"file": str(target.relative_to(root)), "url": url, "sha256": fingerprint(target)})
    archive = root / "speaker" / "segmentation.tar.bz2"
    url = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/"
           "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")
    target = root / "speaker" / "segmentation.onnx"
    if not target.is_file():
        download(url, archive)
        # ไม่ extractall: อ่านเฉพาะ model.onnx ป้องกัน path traversal ใน archive
        with tarfile.open(archive) as package:
            member = next(item for item in package.getmembers() if item.name.endswith("/model.onnx") and item.isfile())
            partial = target.with_suffix(".download")
            with package.extractfile(member) as source, partial.open("wb") as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
            partial.replace(target)
    manifest.append({"file": str(target.relative_to(root)), "url": url, "sha256": fingerprint(target)})
    url = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
           "wespeaker_en_voxceleb_resnet34.onnx")
    target = root / "speaker" / "embedding.onnx"
    download(url, target)
    manifest.append({"file": str(target.relative_to(root)), "url": url, "sha256": fingerprint(target)})
    if not args.without_vocals:
        from audio_separator.separator import Separator
        separator = Separator(model_file_dir=str(root / "vocals"), output_single_stem="Vocals")
        separator.download_model_and_data("Kim_Vocal_2.onnx")
        target = root / "vocals" / "Kim_Vocal_2.onnx"
        manifest.append({"file": str(target.relative_to(root)), "source": "UVR / audio-separator model registry",
                         "sha256": fingerprint(target)})
        for name in ("download_checks.json", "mdx_model_data.json", "vr_model_data.json"):
            target = root / "vocals" / name
            manifest.append({"file": str(target.relative_to(root)), "source": "UVR / audio-separator metadata",
                             "sha256": fingerprint(target)})
    # --without-vocals ไม่ลบ provenance ของชุดเสียงที่เคยติดตั้งไว้
    files = {item["file"] for item in manifest}
    manifest.extend(item for item in previous if item["file"] not in files)
    partial = manifest_path.with_suffix(".partial.json")
    partial.write_text(json.dumps(manifest, indent=2) + "\n")
    partial.replace(manifest_path)
    print("Workspace models ready. Metadata: data/models/workspace-models.json", flush=True)


if __name__ == "__main__":
    main()
