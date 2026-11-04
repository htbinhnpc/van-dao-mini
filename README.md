# Vấn Đạo · Mini Client

Mini client cho **Vấn Đạo: Nghịch Mệnh** — bảng chỉ số nhân vật, tóm tắt vật phẩm, quản lý nhiều tài khoản và trợ lý tự động.

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
  - Bật/tắt trợ lý, chọn nhịp chạy 1 – 5 phút khi chạy trên Vercel.
  - Tự kết toán tu vi, tự lên tiểu tầng, giữ hoạt động và điểm săn.
  - Tự lùi điểm săn khi thua, hoặc về bế quan nếu không còn điểm phù hợp.
  - Tự nhận nhiệm vụ, thưởng ngày/tuần, thành tựu, thư có quà và gói mở rộng ngày.
  - Tự dọn trang bị rơi theo ngưỡng phẩm cấp (phân giải hoặc bán).
  - **Tự luyện đan:** chọn một công thức cụ thể hoặc để hệ thống tự chọn đan tốt nhất có thể luyện; tôn trọng cấp, nguyên liệu, linh thạch, số lò trống và giới hạn tuần. Có thể đặt số lượng muốn giữ để tránh luyện thừa.
  - **Tự dùng đan:** ưu tiên đan tăng tốc tu vi tốt nhất đang có, chỉ dùng khi buff sắp hết và không vượt thời lượng tối đa của game. Có thể bật thêm đan tu vi trực tiếp và chế độ chỉ dùng loại tốt nhất.
  - **Tự đánh boss khu vực:** đánh lần lượt tất cả boss của vùng đã hạ lần đầu khi hồi chiêu kết thúc và đủ cấp. Mỗi boss có nhịp cục bộ riêng (mặc định 10 phút, đặt 0 để chỉ theo hồi chiêu game); có thể ghim một boss nếu muốn tập trung.
  - **Tự gieo/thu hoạch:** thu ô chín trước, sau đó gieo giống hợp lệ trong Linh Điền và các Sinh cảnh đã mở; có thể đặt giống ưu tiên và khoản linh thạch dự phòng.
  - Nút chạy ngay, kết toán thủ công và áp dụng hoạt động.
- **Tài khoản & tiến độ:** liên kết nhiều tài khoản game, xem cấp nhân vật, hoạt động, tình trạng ô trồng, lượt tự động gần nhất và lỗi theo từng tài khoản.
- **Nhật ký** — ghi lại kết toán, đổi hoạt động, nhận thưởng, luyện/dùng đan và lỗi; lọc theo mức độ.


- Tài khoản game Vấn Đạo đang hoạt động.
- Kết nối tới `https://vandaonghichmenh.hongvan.net:60010`.

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
field.plant
field.harvest
field.rush
```

Không chỉnh sửa dữ liệu, không gửi request giả, không vượt qua giới hạn của game. Trên Vercel, Cron xử lý theo phút và lần lượt từng tài khoản đến khi gần hết thời lượng Function; các tài khoản còn lại tiếp tục ở lượt Cron sau.

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

- Cấu hình tự động được lưu riêng theo từng tài khoản trong Supabase.
- Khi liên kết game account lần đầu, backend lấy các thiết lập cơ bản từ game để khởi tạo cấu hình; các thao tác tiêu hao tài nguyên mặc định tắt.
- API đồng bộ config có thể đọc lại các thiết lập game như tự lên tiểu tầng, ngưỡng dọn trang bị và hoạt động hiện tại.

## Ghi chú

- Đây là công cụ cá nhân, không liên kết chính thức với nhà phát triển game.
- Nếu phiên hết hạn, đăng xuất rồi đăng nhập lại.

## Skeleton phát triển

- `frontend/`: React + Vite dashboard.
- `api/`: FastAPI backend, local auth, game account service, dashboard APIs và automation worker.
- `supabase/migrations/`: schema cho local users, session dashboard, game accounts, config, runs và logs.
- `api_knowledge.md`: request/response đã quan sát và thông tin giao thức tham chiếu.

### Chạy local

1. Tạo môi trường Python và cài dependencies: `pip install -r requirements.txt`.
2. Cài frontend dependencies: `npm --prefix frontend install`.
3. Chạy migration `supabase/migrations/0001_initial_schema.sql` trên Supabase và cấu hình `.env` từ `.env.example`.
4. Chạy API: `uvicorn api.index:app --reload --port 8000 --env-file .env`.
5. Chạy dashboard ở terminal khác: `npm run dev`.

Tạo dashboard user đầu tiên bằng `POST /api/v1/auth/bootstrap` với `{ "username", "password", "setup_token" }`; endpoint chỉ hoạt động khi chưa có user nào và `APP_SETUP_TOKEN` khớp. Sau đó đăng nhập qua `POST /api/v1/auth/login`.

`frontend/vite.config.ts` proxy `/api` về backend local. Sao chép `.env.example` thành `.env` và cấu hình secrets trước khi kết nối Supabase. Không commit `.env` hoặc đưa service-role key/session game ra frontend.

Các tính năng tự động chỉ chạy khi bật `enabled` cho tài khoản. Cron cần biến `CRON_SECRET`; session game được mã hóa AES-GCM bằng `SESSION_ENCRYPTION_KEY` trước khi lưu.
