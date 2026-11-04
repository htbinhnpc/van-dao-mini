# Vấn Đạo API knowledge

Ghi nhận khi kiểm tra website `https://vandaonghichmenh.hongvan.net:60010` vào ngày 2026-11-04. Phân biệt rõ thông tin lấy từ frontend (tĩnh) với request đã thử thực tế. Không coi các route dưới đây là API ổn định/chính thức nếu nhà phát hành chưa xác nhận.

## Kết quả kiểm tra trực tiếp

| Request | Kết quả |
|---|---|
| `GET /` | `200`; trả HTML tải React app và các bundle JS/CSS. |
| `GET /api/maintenance` | `200`; JSON quan sát được: `{"ok":true,"serverNow":1793790385866,"maintenance":null}`. |
| `GET /api/announcements` không có session | `401 Unauthorized`. |
| `GET /api/events` không có session | `401 Unauthorized`. |
| `POST /api/auth/login` | Đã thử một lần với thông tin người dùng cung cấp; trả `403 Forbidden`. Không nhận được session và không tiếp tục gọi API cần xác thực. Không thử lại. |

Không gửi lệnh game hay request làm thay đổi trạng thái. Vì đăng nhập thất bại, chưa xác minh được response đăng nhập thành công, cookie/session, API trạng thái sau đăng nhập, hoặc luồng tự động trên tài khoản thật.

## Giao thức quan sát được trong frontend

Bundle frontend (`assets/store-BCoGv6eH.js`) cho thấy wrapper HTTP:

- Gửi JSON với `Content-Type: application/json` khi có body.
- Dùng `credentials: "same-origin"`, do đó trình duyệt gửi/nhận session cookie cùng origin.
- Đọc response dưới dạng JSON. Nếu HTTP không thành công hoặc `ok: false`, ném lỗi lấy mã từ `errorCode` (hoặc `INTERNAL`), status và `details`.
- Timeout client: 30 giây.
- Lệnh game có header `idempotency-key`; client có retry giới hạn cho lỗi mạng. Không nên tự retry lệnh có tác dụng phụ nếu chưa hiểu rõ idempotency phía server.

### Xác thực được suy ra từ bundle (chưa xác minh response thành công)

| Method | Path | Body quan sát được |
|---|---|---|
| `POST` | `/api/auth/login` | `{ username, password, remember }`; có thể thêm `newPassword` trong nhánh đổi mật khẩu. |
| `POST` | `/api/auth/register` | `{ username, password, remember }` |
| `POST` | `/api/auth/recover` | `{ username, code, newPassword, remember }` |
| `GET` | `/api/auth/me` | Không có body; frontend gọi để kiểm tra phiên. |
| `POST` | `/api/auth/logout` | `{}` |
| `GET` | `/api/auth/sessions` | Không có body. |
| `POST` | `/api/auth/sessions/revoke` | `{ sessionId }` |

### State và command API suy ra từ bundle

- `GET /api/state` — trạng thái game; response schema chưa xác minh.
- `POST /api/cmd/{command}` — body `{ payload, expectedVersion }`, gửi `idempotency-key`.
- Client mini-client còn tham chiếu `GET /api/cm/state`, `/api/cm/gw`, `/api/cm/tl` và `POST /api/cm/cmd/{command}`. Đây là các route của chế độ/client khác trong bundle; **không** khẳng định phù hợp với endpoint game thường.
- Các lệnh được README liệt kê gồm `settle`, `settings.set`, `activity.set`, `quest.claim`, `daily.claim`, `weekly.claim`, `achievement.claim`, `mail.claimAll`, `x2.daily.claim`, `craft.start`, `item.use`, `boss.fight`, `field.plant`, `field.harvest`, `field.rush`. Chưa gửi lệnh nào trong lần kiểm tra này.

### Một số route khác được bundle tham chiếu

`/api/characters`, `/api/characters/select`, `/api/character`, `/api/mail`, `/api/market`, `/api/auctions`, `/api/arena`, `/api/chat`, `/api/friends`, `/api/guild`, `/api/guilds`, `/api/guildquests`, `/api/guildwar`, `/api/worldboss`, `/api/ranking`, `/api/maintenance`, `/api/announcements`, `/api/events`.

Danh sách này chỉ phản ánh route string trong bundle, không phải đặc tả đầy đủ về method, payload, quyền truy cập hay response.

## Đối chiếu dự án tham chiếu `D:\Binh_Dev\van-dao-mini`

Đã đọc mã nguồn API, game client và migration Supabase của dự án tham chiếu (không đọc `.env.local`, không chạy code của dự án đó). Các chi tiết dưới đây là cách dự án tham chiếu tích hợp, không phải xác nhận từ tài liệu API chính thức.

### Luồng liên kết game account

1. Backend gọi `POST {GAME_ORIGIN}/api/auth/login` với JSON `{ "username": ..., "password": ..., "remember": true }`.
2. Backend tìm cookie `vd_sid` trong `Set-Cookie`, chỉ giữ phần `name=value` để gửi ở các request sau. Dự án tham chiếu không lưu mật khẩu game.
3. Gọi `GET {GAME_ORIGIN}/api/state` với cookie để kiểm tra session và lấy `state` ban đầu.
4. Dự án tham chiếu trả cookie vào Supabase bằng AES-256-GCM, lưu riêng ciphertext, IV và authentication tag. Khóa 32 byte dạng hex nằm trong biến môi trường `APP_ENCRYPTION_KEY`.

Header game client được tham chiếu: `Origin`, `Referer`, `Cookie`, `User-Agent: VanDaoMiniClient/1.0`; timeout 25 giây. API login dùng cùng origin/referer và JSON content type. **Không lưu session plaintext, không đưa cookie về frontend.**

Login thực tế được thử riêng trong cuộc hội thoại trước đó và trả `403`; do đó body/response thành công, cookie và state chưa được xác minh trực tiếp tại thời điểm ghi nhận. Luồng trên được suy ra từ mã nguồn dự án tham chiếu.

### Đọc state và gửi lệnh

- `GET /api/state` → dự án tham chiếu yêu cầu response có `state`; lưu snapshot vào `game_accounts.state_snapshot`.
- `POST /api/cmd/{command}` với header `Idempotency-Key: <UUID>` và JSON `{ "payload": { ... }, "expectedVersion": state.stateVersion ?? 1 }`.
- Dự án tham chiếu kiểm tra `response.ok`, JSON `ok === false`, và đọc `message` / `errorCode` khi báo lỗi.
- Allowlist lệnh: `settle`, `settings.set`, `activity.set`, `quest.claim`, `daily.claim`, `weekly.claim`, `achievement.claim`, `mail.claimAll`, `x2.daily.claim`, `craft.start`, `item.use`, `boss.fight`, `field.plant`, `field.harvest`, `field.rush`.
- Payload đã được README nêu rõ cho `craft.start` (`{ recipeId, count }`), `item.use` (`{ itemId, qty: 1 }`), `boss.fight` (`{ bossId }`). Với lệnh khác, cần đọc state/game implementation trước khi gửi.
- Gửi state version và idempotency key; không retry mù các lệnh có tác dụng phụ. Client tham chiếu chỉ retry giới hạn ở lỗi mạng với cùng một idempotency key.

### Dashboard API của dự án tham chiếu (không phải API game)

Các route dưới đây là API nội bộ của dự án tham chiếu, hữu ích làm mẫu thiết kế cho backend Python:

| Route | Method | Tác dụng |
|---|---|---|
| `/api/health` | `GET` | Health check. |
| `/api/auth` | `GET`, `POST`, `DELETE` | Kiểm tra, tạo, xóa phiên dashboard trong implementation tham chiếu. |
| `/api/accounts` | `GET`, `POST` | Liệt kê/liên kết game account; POST đăng nhập game và lưu account. |
| `/api/session` | `GET` | Dashboard snapshot: accounts, state, config, logs. |
| `/api/state?accountId=...` | `GET` | Đọc và đồng bộ game state. |
| `/api/config?accountId=...` | `GET`, `POST` | Đọc/cập nhật cấu hình automation. |
| `/api/config/sync?accountId=...` | `POST` | Đồng bộ một phần config từ thiết lập trong game. |
| `/api/command` | `POST` | Body có `accountId`, `cmd`, `payload`; chỉ chấp nhận allowlist. |
| `/api/tick` | `POST` | Chạy một vòng automation thủ công. |
| `/api/progress?accountId=...` | `GET` | Đọc nhật ký gần đây. |
| `/api/account?accountId=...` | `PATCH`, `DELETE` | Đổi nhãn hoặc gỡ account. |
| `/api/cron` | `GET`, `POST` | Cron tick các account đến hạn; xác thực secret, lease account và dừng trước deadline Function. |

### Supabase và automation từ mã nguồn tham chiếu

- Schema tham chiếu dùng hai bảng `game_accounts` và `automation_logs`. Account chứa `owner_id`, `game_username`, `session_ciphertext`, `session_iv`, `session_tag`, JSON `config`, `automation_data`, `enabled`, `next_run_at`, `lease_until`, `state_snapshot`, `last_tick_at`, `last_error`.
- Cron lấy account enabled đến hạn, dùng lease ngắn để chống chạy đồng thời, xử lý batch tuần tự và để các account chưa chạy ở lượt Cron sau. Secret được kiểm tra qua Bearer hoặc header Vercel Cron.
- Chu kỳ cấu hình được clamp từ 60 đến 300 giây. Mặc định automation tắt; `autoCraft`, `autoUse`, `autoBoss`, `autoFarm` đều tắt. Nhận quest/daily/mail mặc định bật trong config mẫu.
- Các thao tác đan, boss, gieo/thu hoạch có điều kiện trước khi gửi lệnh; chi tiết điều kiện đã mô tả trong README dự án tham chiếu và được triển khai trong `lib/game.js`.
- Dự án tham chiếu là cấu hình một dashboard owner; skeleton hiện tại hướng tới local user và nhiều chủ sở hữu. Khi áp dụng, giữ ràng buộc owner trên mọi truy vấn, mã hóa session và không dựa riêng vào RLS nếu backend dùng service-role key.

## Giới hạn và bước tiếp theo

1. `403` ở login chưa đủ để kết luận sai mật khẩu: có thể là chính sách tài khoản, chặn request tự động/WAF, hoặc cơ chế khác. Không tiếp tục thử thông tin đăng nhập.
2. Nếu chủ tài khoản muốn debug tiếp, đăng nhập thủ công trong trình duyệt và chia sẻ request/response đã loại bỏ `Cookie`, `Set-Cookie`, mật khẩu, token và dữ liệu cá nhân. Cần tối thiểu login thành công, `GET /api/auth/me`, `GET /api/state`, và một request chỉ đọc.
3. Chỉ thử lệnh làm thay đổi game khi chọn rõ lệnh cụ thể và xác nhận tác động chấp nhận được; trước hết nên dùng môi trường/tài khoản thử nghiệm nếu có.
4. Với ứng dụng riêng: không lưu mật khẩu game nếu không cần; mã hóa session khi lưu Supabase, giới hạn quyền truy cập bằng RLS, và không gửi session game về React hoặc ghi vào log.

## Kiểm tra game có kiểm soát sau khi triển khai logic

Với sự cho phép của người dùng, đã thử một lần bằng tài khoản do người dùng cung cấp:

1. `POST /api/auth/login` → thành công; backend nhận `vd_sid`.
2. `GET /api/state` → thành công; response có `state` và `stateVersion`.
3. `POST /api/cmd/settle` với `{ "payload": {}, "expectedVersion": 1119 }` và `Idempotency-Key` → thành công, response có `settle` và `state`.

Không lưu lại thông tin đăng nhập, cookie/session hoặc nội dung state trong repo/tài liệu. Không thử các lệnh tiêu hao vật phẩm/tài nguyên. `settle` là lệnh game thật và có thể cập nhật tiến độ tu vi; đây không phải mock hay sandbox.

## Thông tin đăng nhập

Thông tin đăng nhập đã được cung cấp trong hội thoại và dùng cho đúng một lần thử login; không ghi lại giá trị đó trong tài liệu hay log. Nếu đây là mật khẩu đang dùng thật, nên đổi mật khẩu sau khi trao đổi trong chat.
