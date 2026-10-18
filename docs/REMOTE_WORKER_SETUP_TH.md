# ใช้เครื่องที่สอง (Windows/Linux + NVIDIA) เป็น Worker คำนวณแทน Mac

ไม่มี auto-dispatch ผ่านเครือข่าย (ยังไม่สร้าง เสี่ยงเกินไปใกล้ deadline) — ใช้ `workspace_cli.py`
เป็นตัว "worker" แทน: รันบนเครื่องที่สอง, ได้ไฟล์ Workspace ที่มีผลวิเคราะห์กลับมา, เปิดต่อบน Mac ได้ปกติ

ขั้นตอน: เปิด SSH บนเครื่องที่สอง → sync โค้ด+ข้อมูลไป → รันสแกนที่นั่น → sync ผลกลับมา

## 1. เปิด SSH บนเครื่องที่สอง (ยังไม่เคยตั้ง)

**ถ้าเป็น Windows** — เปิด PowerShell แบบ **Run as Administrator** แล้วรัน:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

หา IP ของเครื่องนั้นด้วย `ipconfig` (ดูเลขใต้ Wi-Fi adapter เช่น `192.168.1.xx`)

**ถ้าเป็น Linux**: `sudo apt install openssh-server && sudo systemctl enable --now ssh` แล้วดู IP ด้วย `ip addr`

จากเครื่อง Mac ทดสอบว่าต่อได้: `ssh <username>@<IP ของเครื่องที่สอง>`

## 2. ติดตั้งโค้ดบนเครื่องที่สอง (ครั้งแรกครั้งเดียว)

บนเครื่องที่สอง (เปิด PowerShell/Terminal ธรรมดา):

```bash
git clone https://github.com/Pssolmn/Speaker_Detection.git
cd Speaker_Detection
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux

pip install -r requirements.txt --index-url https://download.pytorch.org/whl/cu124 --extra-index-url https://pypi.org/simple
pip install -r requirements-ai.txt
python -m scripts.setup_workspace_models
```

ติดตั้ง FFmpeg แยก (ไม่ใช่ pip package): Windows ใช้ `winget install ffmpeg` หรือโหลดจาก ffmpeg.org แล้วใส่ PATH; Linux ใช้ `sudo apt install ffmpeg`

anime-face YOLO weights เตรียมแยกตาม `data/models/README.md`

## 3. ส่งวิดีโอ + โมเดลไปเครื่องที่สอง (ทุกครั้งที่มีงานใหม่)

จากเครื่อง Mac (แทน `<user>@<IP>` ด้วยค่าจริง, path ปลายทางคือ path เดียวกับที่ `git clone` ไว้):

```bash
rsync -avz --progress \
  "data/input/videos/[SubsPlease] Oshi no Ko S3 - 02 (1080p) [C9DF9980].mkv" \
  <user>@<IP>:~/Speaker_Detection/data/input/videos/

rsync -avz --progress data/models/ <user>@<IP>:~/Speaker_Detection/data/models/
```

(Windows ปลายทางไม่มี `rsync` ในตัว แต่ `rsync` ฝั่ง Mac เขียนผ่าน SSH ไปยังปลายทางที่มี OpenSSH ได้ปกติ ไม่ต้องติดตั้งอะไรเพิ่มฝั่ง Windows)

## 4. สร้าง Workspace บนเครื่องที่สอง แล้วสั่งสแกน — นี่คือ "worker" ตัวจริง

บนเครื่องที่สอง:

```bash
python -m src.workspace_cli data/output/oshi-no-ko-s3e02 --create \
  --video "data/input/videos/[SubsPlease] Oshi no Ko S3 - 02 (1080p) [C9DF9980].mkv" \
  --subtitles "data/input/videos/Oshi no Ko S3 - 02 (1080p) [C9DF9980].track3.srt" \
  --scan all --device cuda
```

รันได้เป็นชั่วโมง ปิด SSH session ได้โดยใช้ `tmux`/`screen` ถ้าไม่อยากให้หลุดระหว่างทาง
(`tmux new -s scan` แล้ว detach ด้วย `Ctrl+b d`, กลับมาด้วย `tmux attach -t scan`)

## 5. ดึงผลกลับมา Mac

```bash
rsync -avz --progress <user>@<IP>:~/Speaker_Detection/data/output/oshi-no-ko-s3e02/ \
  data/output/oshi-no-ko-s3e02/
```

แล้วเปิดด้วย GUI บน Mac ตามปกติ (`venv/bin/python -m src.workspace_app data/output/oshi-no-ko-s3e02`)
ไฟล์เสียง/วิดีโอต้นฉบับยังอยู่ที่เดิมทั้งสองเครื่อง ไม่ต้องย้ายซ้ำ

## ข้อควรรู้

- **ห้ามเปิด Workspace เดียวกันพร้อมกันสองเครื่อง** — `.scan.lock` กันไว้แล้ว (เครื่องที่สองจะ error ทันทีถ้า Mac เปิดค้างอยู่) ปิด GUI บน Mac ก่อน sync ไปเครื่องที่สองเสมอ
- CUDA/Windows path ยังไม่เคยทดสอบจริงในโปรเจกต์นี้ — ลองกับ `Test_1.mp4` (คลิปสั้น, อยู่ใน `data/input/videos/`) ก่อนลงมือกับตอนเต็ม
- `--device cuda` บังคับใช้ GPU; ถ้า error ให้ลอง `--device auto` เพื่อ fallback เป็น CPU อัตโนมัติ
