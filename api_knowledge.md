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

## Bộ dọn túi Mini (2026-11-05)

Đối chiếu tĩnh bundle công khai đã lưu `main-Bmv0z3VX.js` (hash ở bảng bên dưới), component `zu` và trình dọn nhiều món `Gu`: `item.dispose` nhận `{itemIds: [...], mode: 'sell' | 'salvage'}` và guard version. UI game cắt danh sách ở **60 ID/lệnh**, bỏ đồ `location=equipped`, `locked`, `favorite`; xác nhận riêng đồ không phải phẩm Phàm hoặc đã cường hóa. Đây là bằng chứng phía client, chưa thử mutation trên account thật.

Policy hiện tại bỏ giữ bản dự phòng mỗi `defId`: mặc bằng `equip.best`, chuyển mức cường hóa cao nhất cùng ô sang món đang mặc rồi xét dọn đồ trong túi theo bộ lọc. Bảo vệ khóa/yêu thích/kho, dữ liệu không rõ, ô chưa có đồ mặc và cường hóa cao hơn món mặc chưa chuyển hết được. Metadata dùng `rarity` và `tier` riêng.

`POST /api/v1/accounts/{id}/cleanup/preview` yêu cầu `prepareEquipment:true`: lấy lease, GET state mới, mặc/chuyển cường hóa có phí, lưu snapshot mỗi bước rồi tạo `automation_runs` queued `cleanup_v2` với version sau chuẩn bị/rules/IDs/expiry. Preview v1 không còn thực thi được. `POST .../cleanup/execute`: xác thực owner, subset ID, expiry 120s, lease, GET state + replan, CAS queued→running và một `item.dispose` với idempotency key=run UUID. Không retry hoặc tái dùng preview sau lỗi. Chặn `item.dispose` và `item.transfer` ở endpoint command chung. Auto cũng chuẩn bị trước khi dọn, tắt native salvage trước explicit settle và tuân thủ ngân sách 12 lệnh/vòng.

Đối chiếu tĩnh bundle công khai ngày 2026-11-05: `/assets/main-BNARi4Kn.js`, component `hu`, gọi `item.transfer` `{fromId,toId}` có guard version. Món đích nhận min(cấp nguồn, trần món đích), cấp cũ món đích quay về món nguồn; phí 5% tổng tiền cường hóa các cấp được chuyển, trả bằng tiền của món đích. `/assets/i18n-B6UHPwZV.js`: `Tu` giới hạn x2 ở +5 Trúc Cơ, +10 Nguyên Anh, +15 Khuy Niết, +20 Không Niết; cấp bắt đầu tính theo số tầng cảnh giới. Mini không chuyển nếu làm mất cấp vượt trần, không gọi `item.enhance` để tăng cấp mới. Chỉ GET bundle, chưa thử chuyển trên tài khoản thật.

Tùy chọn Mini `cleanupSkipConfirmation=false` mặc định, lưu riêng từng account. Cả preview nhanh và execute nhận thêm `skipConfirmation` boolean strict; nếu true phải có opt-in đã lưu. Đây chỉ là tùy chọn UI/Mini, **không gửi thêm trường này sang API game** và không bỏ các guard. Nút dọn ngay gọi preview mới rồi execute một mẻ, không lặp/retry. Worker auto không hỏi từng mẻ; UI có thể bỏ xác nhận khi lưu/bật riêng auto dọn nếu tùy chọn này được bật, không bỏ xác nhận tính năng khác.

Audit: lưu intent trước lệnh hủy đồ, rồi kết quả có ID đã dọn/còn lại, rules, tên/mẫu/ID và witness giữ lại, version, nguồn và chế độ xác nhận. Nếu ghi intent lỗi thì không gửi command. Phân biệt started/succeeded/partial/uncertain/blocked/skipped/configured, không suy diễn timeout thành thành công. Không ghi session/cookie hay toàn bộ state vào nhật ký cleanup. UI hiển thị chi tiết và hỗ trợ tìm ID món.

## Chế tạo/tay nghề Mini (2026-11-05)

- Đặc tả đầu vào là `craft-professions.md` (tên người dùng gọi là `craft_profession.md`). Planner tại `api/services/craft_profession.py`; endpoint đọc riêng `/api/v1/accounts/{id}/crafting` áp dụng kiểm tra owner như các endpoint account khác. Metadata public `/meta` cung cấp tên/cấp mở của mọi công thức, không chỉ đan tu luyện.
- Chỉ GET và phân tích tĩnh `/assets/main-BNARi4Kn.js` và `/assets/i18n-B6UHPwZV.js`, không đọc `.env`, cookie hoặc state tài khoản thật. `qp` gửi `craft.start` `{recipeId}` hoặc `{recipeId,count:8}` với guard; Mini gửi count đã tính lại trong 1–8. State client dùng `professions[p]={level,crafted,next}`, `crafting={slots,jobs,weekUsed}`, job có `id,recipeId,finishAt`; `bagCapacity` là sức chứa trang bị trong túi.
- `Vi` phân nghề: 2 công thức bảo hiểm riêng, mapping charm → talisman/array, đồ → forging, còn lại → alchemy. `Hi` trả `floor(level/5)`; `Kp` cộng bonus cả thành phẩm đồ. UI nói mỗi mẻ hoàn tất cộng 1 điểm, tốc độ +3% mỗi cấp sau cấp 1. Khác với câu "không áp dụng Rèn khí" trong đề xuất, client hiện áp dụng bonus cho cả forging.
- Bộ chọn Mini không giả định cấp 10 đã max: cần đủ 4 record hợp lệ, mỗi record có `next:null`. Thiếu thông tin thì chỉ xét các ưu tiên nhiệm vụ/bổ sung đã biết, không chạy filler/sản xuất. Tất cả ETA tới max có ghi ước tính; ngưỡng suy ra 115/150 không quyết định chi tiêu.
- Lưu `craftLevelBudget` (ngày UTC/base/limit/spent), `craftLevelFocus` và `craftJobs` trong `automation_data`. Debit cày trước lệnh, không refund timeout; log intent trước lệnh, kiểm tra version và đủ ID job mới sau phản hồi. Chưa xác nhận đủ mẻ thì dừng, không tự gửi lại. Các handler khác vẫn dùng ngân sách chung 12 lệnh/40 giây; không nới trần game.
- Chưa có economy/gear-opt/market-price trong repo này: dùng sàn tài nguyên, dự trữ đầu vào nhiệm vụ/đột phá và tiêu chí vũ khí cùng hệ/tier đã biết. Không tự bán sản phẩm hoặc chấm sức mạnh chéo chỉ số. Chưa chạy lệnh chế tạo trên tài khoản thật.

## Nâng phòng động phủ Mini (2026-11-05)

- Chỉ GET và phân tích tĩnh `/assets/main-BNARi4Kn.js` và `/assets/i18n-B6UHPwZV.js`; không đọc `.env`, cookie hay state tài khoản thật. Component `fp` trong main render tab **Các phòng**, dùng `state.cave.rooms` (`{id, level, upgradeFinishAt}`) và gửi `cave.upgrade` `{roomId}` với guard version. UI game vô hiệu hóa mọi nút khi `rooms.find(room => room.upgradeFinishAt !== null)`; mô tả “Mỗi lúc chỉ nâng một phòng. Lần nâng tính theo đồng hồ máy chủ”. `cave.rush` `{roomId,maxStones}` chỉ dùng cho nút rút ngắn thời gian; Mini không gọi.
- Định nghĩa phòng nằm trong i18n chunk: `_r` tạo bảy record bằng `gr(id,maxLevel,baseStones,material,baseQty,baseMinutes)`, tên/hiệu ứng ở `hg` (`room.<id>.name/effect`). Giá trị: `tu_linh` 10/300/Hàn Tinh×4/10; `tinh_that` 12/250/Thiết khoáng×10/8; `dan_phong` 6/500/Linh thảo×20/15; `khi_phong` 5/500/Thiết khoáng×20/15; `linh_dien` 4/800/Linh thảo×30/20; `kho` 8/200/Thú bì×10/5; `tang_bao` 5/2.000/Thiết khoáng×30/30.
- `vr(room, level)` trả `{stones: Math.round(baseStones*1.7**level), items:[{itemId: material, qty: baseQty*(level+1)}], durationMs: baseMinutes*(level+1)*60000}`. Đây là công thức client; server vẫn là nơi quyết định chi phí/điều kiện cuối cùng.
- Planner `api/services/cave.py` chỉ trả action khi state đủ 7 phòng hợp lệ, không phòng nào đang nâng, đủ linh thạch sau dự trữ và đủ nguyên liệu sau sàn. Objective nhiệm vụ `{type:"cave_room", roomId, level}` của quest `active` được ưu tiên tuyệt đối; thiếu tài nguyên cho phòng đó thì chờ. Thứ tự `craft`/`cultivation`/`balanced` chỉ áp dụng khi không có objective động phủ.
- Metadata public `/meta` thêm `rooms` (id/tên/cấp tối đa/hiệu ứng), không chứa state tài khoản. Worker kiểm tra response: tăng `stateVersion`, đúng phòng, cấp +0/+1, `upgradeFinishAt` dương, không phòng khác đổi cấp, đúng một phòng active; sai/timeout thì ghi `uncertain` và dừng, không retry. Chưa nâng phòng trên tài khoản thật.

## Thông tin đăng nhập

Thông tin đăng nhập đã được cung cấp trong hội thoại và dùng cho đúng một lần thử login; không ghi lại giá trị đó trong tài liệu hay log. Nếu đây là mật khẩu đang dùng thật, nên đổi mật khẩu sau khi trao đổi trong chat.

## Đối chiếu bundle công khai để mở rộng auto (2026-11-04)

Người dùng yêu cầu đọc logic từ Chrome cache. File cache Chrome đang bị khóa; sau khi hỏi, người dùng chọn **tải bundle công khai**. Chỉ GET trang chủ và 3 file JS, không đăng nhập, không đọc cookie/session, không gửi lệnh game. Không thực thi bundle; dữ liệu literal được phân tích tĩnh bằng TypeScript AST rồi đối chiếu các chỗ gọi lệnh trong UI. Chỉ có logic phía client; điều kiện/phần thưởng cuối cùng vẫn do server xác thực.

| File tại `/assets/` | SHA-256 nội dung lưu UTF-8 |
|---|---|
| `main-Bmv0z3VX.js` | `9a1c2e7872a7359b4efb8646778f6bb100e50877d44c0a17afa0202035069c22` |
| `store-BU-hRQPl.js` | `ce52559fee916436fe73fb66f28989ddbacec6b159c673c36d65a003bba87286` |
| `i18n-DxMaxujG.js` | `1c1904461bc7e9141e43480b6ef5e53eff279ce92666c5db1be6404add3df770` |

Tất cả lệnh mới dùng `POST /api/cmd/{command}` như wrapper `rt` trong store; không dùng `/api/cm/cmd` của nhánh Cầu Ma.

| Lệnh | Payload quan sát được | Điều kiện UI / vị trí logic |
|---|---|---|
| `equip.best` | `{}` (guard version) | Túi đồ / nhân vật: mô tả game chọn mỗi ô tốt nhất, không thay đồ đang khóa và không đổi loại vũ khí. Không tự triển khai lại thuật toán chấm điểm. |
| `minor.trial` | `{}` | Component `Wp`: gate có `kind=trial` và `have<need`. Thua UI mô tả không mất gì. Auto còn yêu cầu đủ tu vi và chờ 10 phút/lần. |
| `sect.task.claim` | `{taskId}` | `state.sect.id`, `state.sectExtra.tasks`: chưa nhận, `current>=target`. Khác `sect.task` của nhánh Cầu Ma, có thể tiêu vật tư. |
| `season.task.claim` | `{taskId}` | `state.season.tasks`: chưa nhận, `current>=target`. Không tự đổi lễ phù. |
| `title.claim` | `{titleId}` | Component `Ed`, `state.ascend.titles`: `earned && !owned`; không tự gọi `title.equip`. |
| `pet.adopt` | `{petId}` | `state.pets`: `canAdopt && !owned`. Hợp khế có thể dùng khế ấn; mặc định tắt. |
| `npc.talk` | `{npcId}` | Component đạo hữu: `met`, `talked`; trò chuyện lần đầu ngày +8 thiện cảm. Auto bỏ qua thiện cảm đã 1000. |
| `npc.claim` | `{npcId,tierId}` | `met`, `affinity>=tier.need`, `!claimed.includes(tier.id)`. Bảng `Xi`: acquainted=100, close=250, trusted=450, confidant=700, bonded=1000. |
| `hunt.run` | `{petId}` | `character.level>=hunt.reqLevel`, `x2.hunt.runs>0`. UI mô tả thua hoàn lượt; auto vẫn chờ khoảng nghỉ để tránh spam. |

`game_rules.py` giữ 40 mục tiêu từ literal `da.pets`, nhóm `da.hunts`, bảng cấp `Fe`, và vòng mở rộng `Ia`: Trúc Cơ=16, Kết Đan=20, Nguyên Anh=24, Hóa Thần=28, Vấn Đỉnh=36, Khuy Niết=42, Toái Niết=50, Không Niết=54, Không Huyền=62, Không Kiếp=66. Mỗi nhóm 4 linh thú, ngưỡng khế ấn lần lượt 20/40/60/90/120/160/220/280/360/480. `huntPetId` phải chọn rõ; auto dừng khi đủ ngưỡng hoặc đã thu nhận, không săn khế ấn dư cho tiến hóa.

Đã thấy nhưng **chưa auto hóa**: `breakthrough.major`/`breakthrough.trial` (có thể mất vật liệu/tu vi), `npc.gift`, mua bán/đấu giá/quyên góp, đổi nhánh và các lệnh Cầu Ma. API state thực tế của các tính năng mới chưa được xác minh trên account thật; thiếu trường bắt buộc thì bỏ qua, không đoán là đã sẵn sàng. Không mở rộng allowlist sang các lệnh chưa triển khai/đối chiếu.
