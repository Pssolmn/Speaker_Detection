# Anime face weights

ไฟล์ที่ GUI/CLI ใช้เป็นค่าเริ่มต้น: `face_detect_v1.4_n/model.pt`

- แหล่ง: [deepghs/anime_face_detection](https://huggingface.co/deepghs/anime_face_detection/tree/main/face_detect_v1.4_n)
- class ที่ใช้: `face`; confidence threshold เริ่มต้น 0.278
- SHA-256 ของไฟล์ในเครื่องตอนตรวจ:
  `326e1f5aa6f922f889b90a47a9011122cc83b61a2275271276f69605e2b36d1a`
- weight ถูก gitignore; ไม่มีการดาวน์โหลดหรือฝึกโมเดลอัตโนมัติเมื่อเปิดโปรแกรม
- เลือกไฟล์อื่นได้ที่ช่อง Anime weights ใน GUI หรือ `--model` ใน CLI
- ใช้โมเดลที่ฝึกตรวจใบหน้าอนิเมะและมี class `face`; YOLO COCO ทั่วไปไม่ตรงกับ ROI ที่ใช้

ดาวน์โหลดใหม่เมื่อย้ายเครื่อง: เปิดแหล่งข้างต้น เลือกไฟล์ model.pt แล้วเก็บตามตำแหน่งนี้
ไม่ต้อง rebuild ฐานตัวละครเพียงเพราะเปลี่ยน detector; ถ้าเปลี่ยนสูตร feature จึงต้องประเมิน/rebuild ให้ตรงกัน

## โมเดลสำหรับ Project Workspace (15 ตุลาคม 2026)

ติดตั้งในเครื่องแล้วโดยสคริปต์ `venv/bin/python -m scripts.setup_workspace_models`
ตรวจ SHA256 แบบไม่ใช้เครือข่ายด้วย `venv/bin/python -m scripts.setup_workspace_models --verify-only`
รายการไฟล์/ต้นทาง/hash ที่ติดตั้งจริงอยู่ใน `workspace-models.json`; weights ไม่เก็บใน Git

| ส่วน | โมเดล/ต้นทาง | ไฟล์ local |
|---|---|---|
| ลักษณะตัวละคร | [CCIP ONNX](https://huggingface.co/deepghs/ccip_onnx), variant ccip-caformer-6-randaug-pruned_fp32 | ccip/model_feat.onnx, model_metrics.onnx, metrics.json |
| แบ่งช่วงผู้พูด | [sherpa-onnx segmentation exports](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models), pyannote segmentation 3.0 | speaker/segmentation.onnx |
| ลักษณะเสียง | [sherpa-onnx speaker embeddings](https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models), wespeaker_en_voxceleb_resnet34 | speaker/embedding.onnx |
| สกัด Vocal | [audio-separator / UVR registry](https://github.com/nomadkaraoke/python-audio-separator), Kim_Vocal_2.onnx | vocals/Kim_Vocal_2.onnx + download_checks/mdx_model_data/vr_model_data JSON |

CCIP preprocessing/metric อ้างอิง [deepghs/imgutils](https://github.com/deepghs/imgutils/blob/main/imgutils/metrics/ccip.py)
ใช้ learned distance คู่กับ encoder ไม่แทนด้วย cosine โดยพลการ
CCIP ที่ติดตั้งอ้าง revision `eb2acdd29af1703388d3d0c04221add322bc9110`; setup รักษา URL ของไฟล์เดิม ไม่เปลี่ยน provenance ทั้งที่ไม่ได้ดาวน์โหลดใหม่

ตัว runtime และน้ำหนักโมเดลมีเงื่อนไขแยกกัน ดู [sherpa-onnx LICENSE](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE),
[pyannote model card](https://huggingface.co/pyannote/segmentation-3.0), CCIP และ UVR ต้นทางก่อนแจก weights/ใช้เชิงพาณิชย์
การดาวน์โหลดสำเร็จหรือ license ของ wrapper ไม่ใช่การรับรองสิทธิ์ของทุกโมเดล/ข้อมูลฝึก
ไม่ได้ใช้ Hugging Face token หรือยอมรับเงื่อนไขบัญชีแทนผู้ใช้; ใช้ public export ของผู้เผยแพร่ตาม URL ใน manifest
