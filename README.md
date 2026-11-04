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

Mini client chỉ dùng các lệnh của game client qua API game (payload đã đối chiếu, không gọi endpoint quản trị):

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
equip.best
minor.trial
sect.task.claim
season.task.claim
title.claim
pet.adopt
npc.talk
npc.claim
hunt.run
```

Không chỉnh sửa dữ liệu máy chủ hay vượt qua giới hạn của game. Trên Vercel, Cron xử lý lần lượt các tài khoản đến hạn và dừng trước deadline Function; các tài khoản còn lại tiếp tục ở lượt Cron sau. Nhịp gọi Cron thực tế do `vercel.json` quyết định.

### Auto mở rộng (tất cả mặc định tắt)

Đối chiếu JavaScript **công khai** của game ngày 2026-11-04 (Chrome đang khóa cache; đã dùng bundle công khai thay thế theo lựa chọn người dùng). Đây là logic/payload quan sát từ client, không phải mã xử lý trên server hoặc cam kết API ổn định. Xem bằng chứng trong `api_knowledge.md`.

| Cấu hình | Điều kiện / giới hạn |
|---|---|
| `autoEquipBest` | Khi có đồ trong túi, gọi `equip.best`; game tự chọn. Không tự bán, phân giải, mở khóa hay thay loại vũ khí bằng lệnh riêng. Có thể đổi bộ đồ theo bộ chọn của game. |
| `autoMinorTrial` | Chỉ `character.next=minor`, đủ tu vi, `minorGate.kind=trial` chưa đạt; tối đa 1 lần/10 phút, kể cả thua/lỗi. Không tự đột phá lớn; auto lên tầng của game áp dụng ở lần settle sau. |
| `autoSectTasks`, `autoSeasonTasks` | Nhận nhiệm vụ tông môn/lễ hội có `claimed=false`, đủ `current/target`; không đóng góp, mua hàng hay làm nhiệm vụ tốn vật phẩm. |
| `autoTitles` | Chỉ nhận danh hiệu `earned=true`, `owned=false`; không tự mang/thay danh hiệu. Ba nhóm thưởng này tổng cộng tối đa 3 lệnh/vòng. |
| `autoPetAdopt` | Tối đa 1 linh thú/vòng khi `canAdopt=true`, `owned=false`; có thể tiêu khế ấn hợp khế. Không tự xuất chiến, nuôi hay tiến hóa. |
| `autoNpcTalk` | Tối đa 2 đạo hữu đã gặp/vòng, chưa trò chuyện ngày và thiện cảm dưới 1000; không tặng quà hay tự chọn quan hệ. |
| `autoNpcRewards` | Tối đa 2 quà mốc thiện cảm/vòng; dùng state mới sau trò chuyện và bỏ qua mốc đã nhận. |
| `autoHunt` | Bắt buộc chọn `huntPetId` trong 40 linh thú khế ấn; đủ cấp, còn lượt trên `huntReserveRuns`, chưa đủ khế ấn và chưa thu nhận. Tối đa 1 lượt/vòng, chờ `huntIntervalMin` (mặc định 10 phút) kể cả thua. Không mua thêm lượt. |

Mỗi vòng dùng state/version mới từ phản hồi trước, tổng cộng **tối đa 12 lệnh**, chỉ bắt đầu lệnh trong cửa sổ 40 giây. Phần chưa chạy để vòng sau. Nếu lệnh lỗi, timeout, xung đột version hoặc phản hồi thiếu state, dừng phần còn lại và lưu lỗi; không retry lệnh có tác dụng phụ với key mới. Lịch sử khoảng nghỉ lưu trong `automation_data`, không chỉ giữ trong RAM. Các kiểm thử dùng mock, chưa bật/thử auto mới trên tài khoản game thật.

Chọn các auto trong tab **Tự động**, lưu cấu hình riêng cho từng tài khoản, rồi dùng **Chạy ngay** để chạy một vòng theo cấu hình đã lưu. Cron chỉ chạy khi tài khoản bật trợ lý; nhịp thực tế còn phụ thuộc lịch Cron của môi trường triển khai (cấu hình Vercel hiện tại là mỗi ngày một lần).

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

### Dashboard: bản cập nhật giao diện tu tiên

- Bảng màu ngọc bích, vàng cổ, nền mực xanh đối chiếu từ CSS game gốc. Hình Thanh Khê/nhân vật phục vụ nội bộ từ `frontend/public/game-art/`; xem nguồn và lưu ý quyền sử dụng ở `frontend/public/game-art/README.md`. Không tải font/ảnh bên thứ ba khi chạy dashboard.
- Tổng quan có cảnh tu luyện, metadata cảnh giới/hoạt động, thanh tu vi, tài nguyên, nhiệm vụ và chỉ số (`state.stats`, có fallback schema cũ). Không mô phỏng số liệu hoặc chạy game bằng hiệu ứng giao diện.
- Auto chia 6 nhóm, tìm kiếm, thiết lập mục tiêu/hạn mức, kiểm tra thay đổi chưa lưu, hoàn tác và xác nhận các mục tác động game. Lưu cấu hình không tự gọi tick. Chuyển trang/tài khoản/đăng xuất và tải lại trang được bảo vệ khi có bản nháp chưa lưu.
- Chạy vòng thủ công và gỡ liên kết yêu cầu xác nhận. Chặn gửi trùng khi request đang chạy. Lỗi tải dữ liệu không bị nhầm là đã đăng xuất, túi trống hoặc thao tác thành công.
- Túi đồ gồm vật liệu từ API, trang bị từ snapshot và tiền tệ; tìm không dấu, lọc, xem chi tiết chỉ đọc. Nhật ký có lọc trạng thái/nội dung. Mobile có thanh điều hướng dưới, hỗ trợ bàn phím, focus modal và reduced motion.

#### Kiểm thử giao diện

```powershell
npm --prefix frontend install
npm --prefix frontend exec -- playwright install chromium
npm run build
npm --prefix frontend run test:e2e
python -m unittest discover -s tests -v
```

Playwright chạy Chromium thật trên **production preview**, với desktop và viewport iPhone; kiểm tra các luồng chính, xác nhận tiêu hao, bản nháp, lỗi API, nhiều độ rộng 320–1440px, bàn phím và WCAG qua axe. API được intercept bằng **tài khoản/dữ liệu giả lập**, không đọc `.env` hay Chrome cache, không đăng nhập/gửi lệnh tới game thật và không truy cập Supabase thật. Ảnh chụp/trace khi kiểm thử nằm trong `frontend/test-results/`, báo cáo HTML trong `frontend/playwright-report/` (không commit).

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
