# Vấn Đạo · Mini Client

Mini client cục bộ cho **Vấn Đạo: Nghịch Mệnh** — bảng chỉ số nhân vật, tóm tắt vật phẩm và tab trợ lý tự động. Giao diện chạy trong trình duyệt, mọi lệnh game được gửi qua một server Node nhỏ trên máy bạn để tránh CORS và giữ phiên đăng nhập an toàn.

## Tính năng

- **Tổng quan**
  - Bảng stat đầy đủ: sinh lực, linh lực, công, pháp công, phòng ngự, kháng, tốc độ, bạo kích, xuyên giáp, hồi phục, giảm hồi chiêu…
  - Cảnh giới, cấp, thanh tu vi, tốc độ tu vi, giới hạn tích lũy.
  - Hoạt động hiện tại, điểm săn, tiến độ chu kỳ, kết quả thắng/thua.
  - Trang bị đang mặc, kỹ năng đã học, căn cơ và xuất thân.
  - Nhiệm vụ đang làm, mốc có thể nhận và thưởng ngày/tuần/thành tựu.
- **Vật phẩm**
  - Tóm tắt linh thạch, vật liệu, trang bị, sức chứa túi và kho đồ.
  - Danh sách vật liệu, tiền tệ và trang bị kèm icon, phẩm cấp, cường hóa, vị trí.
  - Tìm kiếm và lọc theo loại.
- **Tự động**
  - Bật/tắt trợ lý, chọn nhịp chạy 5 giây – 5 phút.
  - Tự kết toán tu vi, tự lên tiểu tầng, giữ hoạt động và điểm săn.
  - Tự lùi điểm săn khi thua, hoặc về bế quan nếu không còn điểm phù hợp.
  - Tự nhận nhiệm vụ, thưởng ngày/tuần, thành tựu, thư có quà và gói mở rộng ngày.
  - Tự dọn trang bị rơi theo ngưỡng phẩm cấp (phân giải hoặc bán).
  - Nút chạy ngay, kết toán thủ công và áp dụng hoạt động.
- **Nhật ký** — ghi lại kết toán, đổi hoạt động, nhận thưởng và lỗi; lọc theo mức độ.

## Yêu cầu

- Node.js **20 trở lên** (khuyến nghị 22+).
- Tài khoản game Vấn Đạo đang hoạt động.
- Kết nối tới `https://vandaonghichmenh.hongvan.net:60010`.

## Chạy

```powershell
cd C:\Users\ASUS\van-dao-mini
npm start
```

Mở trình duyệt tại:

```text
http://127.0.0.1:3010
```

Đăng nhập bằng tài khoản game. Mật khẩu chỉ được gửi tới API đăng nhập của game qua server cục bộ, **không được lưu** trong project. Nếu chọn “Lưu phiên đăng nhập”, server chỉ lưu cookie phiên `vd_sid` trong `.session.json` (đã nằm trong `.gitignore`).

Đổi cổng nếu 3010 đang bận:

```powershell
$env:PORT=3011; npm start
```

## Cấu trúc

```text
van-dao-mini/
├─ server.js              # server cục bộ, proxy API game, vòng tự động, SSE
├─ public/
│  ├─ index.html          # khung giao diện
│  ├─ styles.css          # giao diện ink/jade/gold
│  └─ app.js              # logic hiển thị và thao tác
├─ data/
│  └─ meta.json           # metadata vật phẩm, trang bị, kỹ năng, vùng, cảnh giới…
├─ scripts/
│  └─ build-meta.mjs      # công cụ tái tạo meta từ bundle game (dành cho dev)
├─ package.json
└─ README.md
```

## Nguyên tắc hoạt động

Mini client chỉ dùng các lệnh chính thức của game:

```text
settle
settings.set
activity.set
quest.claim
daily.claim
weekly.claim
achievement.claim
mail.claimAll
x2.daily.claim
```

Không chỉnh sửa dữ liệu, không gửi request giả, không vượt qua giới hạn của game. Vòng tự động chạy trên server Node cục bộ nên vẫn tiếp tục khi đóng tab, miễn là server còn chạy. Nhịp mặc định là 15 giây; không nên đặt quá thấp.

## Ghi chú

- Đây là công cụ cá nhân, không liên kết chính thức với nhà phát triển game.
- API game có thể thay đổi sau cập nhật; khi đó cần cập nhật `server.js` hoặc `data/meta.json`.
- Không mở cổng 3010 ra Internet. Server chỉ lắng nghe `127.0.0.1`.
- Tệp `.session.json` và `.config.json` được tạo khi chạy, không nên chia sẻ hoặc commit.
- Nếu phiên hết hạn, đăng xuất rồi đăng nhập lại.
