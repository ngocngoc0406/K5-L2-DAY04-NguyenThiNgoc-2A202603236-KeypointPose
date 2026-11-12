# Demo Facial Landmarks + Person Pose

Ứng dụng độc lập, chạy local bằng FastAPI và OpenCV; không đọc/ghi vào ảnh,
nhãn, assignment hoặc export của bài lab. **Không dùng dự đoán của demo làm
nhãn nộp lab.**

## Trạng thái

- Đã có giao diện upload, chọn Face / Person / Both, vẽ skeleton, confidence,
  nhiều khuôn mặt/người, chọn nhiều ảnh/thư mục và lưu batch theo lựa chọn.
- Batch được export thành COCO Keypoints ZIP riêng cho `face` hoặc `person`,
  có thể nhập vào CVAT để kiểm tra/chỉnh sửa. Confidence thấp hoặc keypoint
  ngoài ảnh được xuất `v=0`; model không suy luận occlusion nên không tự gán
  `v=1`.
- Nhánh person dùng Ultralytics YOLO pose với 17 điểm COCO.
- Nhánh face dùng MediaPipe Face Detector + Face Landmarker, rồi ánh xạ tường
  minh 13 điểm vào `src/keypoint_schema.json`.
- Schema face hiện tại không có eyebrow landmarks; demo giữ nguyên đúng 13 tên
  điểm đó. Muốn thêm điểm lông mày cần một schema/project riêng, không thể âm
  thầm đổi schema bài lab.
- Uploader Roboflow chỉ nhận một loại dữ liệu mỗi lần, yêu cầu manifest/schema
  đúng, chạy dry-run mặc định, và yêu cầu `--confirm-upload` để gửi.
- **CVAT đã khảo sát read-only; không đổi Compose/container/volume.** CVAT và
  Nuclio đang chạy. YOLOv7 Nuclio function chỉ khai báo bounding boxes;
  MMPose HRNet32 có skeleton `body` 17 điểm nhưng sublabel là `1..17`, đồng
  thời function còn khai báo `feet`, `face` 68 điểm và `hands` 42 điểm. Nó
  không khớp tên label `person` và thứ tự có tên của schema lab nên chưa thể
  gắn trực tiếp vào project đó. Chưa thấy face-keypoint Nuclio function.
- Dashboard Nuclio không truy cập được tại `localhost:8070`; CVAT
  `/api/lambda/functions` trả `401` khi không đăng nhập. Không thử vượt qua
  xác thực. ZIP COCO là đường nhập review không cần thay đổi Nuclio.

## Chạy local trên Windows

Python 3.10–3.12 được khuyến nghị do tương thích wheel của MediaPipe và PyTorch.
Tạo môi trường riêng:

```powershell
cd .\pose_landmark_system
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Tải model face công khai vào `models/` (lần đầu cần internet):

```powershell
.\scripts\download_face_models.ps1
```

YOLO pose tải checkpoint pretrained `yolo11n-pose.pt` khi inference lần đầu
nếu chưa có trong cache Ultralytics. Có thể đặt `PERSON_POSE_MODEL` trỏ tới
checkpoint pose khác tương thích COCO-17. Face Landmarker là model pretrained
công khai tải bằng script phía trên. Hai nhánh này cho phép demo mà chưa cần
train model riêng; Roboflow uploader không tự train hoặc thay checkpoint.

Khởi chạy:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mở [http://127.0.0.1:8000](http://127.0.0.1:8000). Chọn một hay nhiều ảnh hoặc
thư mục, chọn Face / Person / Both, rồi chạy inference. Bật “Lưu ảnh và JSON kết
quả” để cho phép export; mặc định dữ liệu chỉ ở RAM và không được lưu.

- `GET /api/health`: health check.
- `POST /api/predict`: inference cho một ảnh.
- `POST /api/batch`: batch inference (tối đa 50 ảnh, 100 MB tổng).
- `GET /api/batch/{batch_id}/export/{face|person}`: tải COCO Keypoints ZIP riêng
  theo loại. Batch phải được lưu trước khi export.

Mỗi ảnh tối đa 10 MB / 25 megapixel. Export đặt keypoint `v=2` khi confidence
ít nhất 0.2 và tọa độ trong ảnh; các điểm khác là `v=0` với tọa độ `0,0`.
`v=1` cần review người vì các model demo không cung cấp nhãn occlusion đáng tin
cậy. Đây là nhãn gợi ý tự động; cần kiểm tra/chỉnh sửa trước khi dùng làm
ground truth.

Để chạy model từ checkpoint/path khác, đặt biến trước khi mở server:

```powershell
$env:PERSON_POSE_MODEL = "D:\models\person-pose.pt"
$env:FACE_DETECTOR_MODEL = "D:\models\blaze_face_short_range.tflite"
$env:FACE_LANDMARKER_MODEL = "D:\models\face_landmarker.task"
```

## Roboflow: hai project, hai dataset

1. Tạo riêng hai project loại Keypoint Detection trên Roboflow: một project
   **face** (13 điểm theo schema lab), một project **person** (17 điểm COCO).
   Không upload lẫn loại annotation.
2. Dùng annotation đã có và đã kiểm tra; không tự sinh nhãn từ dự đoán. Lưu hai
   dataset bên ngoài repo, ở hai thư mục tách biệt. Xem
   [`datasets/README.md`](datasets/README.md) để biết manifest, schema, nguồn
   dataset ứng viên và điều cần xác minh về license.
3. Trong Roboflow kiểm tra thứ tự keypoint và một số annotation mẫu, rồi tạo
   version riêng cho từng project.
4. Đặt biến trong PowerShell. API key chỉ tồn tại trong process/shell hiện
   tại; với sử dụng lâu dài, lấy key từ secret manager hoặc cấu hình secret
   riêng của môi trường, không commit:

   ```powershell
   $env:ROBOFLOW_API_KEY = "<your-private-key>"
   $env:ROBOFLOW_WORKSPACE = "your-workspace"
   $env:ROBOFLOW_FACE_PROJECT = "your-face-project"
   $env:ROBOFLOW_PERSON_PROJECT = "your-person-project"
   $env:FACE_DATASET_DIR = "D:\datasets\face"
   $env:PERSON_DATASET_DIR = "D:\datasets\person"
   ```

5. Cài SDK bổ sung và chạy dry-run riêng cho từng project:

   ```powershell
   python -m pip install -r requirements-roboflow.txt
   python .\roboflow_upload.py face
   python .\roboflow_upload.py person
   ```

   Chỉ sau khi duyệt đường dẫn, manifest, license và destination trong kết quả
   dry-run, mới thêm `--confirm-upload`. Script từ chối cùng project ID cho
   face/person và từ chối các đường dẫn `data/`, `src/lab/images/`,
   `src/exports/` của repo. Upload chưa được thực hiện tự động.

## Đưa batch vào CVAT để review

1. Chọn “Lưu ảnh và JSON kết quả”, chạy batch, rồi export riêng `Face COCO`
   hoặc `Person COCO`.
2. Trong CVAT, tạo **project demo mới**, không dùng project/job bài lab. Dùng
   đúng skeleton label và keypoint order ở `src/keypoint_schema.json` (một
   label `face` cho face task, hoặc `person` cho person task).
3. Import ZIP bằng dataset format **COCO Keypoints 1.0**. Nếu format không hiện
   trong danh sách import của phiên bản CVAT này, dừng lại và không thay
   Compose; kiểm tra adapter/format tương thích trước.
4. Mở task/job, review điểm và visibility, sửa dự đoán sai trong CVAT, rồi
   export dataset đã kiểm tra. Không dùng kết quả auto-annotation làm nhãn nộp
   bài lab.

## Thêm Face-13 và Person-COCO17 vào CVAT Local

Hai Nuclio detector độc lập được cung cấp:

| Model trong CVAT | Nguồn inference | Output |
|---|---|---|
| `Person Pose COCO-17` | Adapter gọi function MMPose `pth-mmpose-hrnet32` đang chạy | Một skeleton `person`, 17 điểm theo COCO |
| `Face Landmarks 13` | Face Detector và Face Landmarker của MediaPipe | Một skeleton `face`, 13 điểm theo schema repo |

Để build/cập nhật và đăng ký hai model trên Nuclio (PowerShell tại thư mục repo):

```powershell
.\pose_landmark_system\scripts\deploy_cvat_functions.ps1
```

Script kiểm tra CVAT, Nuclio, `nuctl` và HRNet đang chạy; tự lấy IP hiện tại
của HRNet trong Docker bridge; tải các model face vào thư mục models; rồi deploy
hai function. Script chỉ deploy/cập nhật các function có tên riêng ở trên,
không sửa Docker Compose, không restart CVAT/HRNet, và không xóa volume/database.
Giữ Docker và các service CVAT/Nuclio/HRNet hoạt động khi chạy script. IP nội bộ
của HRNet có thể đổi sau khi container được tạo lại, nên chạy lại script nếu
Person adapter báo lỗi gọi upstream.

Sau khi deploy:

1. Tạo một **task/project demo mới** trong CVAT, không dùng project/job bài lab.
2. Tạo một skeleton label tên `person` với đúng 17 sublabels/thứ tự COCO, hoặc
   một skeleton label tên `face` với đúng 13 sublabels/thứ tự trong
   `src/keypoint_schema.json`. Mỗi function chỉ xử lý loại đối tượng của mình.
3. Vào **Tasks**, mở menu **Action > Automatic annotation**, chọn model tương ứng,
   map label nếu CVAT yêu cầu, rồi chạy **Annotate**. Xem và chỉnh sửa kết quả
   trong task trước khi export.
4. Nếu model không hiện, kiểm tra trạng thái function:

   ```powershell
   wsl -e nuctl get functions --platform local
   ```

CVAT chỉ liệt kê Nuclio function đã deploy và sẵn sàng; các label/sublabel của
task cần tương thích với model. Xem hướng dẫn chính thức [Automatic
annotation](https://docs.cvat.ai/docs/annotation/auto-annotation/automatic-annotation/)
và [AI models](https://docs.cvat.ai/docs/annotation/auto-annotation/ai-models/).
Không dùng dự đoán tự động làm nhãn nộp bài lab.

## Kiểm thử

Từ thư mục repo:

```powershell
python -m compileall -q pose_landmark_system
python -m pytest pose_landmark_system\tests -q
```

Tests không tải checkpoint, không gọi Roboflow và không kết nối CVAT.
