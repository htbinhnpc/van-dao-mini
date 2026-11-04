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
  - **Tự luyện đan:** chọn một công thức cụ thể hoặc để hệ thống tự chọn đan tốt nhất có thể luyện; tôn trọng cấp, nguyên liệu, linh thạch, số lò trống và giới hạn tuần. Có thể đặt số lượng muốn giữ để tránh luyện thừa.
  - **Tự dùng đan:** ưu tiên đan tăng tốc tu vi tốt nhất đang có, chỉ dùng khi buff sắp hết và không vượt thời lượng tối đa của game. Có thể bật thêm đan tu vi trực tiếp và chế độ chỉ dùng loại tốt nhất.
  - **Tự đánh boss khu vực:** đánh lần lượt tất cả boss của vùng đã hạ lần đầu khi hồi chiêu kết thúc và đủ cấp. Mỗi boss có nhịp cục bộ riêng (mặc định 10 phút, đặt 0 để chỉ theo hồi chiêu game); có thể ghim một boss nếu muốn tập trung.
  - Nút chạy ngay, kết toán thủ công và áp dụng hoạt động.
- **Nhật ký** — ghi lại kết toán, đổi hoạt động, nhận thưởng, luyện/dùng đan và lỗi; lọc theo mức độ.

## Yêu cầu

- Node.js **20 trở lên** (khuyến nghị 22+).
- Tài khoản game Vấn Đạo đang hoạt động.
- Kết nối tới `https://vandaonghichmenh.hongvan.net:60010`.

## Chạy

```powershell
cd D:\Binh_Dev\van-dao-mini
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
│  └─ meta.json           # metadata vật phẩm, trang bị, kỹ năng, công thức, vùng, boss, cảnh giới…
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
craft.start
item.use
boss.fight
```

Không chỉnh sửa dữ liệu, không gửi request giả, không vượt qua giới hạn của game. Vòng tự động chạy trên server Node cục bộ nên vẫn tiếp tục khi đóng tab, miễn là server còn chạy. Nhịp mặc định là 15 giây; không nên đặt quá thấp.

### Cơ chế luyện/dùng đan

- **Tự luyện đan** chỉ gọi `craft.start` với `{ recipeId, count }`. Trước khi gửi lệnh, client kiểm tra cấp nhân vật, nguyên liệu, linh thạch, số lò trống và giới hạn mẻ/tuần. Nếu chọn “Tự chọn”, client ưu tiên đan tăng tốc tu vi có `ratePct` cao nhất đang luyện được, sau đó mới tới đan tu vi trực tiếp.
- **Tự dùng đan** chỉ gọi `item.use` với `{ itemId, qty: 1 }`, mỗi vòng tối đa một đan. Với đan buff, client đọc `state.buffs` và chỉ dùng khi thời gian còn lại thấp hơn ngưỡng cấu hình, đồng thời không dùng nếu sẽ vượt `maxTotalMs` của game. Mặc định chỉ dùng loại tốt nhất đang có để không tiêu đan thấp hơn vô ích.
- Đan tu vi trực tiếp (`cultivation_exp`) mặc định **tắt** vì thường là đan sự kiện quý; bật rõ trong tab Tự động nếu muốn dùng tự động.
- Các thao tác này đều là lệnh chính thức, không can thiệp bộ nhớ game hay dữ liệu máy chủ.
- Tự luyện đan và tự dùng đan mặc định **tắt**; bật riêng trong tab **Tự động** sau khi đã kiểm tra công thức, ngưỡng buff và số lượng muốn giữ.

### Cơ chế đánh boss khu vực

- **Tự đánh boss** chỉ gọi `boss.fight` với `{ bossId }`. Client chỉ chọn boss thuộc vùng đã `bossCleared` (đã hạ lần đầu), vùng đã mở, nhân vật đủ `reqLevel` và `bossCooldownUntil` đã hết.
- Client đánh **tuần tự** qua danh sách boss đã vượt, mỗi vòng chọn boss kế tiếp đang sẵn sàng. Mỗi boss có nhịp cục bộ riêng theo ô “Nhịp đánh mỗi boss” (mặc định **10 phút**, đặt **0** để chỉ dựa vào hồi chiêu thực tế của game).
- Có thể ghim một vùng cụ thể trong danh sách; khi đó client chỉ đánh boss của vùng đó và bỏ qua các boss khác.
- Thua không mất gì và không bị hồi chiêu; client sẽ chuyển sang boss kế tiếp ở nhịp sau. Kết quả thắng/thua và phần thưởng được ghi vào nhật ký.
- Tính năng mặc định **tắt**; bật riêng trong tab **Tự động**.

### Cấu hình được lưu và đồng bộ

- Cấu hình tự động được lưu tại `.config.json` trong thư mục dự án và tự nạp lại khi khởi động.
- Lần đầu chạy (chưa có `.config.json`), client lấy các thiết lập đang có trong game như tự lên tiểu tầng, ngưỡng dọn trang bị và hoạt động hiện tại để khởi tạo cấu hình.
- Nút **Đồng bộ thiết lập từ game** trong tab **Tự động** đọc lại các thiết lập đó từ tài khoản và ghi đè cấu hình cục bộ khi bạn muốn.

## Ghi chú

- Đây là công cụ cá nhân, không liên kết chính thức với nhà phát triển game.
- API game có thể thay đổi sau cập nhật; khi đó cần cập nhật `server.js` hoặc `data/meta.json`.
- Không mở cổng 3010 ra Internet. Server chỉ lắng nghe `127.0.0.1`.
- Tệp `.session.json` và `.config.json` được tạo khi chạy, không nên chia sẻ hoặc commit.
- Nếu phiên hết hạn, đăng xuất rồi đăng nhập lại.
