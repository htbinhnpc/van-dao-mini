# Vấn Đạo — Game client knowledge skeleton

> **Mục đích:** bản skeleton tra cứu nhanh các hàm, endpoint và command của game gốc, phục vụ mini client.
>
> **Nguồn:** quét Chrome cache + đối chiếu bundle công khai ngày **2026-11-05**. Đây là **hành vi phía client**, không phải đặc tả chính thức của server. Server có thể trả thêm field, đổi điều kiện hoặc chặn lệnh mà client không biết.
>
> **Không thực hiện:** không đăng nhập, không đọc/ dùng cookie hay session, không gửi command làm thay đổi game state.

---

## 0. Nguồn dữ liệu và phạm vi

### 0.1 Chrome cache đã quét

Đường dẫn:

```text
C:\Users\ASUS\AppData\Local\Google\Chrome\User Data\Default\Cache\Cache_Data
```

Kết quả:

| Hạng mục | Ghi nhận |
|---|---|
| Index cache (`data_1`) | Chỉ thấy 2 URL thuộc game: `https://vandaonghichmenh.hongvan.net:60010/assets/store-BU-hRQPl.js` và một icon `assets/icons/skills/x2_skill_054_01.png?v=1`. |
| HTTP body của JS | Không còn trong `Cache_Data` (không tìm thấy nội dung bundle). |
| Code Cache (`Default\Code Cache\js`) | Có cached data cho nhiều asset game: `main-CTxUrJ_7.js`, `main-Bmv0z3VX.js`, `store-BU-hRQPl.js`, `store-BCoGv6eH.js`, `scene-n3fvB4Ln.js`, `scene-47oBnRR4.js`, `phaser-wjeKs800.js`, `phaser-BQPg0a7f.js`, `i18n-DxMaxujG.js`, `i18n-BWzMuw8w.js`. |
| Cookie | Có cookie `vd_sid` của domain game trong `Network\Cookies`, nhưng **không đọc/ không dùng giá trị**. |

Vì HTTP body không còn, tài liệu này dùng **GET công khai** các asset mà cache đã chỉ ra. Không thực thi bundle.

### 0.2 Asset đã đối chiếu

Trang chủ hiện tại (`GET /`) tham chiếu:

```html
<script type="module" src="/assets/main-Bmv0z3VX.js"></script>
<link rel="modulepreload" href="/assets/i18n-DxMaxujG.js">
<link rel="modulepreload" href="/assets/store-BU-hRQPl.js">
<link rel="stylesheet" href="/assets/main-Dl8iUS-g.css">
```

| File | Kích thước | SHA-256 |
|---|---:|---|
| `main-Bmv0z3VX.js` | 874.411 B | `9a1c2e7872a7359b4efb8646778f6bb100e50877d44c0a17afa0202035069c22` |
| `store-BU-hRQPl.js` | 2.748.438 B | `ce52559fee916436fe73fb66f28989ddbacec6b159c673c36d65a003bba87286` |
| `i18n-DxMaxujG.js` | 1.058.422 B | `1c1904461bc7e9141e43480b6ef5e53eff279ce92666c5db1be6404add3df770` |

### 0.3 File bổ trợ trong repo

| File | Nội dung |
|---|---|
| `api_knowledge.md` | Request/response đã quan sát thủ công, ghi chú login/settle. |
| `data/meta.json` | Static data: items, equipment, skills, pets, recipes, maps, quests… dùng để tra ID. |
| `static-rules.json` (bản tải công khai) | Bảng tĩnh: pets, hunts, recipes, dungeons, chapters, origins, skills, sets… |

---

## 1. Kiến trúc client

### 1.1 Module

| Module | Vai trò |
|---|---|
| `store-BU-hRQPl.js` | HTTP wrapper, API object, state store (Zustand-like), `applyState`, `cmd`, `settle`, auth/session. |
| `main-Bmv0z3VX.js` | Toàn bộ UI/game screens; nơi phát command và đọc `result`. |
| `i18n-DxMaxujG.js` | Text/error message; có map `err.<CODE>`. |
| `scene-n3fvB4Ln.js`, `phaser-wjeKs800.js` | Scene/Phaser runtime, không chứa API command. |

### 1.2 Hai “world”

| World | Dấu hiệu | Endpoint state | Endpoint command | Ghi chú |
|---|---|---|---|---|
| `tn` (Tiên Nghịch) | `world === 'tn'` | `GET /api/state` | `POST /api/cmd/{command}` | Có `expectedVersion`. |
| `cm` (Cầu Ma / Bộ Lạc) | `world === 'cm'`, `?world=cm` | `GET /api/cm/state` | `POST /api/cm/cmd/{command}` | **Không** gửi `expectedVersion`; nhiều trang thêm `?world=cm` vào GET. |

Helper `Au()` trả context:

```ts
{
  world: 'tn' | 'cm',
  cmd: (command, payload, opts?) => Promise,
  money: bigint,
  materials, equipment, myId, power, level,
  url: (path) => path           // cm: thêm ?world=cm
}
```

---

## 2. Hàm lõi

### 2.1 HTTP wrapper

| Hàm | Chữ ký / input | Mục đích | Output / lỗi |
|---|---|---|---|
| `Ye` | `Ye(method, path, body?, headers?, signal?)` | Gọi `fetch` JSON, `credentials: same-origin`, timeout 30 s, `content-type: application/json` nếu có body. | JSON response. Ném `Je` nếu lỗi mạng/ parse/ HTTP không ok/ `ok === false`. |
| `Ze` | `Ze(path, signal?)` | GET có **read queue** chống trùng request. | JSON hoặc `Je('NETWORK', 0)`. |
| `Qe` | `Qe()` | Sinh UUID v4 cho `idempotency-key`. | Chuỗi UUID. |
| `rt` | `rt(command, payload, expectedVersion)` | `POST /api/cmd/{command}` body `{payload, expectedVersion}`, header `idempotency-key`. | JSON; retry tối đa 2 lần chỉ với lỗi `NETWORK`, cùng key, backoff 800/1600 ms. |
| `it` | `it(command, payload)` | `POST /api/cm/cmd/{command}` body `{payload}`, header `idempotency-key`. | JSON; retry như `rt`, không có `expectedVersion`. |
| `at` | object API | Tập method API (xem §3). | — |

### 2.2 Error class và read queue

| Thành phần | Mô tả |
|---|---|
| `Je extends Error` | Có `code`, `status`, `details`, `stateVersion`. Code mặc định `INTERNAL`; lỗi mạng `NETWORK` status `0`. |
| `qe` (read queue) | `concurrency = 3`, `maxWaiting = 24`; dedupe request GET đang chạy theo key; quá tải ném `Read queue full`. |

`Ye` xử lý đặc biệt:

- Nếu response `errorCode === 'MAINTENANCE'` → dispatch event `vd:maintenance` với `details`.
- Nếu HTTP không ok hoặc JSON `ok === false` → ném `Je(errorCode ?? 'INTERNAL', status, details, stateVersion)`.
- Nếu parse JSON lỗi: `NETWORK` khi aborted/HTTP ≥ 500, ngược lại `INTERNAL`.

### 2.3 Store actions

| Action | Input | Mục đích | Ghi chú |
|---|---|---|---|
| `boot()` | — | Gọi `me()`, kiểm tra payment/maintenance/character, gọi `state()`, vào game và `settle(true)`. | Lỗi `NETWORK` → offline + retry sau 3 s. |
| `applyState(state, opts?)` | snapshot, `{silent?}` | Gán state mới, cập nhật `clockOffset = serverNow - Date.now()`, tính loot mới từ chênh lệch `wallet`/`materials`/`equipment`. | Bỏ qua snapshot cũ hơn theo `stateVersion`/`serverNow`. |
| `cmd(command, payload, opts?)` | command, payload, `{guard?, quiet?}` | Gọi `at.command`, `applyState(res.state)`, hiện toast lỗi; `guard` mới gửi `stateVersion`. | `VERSION_CONFLICT` → tự GET state mới. Trả `null` khi lỗi. |
| `settle(silent?)` | boolean | Gọi `cmd('settle', {})`; hiện toast lên tầng, nhặt trang bị, craft xong. | Có cờ chống chạy song song. |
| `setSettings(patch)` | object | Merge setting UI vào localStorage `vd.settings.v1`. | Không gửi server. |
| `logout()` | — | Gọi `at.logout()`, reset phase auth/state. | — |
| `go(page)`, `openEvent(id)`, `goFocus(focus)`, `showSources(item)`, `freshFocus(page)` | — | Điều hướng UI/nội bộ. | Không phải command server. |
| `holdLoot(bool)`, `pruneLoot()` | — | Giữ/ dọn loot hiển thị. | — |
| `toast(kind, text)`, `dismissToast(id)` | — | Hàng đợi toast tối đa 4 cái. | — |

### 2.4 Helper UI đáng chú ý

| Hàm / component | Mục đích |
|---|---|
| `Au()` | Trả context world hiện tại + hàm `cmd` + `url` + nhãn tiền tệ. |
| `ju()` | Context túi đồ/vault theo world. |
| `Vg()` | Mở modal battle: gọi `N.battle(result.battleId)` rồi hiển thị log. |
| `W_(result, fallbackText)` | Đọc `result.objective` và hiển thị “chưa đạt mục tiêu”. |
| `Qd(path)` | Hook GET + cache + reload + loading/error. |
| `tf(channel)` | Poll chat bằng `GET /api/chat?channel=...&after=...`. |
| `d_(cmState)` | Chuyển state Cầu Ma thành context `world: 'cm'`. |

---

## 3. Endpoint catalog

### 3.1 API object `at`

| Method | Endpoint | Body / query | Response client đọc |
|---|---|---|---|
| `me()` | `GET /api/auth/me` | — | `{ user, hasCharacter, paymentRequired, maintenance }` |
| `register(u,p,remember=true)` | `POST /api/auth/register` | `{username,password,remember}` | `{recoveryCode?}` |
| `login(u,p,newPassword?,remember=true)` | `POST /api/auth/login` | `{username,password,remember,newPassword?}` | `{recoveryCode?, user?}` |
| `recover(u,code,newPassword,remember=true)` | `POST /api/auth/recover` | `{username,code,newPassword,remember}` | `{recoveryCode?}` |
| `newRecoveryCode(password)` | `POST /api/auth/recovery-code` | `{password}` | `{recoveryCode}` |
| `logout()` | `POST /api/auth/logout` | `{}` | — |
| `sessions()` | `GET /api/auth/sessions` | — | `{sessions}` |
| `revokeSession(id)` | `POST /api/auth/sessions/revoke` | `{sessionId}` | — |
| `state()` | `GET /api/state` | — | `{state}` |
| `cmState()` | `GET /api/cm/state` | — | `{state}` |
| `cmGw()` | `GET /api/cm/gw` | — | GW state |
| `cmTl()` | `GET /api/cm/tl` | — | TL state |
| `command(cmd,payload,expectedVersion?)` | `POST /api/cmd/{cmd}` | `{payload,expectedVersion}` + `idempotency-key` | `{ok,state,stateVersion?,result?,settle?}` |
| `cmCommand(cmd,payload)` | `POST /api/cm/cmd/{cmd}` | `{payload}` + `idempotency-key` | `{ok,state,result?}` |
| `battle(id,signal?)` | `GET /api/battles/{id}` | — | `{battle}` |
| `battleRetry(id,signal?)` | `GET /api/battles/{id}` | — | Retry 4 lần với delay 1/3/6/10 s. |
| `online()` | `GET /api/online` | — | `{online}` |
| `discordLink()` | `GET /api/discord/link` | — | Link state |
| `discordCode()` | `POST /api/discord/link/code` | `{}` | Code |
| `discordUnlink()` | `POST /api/discord/unlink` | `{}` | — |
| `paymentFee()` | `GET /api/payment/fee` | — | `{fee,description,discordInviteUrl}` |
| `paymentStatus()` | `GET /api/payment/registration` | — | `{payment}` |
| `paymentStart()` | `POST /api/payment/registration` | `{}` | `{payment}` |
| `createCharacter(payload)` | `POST /api/character` | `{name,gender,originId,attrs,portrait,tint}` | `{state}` |
| `get(path,signal?)` | GET bất kỳ | — | JSON |
| `post(path,body)` | POST bất kỳ | body | JSON |

### 3.2 Endpoint đọc khác

| Method | Endpoint | Query / body | Response client đọc |
|---|---|---|---|
| GET | `/api/characters` | — | `{characters, max}` |
| POST | `/api/characters/select` | `{characterId}` | — |
| GET | `/api/maintenance` | — | `{ok, serverNow, maintenance}` |
| GET | `/api/announcements` | — | `{announcements, maintenance}` |
| GET | `/api/events` | SSE `withCredentials` | event `announce`, `chat`, `mail` |
| GET | `/api/online/events` | SSE | event `online` (`{online}`) |
| GET | `/api/payment/events` | SSE | event `fee` |
| GET | `/api/breakthrough/odds` | — | `{odds}` |
| GET | `/api/mail` | — | `{mails}` |
| GET | `/api/market` | `kind,q,rarity,slot,maxPrice,sort` hoặc `mine=1`, `bought=1` | `{listings}` |
| GET | `/api/auctions` | `kind` hoặc `mine=1` | `{list}` |
| GET | `/api/arena` | `pick` | `{arena}` |
| GET | `/api/friends` | — | `{friends}` |
| GET | `/api/chat` | `channel`, `after` | `{messages}` |
| GET | `/api/guild` | — | `{guild}` |
| GET | `/api/guilds` | — | Danh sách bang |
| GET | `/api/guildquests` | — | `{quests}` |
| GET | `/api/guildwar` | — | `{war}` |
| GET | `/api/guild-emblem/{id}` | `v` | ảnh |
| GET | `/api/worldboss` | `scope` | `{boss}` |
| GET | `/api/ranking` | `type`, `group` | Bảng xếp hạng |
| GET | `/api/cm/ranking` | `type`, `realm` | Bảng xếp hạng Cầu Ma |
| GET | `/api/vault` | — | `{vault}` |
| GET | `/api/gw2` | — | `{gw2}` |
| GET | `/api/gw2/battle/{id}` | — | `{battle}` |
| GET | `/api/gw2/match/{id}` | — | `{match}` |
| GET | `/api/profile/{id}` | — | Profile |
| GET | `/api/x3/ranking` | `event` | Bảng xếp hạng sự kiện |
| GET | `/api/admin/overview` | — | Admin |
| GET | `/api/admin/economy` | `hours=24` | Admin |
| GET | `/api/admin/audit` | — | Admin |
| GET | `/api/admin/reports` | — | Admin |
| GET | `/api/admin/character` | `name` | Admin |
| POST | `/api/admin/ban` | payload | Admin |
| POST | `/api/admin/mail` | payload | Admin |

### 3.3 Envelope

**Thành công (quan sát từ client):**

```json
{
  "ok": true,
  "state": { "...": "snapshot mới" },
  "stateVersion": 1119,
  "result": { "...": "tùy lệnh" }
}
```

- `state` được client dùng cho **mọi** command thành công (`applyState(res.state)`).
- `result` là object riêng của lệnh (trận đấu, phần thưởng, outcome…).
- `settle` là object riêng của lệnh `settle`.
- Client chỉ coi lỗi khi HTTP không ok hoặc `ok === false`; không kiểm tra schema.

**Lỗi:**

```json
{
  "ok": false,
  "errorCode": "INSUFFICIENT_RESOURCES",
  "message": "...",
  "details": { "...": "tùy lỗi" },
  "stateVersion": 1119
}
```

### 3.4 Error code thường gặp

| Code | Nghĩa |
|---|---|
| `NETWORK` | Mất mạng/timeout; client có retry giới hạn. |
| `UNAUTHENTICATED` | Session hết hạn → về màn đăng nhập. |
| `FORBIDDEN` | Không có quyền. |
| `INVALID_INPUT` | Payload sai. |
| `INVALID_CREDENTIALS` | Sai tài khoản/mật khẩu/mã khôi phục. |
| `PASSWORD_CHANGE_REQUIRED` | Admin buộc đổi mật khẩu. |
| `VERSION_CONFLICT` | State đã đổi ở tab/thiết bị khác; client tự GET state mới. |
| `INSUFFICIENT_RESOURCES` | Thiếu tài nguyên/tiền/vật liệu. |
| `REQUIREMENT_NOT_MET` | Chưa đủ điều kiện. |
| `LEVEL_TOO_LOW` | Cảnh giới/cấp quá thấp. |
| `REGION_LOCKED` | Vùng chưa mở. |
| `BAG_FULL` | Túi đầy. |
| `DAILY_LIMIT` / `WEEKLY_LIMIT` | Hết lượt ngày/tuần. |
| `NOT_READY` | Chưa tới lúc/ hồi chiêu. |
| `ALREADY_CLAIMED` | Đã nhận rồi. |
| `QUEST_NOT_ACTIVE` / `QUEST_NOT_COMPLETE` | Nhiệm vụ chưa tới lượt/ chưa xong. |
| `SKILL_NOT_LEARNED` / `SKILL_ALREADY_LEARNED` / `DUPLICATE_SKILL` / `SLOT_LOCKED` | Lỗi kỹ năng. |
| `CRAFT_QUEUE_FULL` / `JOB_NOT_FOUND` / `JOB_NOT_CANCELLABLE` | Lỗi lò luyện. |
| `SECT_REQUIRED` / `ALREADY_IN_SECT` / `SECT_COOLDOWN` / `RANK_TOO_LOW` | Lỗi tông môn. |
| `GUILD_REQUIRED` / `ALREADY_IN_GUILD` | Lỗi bang hội. |
| `MAINTENANCE` | Bảo trì; client dispatch `vd:maintenance`. |
| `WRONG_WORLD` | State thuộc world khác; client reload. |
| `FEATURE_UNAVAILABLE` | Tính năng chưa mở. |
| `AT_CONTENT_CAP` | Chạm giới hạn nội dung phiên bản. |
| `INTERNAL` | Lỗi server không xác định. |

---

## 4. Command catalog

> Quy ước:
> - **Payload** là object gửi trong `payload` (không phải body ngoài).
> - **Response** chỉ ghi field client **thực sự đọc thêm** ngoài `state`.
> - `guard` = client gửi kèm `expectedVersion`.
> - Dấu `(?)` = payload/response suy ra từ call site hoặc tên, chưa thấy đủ nhánh xử lý.

### 4.1 Lõi / vận hành

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `settle` | `{}` | Kết toán chu kỳ/offline: tu vi, loot, craft, lên tầng. | `settle.{validMs,layerUps,equipment,craftsCompleted}` |
| `settings.set` | `{autoMinor?, autoSalvageTier?, ...}` | Lưu cài đặt nhân vật (tự lên tiểu tầng, tự xử lý đồ rơi). | — |
| `activity.set` | world `tn`: `{type:'farm', targetId}` hoặc `{type}`; world `cm`: `{activity}` | Đổi hoạt động chính (farm/gather/cultivate/…) và điểm săn. | `result.win` (farm) |
| `guide.set` | `{done: boolean}` | Đánh dấu đã đọc/ bỏ qua hướng dẫn nhập môn. | — |
| `character.rename` | `{name}` | Đổi đạo danh. | — |
| `attrs.reset` | `{attrs}` | Phân bổ lại điểm thuộc tính. | — |
| `look.set` | `{tint}` hoặc `{portrait}` | Đổi màu y phục/ chân dung. | — |
| `profile.showBond` | `{show: boolean}` | Hiện/ ẩn quan hệ đạo lữ trên profile. | — |
| `legacy.view` | `{}` | Xem di sản/ ký ức ở lại Tiên Nghịch. | — |
| `timer.rush` | `{...target, maxCoins}`; `target` là `{plot}`, `{roomId}`, `{habitatId}`, `{what:'job',jobId}`, `{what:'forge'}` | Bỏ qua thời gian chờ bằng thạch tệ (nông trại, động phủ, lò luyện, lò rèn). | `result.coins` (số đã tiêu) |

### 4.2 Tu luyện / đột phá / nội tại

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `breakthrough.minor` | `{}` | Lên tiểu tầng khi đủ tu vi. | — |
| `breakthrough.major` | `{insurance?, topUp?}` | Đột phá đại cảnh giới (có thể mua bảo hiểm/ top-up). | — |
| `breakthrough.trial` | `{}` | Khiêu chiến thử thách đột phá. | `result` (battle/win) |
| `minor.trial` | `{}` | Thử thách mốc tiểu cảnh giới. | `result` |
| `ascend.trial` | `{}` | Thử thăng linh. | `result.objective.{met,text}` |
| `tribulation.fight` | `{trialId, originId?, responses?, phase2Preset?, dropSkill?}` | Độ kiếp. | `result` (battle, won, points) |
| `body.refine` | `{axis}` | Luyện thể theo hướng. | — |
| `bone.temper` | `{}` | Tôi cốt. | `result` |
| `immortal.refine` | `{qty}` | Luyện ngọc (1/10/…). | — |
| `immortal.train` | `{form}` | Luyện hình thái. | — |
| `immortal.setForm` | `{form}` hoặc `{form:null}` | Vận/ thu hình thái. | — |
| `meridian.open` | `{}` | Khai mở hệ kinh mạch. | — |
| `meridian.unlock` | `{meridianId}` | Đả thông một kinh mạch. | — |
| `meridian.attune` | `{meridianIds: string[]}` | Luyện/ điều chỉnh nhiều kinh mạch. | — |
| `meridian.core` | `{core}` | Mở/ nâng lõi kinh mạch. | — |
| `medicine.use` | `{itemId, withQingChen?}` | Dùng thuốc huyết tuyến. | `result.{progress,veins}` |
| `dao.research` | `{daoId}` | Lĩnh ngộ đạo. | — |
| `dao.setMain` | `{daoId}` | Đặt đạo chính. | — |
| `dao.trial` | `{}` | Thử đạo. | `result` |
| `essence.research` | `{essenceId}` | Lĩnh ngộ bản nguyên. | — |
| `essence.set` | `{main, secondary}` | Đặt bản nguyên chính/ phụ. | — |
| `manvan.research` | `{nodeId}` | Nghiên cứu Man Văn. | — |
| `manvan.set` | `{memories, branch}` | Chọn ký ức/ nhánh Man Văn. | `result.wrong` |
| `manvan.rebranch` | `{branch, memories}` | Đổi nhánh Man Văn. | — |
| `research.branch` | `{branch}` | Chọn nhánh nghiên cứu. | — |
| `research.node` | `{nodeId}` | Mở nút nghiên cứu. | — |
| `research.reset` | `{}` | Đặt lại nút chưa dùng. | — |
| `tech.learn` | `{techId}` (guard) | Học tâm pháp tông môn. | — |
| `tech.set` | `{main, subs: string[]}` (guard) | Đặt tâm pháp chính/ phụ. | — |
| `tech.upgrade` | `{techId}` (guard) | Nâng cấp tâm pháp. | — |
| `ancient.puppet` | `{}` | Đánh khôi lỗi Cổ Thần. | `result.{battle,won,tierUp,tier}` |
| `ancient.resonate` | `{picks}` | Cộng hưởng sao. | — |
| `ancient.runes` | `{runeIds: string[]}` | Lắp/ tháo rune. | — |
| `ancient.temper` | `{}` | Tôi luyện Cổ Thần. | — |
| `ancient.train` | `{on: boolean}` | Bật/ tắt luyện thể Cổ Thần. | — |
| `ancient.trial` | `{chapterId, ...}` | Thử thách chương Cổ Thần. | `result.{battle,won,first,practice,shard,kiepPassed,lostTemper}` |
| `demonic.calm` | `{}` | Tĩnh tâm giảm ma chướng. | — |
| `demonic.join` | `{branch}` | Chọn nhánh ma. | — |
| `demonic.switch` | `{path}` hoặc `{branch}` | Đổi đường tu ma/ chính. | — |
| `demonic.tier` | `{branch}` | Mở/ nâng bậc ma. | — |
| `demonic.trial` | `{}` | Thử thách ma. | `result` |
| `secret.enter` | `{realmId}` | Vào Hóa Phàm bí cảnh. | — |
| `secret.step` | `{action, path?}` | Đi bước trong bí cảnh. | `result.{spring,won,cleared,left,kept}` |
| `mortal.begin` | `{lineId}` | Bắt đầu một đời phàm nhân. | — |
| `mortal.choose` | `{lineId, choice}` | Chọn lựa. | — |
| `mortal.rechoose` | `{lineId, step, choice}` | Chọn lại. | — |
| `journey.enter` | `{}` | Mở cổng hành trình. | — |
| `journey.return` | `{}` | Trở về Tiên Nghịch. | `result.outcome` |
| `control.step` | `{step}` | Điều khiển khí. | `result.outcome` |
| `chain.start` | `{}` | Bắt đầu vượt xích. | — |
| `chain.act` | `{action}` | Hành động vượt xích. | `result.{done,fell,log,stage}` |
| `gate.attempt` | `{gateId}` | Vượt cửa Chứng Đạo. | `result.{battle,passed,shards,insight}` |
| `encounter.fight` | `{encounterId}` | Đánh encounter. | `result.{battleId,win}` |
| `encounter.resolve` | `{encounterId, choice}` | Chọn cách xử lý encounter. | — |
| `practice.fight` | `{encounterId}` | Luyện tập encounter (không thưởng). | `result.{battleId,win}` |
| `training.dummy` | `{preset, kind, seconds}` | Đánh bù nhìn thử DPS. | — |
| `tower.climb` | `{}` | Leo Đông Hoang Tháp. | `result` |
| `tl.fight` | `{}` | Đánh Thiên Lam. | `result` |
| `survey.run` | `{surveyId}` | Khảo chứng vùng. | `result` |
| `x3.trial` | `{n, preset}` | Thử luyện sự kiện. | `result` |
| `x3.ladder` | `{floor, mode}` | Vượt bậc thang. | `result` |
| `x3.mirror` | `{choices, mode}` | Vân Hải Cổ Độ. | `result` |
| `x3.alchemy` | `{exam?, mode}` | Hộ dược/ thi đan. | `result` |
| `x3.cloud` | `{mode}` | Vân Tông Đan Viện. | `result` |
| `x3.story` | `{n, branch, preset}` | Cốt truyện sự kiện. | `result` |

### 4.3 Chiến đấu / boss / PvP

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `boss.fight` | `{bossId, hard?}` | Đánh boss vùng/ boss bản đồ. | `result` (battle/win) |
| `worldboss.attack` | `{scope}` | Đánh boss thế giới. | `result.{battle,damage,killed,counted}` |
| `worldboss.claim` | `{scope, milestoneId, originId?}` | Nhận mốc boss thế giới. | — |
| `arena.fight` | `{defenderId, ranked}` | Đấu trường. | `result.{battle,won,ratingDelta,rating,tokens}` |
| `arena.buy` | `{shopId}` | Đổi shop đấu trường. | — |
| `guildwar.attack` | `{nodeId}` | Đánh cứ điểm tông môn chiến. | `result.{battle,won,score,defenderName}` |
| `guildwar.garrison` | `{nodeId}` hoặc `{nodeId:null}` | Đóng/ rút quân. | — |
| `gw.attack` | `nodeId` | Chiến bộ lạc: đánh cứ điểm. | `result.captured` |
| `gw.defend` | `nodeId` | Đặt thủ. | — |
| `gw.scout` | `nodeId` | Trinh sát. | — |
| `gw.repair` | `nodeId` | Sửa cứ điểm. | — |
| `gw.register` | `{}` | Đăng ký chiến. | — |
| `gw.shop` | `{offerId}` | Đổi shop chiến. | — |
| `gw2.register` | `{}` | Đăng ký Chiến Tuyến. | — |
| `gw2.cancel` | `{}` | Hủy đăng ký Chiến Tuyến. | — |
| `gw2.lineup` | `{order}` | Lưu thứ tự đội hình. | — |

### 4.4 Trang bị / vật phẩm / chế tạo

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `equip.best` | `{}` (guard) | Tự mặc trang bị tốt nhất từng ô; không đổi loại vũ khí, không thay đồ khóa. | — |
| `equip` | `{itemId}` (guard) | Mặc một món trang bị trong túi. | — |
| `unequip` | `{itemId}` (guard) | Tháo trang bị đang mặc về túi. | — |
| `item.use` | `{itemId, qty}` | Dùng vật phẩm. | — |
| `item.dispose` | `{itemIds: string[], mode: 'sell'\|'salvage'}` (guard) | Bán/ phân giải nhiều món; UI giới hạn 60 ID/lệnh. | — (client không đọc `result`) |
| `item.enhance` | `{itemId}` (guard) | Cường hóa trang bị. | — |
| `item.favorite` | `{itemId, favorite}` | Bật/ tắt yêu thích. | — |
| `item.lock` | `{itemId, locked}` | Khóa/ mở khóa. | — |
| `item.transfer` | `{fromId, toId}` (guard) | Chuyển vật phẩm. | — |
| `craft.start` | `{recipeId, count?}` | Bắt đầu luyện đan; UI cho `count` tối đa 8. | — |
| `craft.cancel` | `{jobId}` | Hủy mẻ. | — |
| `craft.rush` | `{jobId, maxStones}` | Rút ngắn mẻ bằng linh thạch. | `result.stones` |
| `gear.buy` | `{slot}` | Mua/ rèn trang bị theo ô. | — |
| `v3.gear.craft` | `{gearId}` | Rèn trang bị. | — |
| `v3.art.forge` | `{artId}` | Rèn pháp bảo. | — |
| `v3.art.upgrade` | `{artId, branch?}` | Nâng pháp bảo. | — |
| `v3.art.equip` | `{artId}` hoặc `{artId:null}` | Đeo/ bỏ pháp bảo. | — |
| `v3.manual.learn` | `{manualId}` | Học/ nâng công pháp. | — |
| `v3.manual.choose` | `{manualId, choice}` | Chọn hướng công pháp. | — |
| `v3.manual.slot` | `{main, aux}` | Lưu cách xếp công pháp. | — |
| `treasure.bind` | `{treasureId}` | Kết bản mệnh bảo vật. | — |
| `treasure.branch` | `{branch}` | Chọn nhánh bảo vật. | — |
| `treasure.nurture` | `{}` | Nuôi bảo vật. | — |
| `x2t.forge` | `{treasureId}` | Rèn bảo vật. | — |
| `x2t.ascend` | `{treasureId}` | Thăng bảo vật. | — |
| `x2t.exchange` | `{treasureId, qty}` | Đổi mảnh bảo vật. | — |
| `skill.learn` | `{skillId}` | Học kỹ năng. | — |
| `skills.set` | `{loadout, assist, passives, variants?, preset?}` | Lưu bộ kỹ năng. | — |
| `loadout.set` | `{rules, passives, preset}` (guard) | Lưu luật/ kỹ năng farm. | — |
| `rules.set` | `{preset, ...rules?}` | Lưu preset luật auto trong trận. | — |
| `preset.clear` | `{preset}` | Xóa cấu hình riêng của preset. | — |
| `stance.set` | `{stance}` | Đổi thế đứng. | — |
| `artifact.set` | `{skillId}` hoặc `{skillId:null}` | Gán/ bỏ kỹ năng artifact. | — |
| `title.claim` | `{titleId}` | Nhận danh hiệu. | — |
| `title.equip` | `{titleId}` hoặc `{titleId:null}` | Mang/ bỏ danh hiệu. | — |
| `skin.claim` | `{skinId}` | Nhận skin. | — |
| `skin.equip` | `{skinId}` hoặc `{skinId:null}` | Mặc/ bỏ skin. | — |
| `skin.set` | `{skinId}` hoặc `{skinId:null}` | Đặt skin. | — |

### 4.5 Nông trại / sản xuất

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `field.plant` | `{plot, seedId}` | Gieo hạt. | — |
| `field.harvest` | `{plot}` | Thu hoạch ô. | — |
| `field.rush` | `{plot, maxStones}` | Rút ngắn thời gian ô. | — |
| `habitat.open` | `{habitatId}` | Mở ô sinh cảnh. | — |
| `habitat.rush` | `{habitatId, maxStones}` | Rút ngắn sinh cảnh. | — |
| `cave.rush` | `{roomId, maxStones}` | Rút ngắn động phủ. | `result.stones` |
| `cave.upgrade` | `{roomId}` | Nâng phòng động phủ. | — |
| `v2.garden` | `{action:'plant'\|'harvest', slot}` | Chăm vườn thuốc. | — |
| `v2.cure` | `{action:'start'\|'collect', slot}` | Chăm thuốc. | — |
| `v2.flower` | `{}` | Chăm hoa viên. | — |
| `v3.area.farm` | `{areaId, option?}` hoặc `{areaId:null}` | Farm khu vực/ dừng farm. | — |
| `v3.area.unlock` | `{areaId}` | Mở khu vực. | — |
| `camp.upgrade` | `{}` | Nâng cấp doanh trại bộ lạc (Cầu Ma, mở ở chương 4). | — |

### 4.6 Nhiệm vụ / thưởng / sự kiện

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `quest.claim` | `{questId}` | Nhận thưởng nhiệm vụ. | — |
| `daily.claim` | `{taskId}` | Nhận thưởng ngày. | — |
| `weekly.claim` | `{taskId}` | Nhận thưởng tuần. | — |
| `achievement.claim` | `{achievementId}` | Nhận thành tựu. | — |
| `season.task.claim` | `{taskId}` | Nhận nhiệm vụ mùa. | — |
| `sect.task.claim` | `{taskId}` | Nhận nhiệm vụ tông môn. | — |
| `guild.quest.claim` | `{questId}` | Nhận nhiệm vụ bang. | — |
| `chapter.claim` | `{chapterId}` | Nhận thưởng chương. | — |
| `chapter.choose` | `{chapterId, choice}` | Chọn lựa chương. | — |
| `chapter.step` | `{step, branch?}` (chương x2) hoặc `{chapterId, stepId}` (chương cm) | Đi bước chương. | `result.{battle,done}` (bước chiến đấu) |
| `chapter.fight` | `{chapterId, stepId, picks?}` | Đánh trận chương. | `result.{win,lost,matsLost,wrong}` |
| `chapter.break` | `{chapterId, stepId}` | Phá/ vượt bước chương. | `result.{win,lost,matsLost}` |
| `story.step` | `{chapterId, step, branch?}` | Bước cốt truyện. | — |
| `story.recall` | `{chapterId}` | Hồi tưởng chương. | — |
| `ch1.choose` | `{choice}` | Chọn lựa chương 1. | — |
| `event.stage` | `{stageId}` | Đánh stage sự kiện. | `result` |
| `event.daily` | `{}` | Làm nhiệm vụ ngày sự kiện. | — |
| `event.exchange` | `{}` | Đổi thưởng sự kiện. | — |
| `ev.draw` | `{eventId, count, useTickets}` | Quay sự kiện. | `result` |
| `ev.fight` | `{eventId, kind, n}` | Đánh sự kiện. | `result` |
| `ev.shop` | `{eventId, skinId}` | Đổi shop sự kiện. | — |
| `ev.tickets` | `{eventId}` | Nhận vé sự kiện. | — |
| `evidence.claim` | `{evidenceId}` | Chọn mệnh đề Mệnh Cách. | — |
| `mail.claim` | `{mailId}` | Nhận thư. | — |
| `mail.claimAll` | `{}` | Nhận tất cả thư có quà. | — |
| `mail.delete` | `{mailId}` | Xóa thư. | — |
| `giftcode.redeem` | `{code}` | Nhập giftcode. | `result` |
| `origin.weekly` | `{originId}` | Nhận thưởng tuần nguyên. | — |
| `x2.daily.claim` | `{}` | Nhận thưởng ngày mở rộng 2. | — |
| `x3.daily` | `{}` | Nhận thưởng ngày sự kiện x3. | — |
| `x3.wheel.mission` | `{missionId}` | Nhận nhiệm vụ vòng quay. | — |
| `x3.wheel.draw` | `{count, maxStones, useTickets}` | Quay vòng x3. | `result` |
| `x3.wheel.exchange` | `{skinId}` | Đổi skin vòng quay. | — |
| `x3.lwheel.draw` | `{wheelId, count, maxStones}` | Quay vòng may mắn. | `result` |
| `x3.shop` | `{eventId, itemId}` | Đổi shop sự kiện x3. | — |

### 4.7 Xã hội / bang hội / chợ

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `friend.request` | `{name}` | Gửi lời kết bạn. | — |
| `friend.accept` | `{characterId}` | Chấp nhận kết bạn. | — |
| `friend.remove` | `{characterId}` | Xóa bạn. | — |
| `block.add` | `{characterId}` | Chặn. | — |
| `block.remove` | `{characterId}` | Bỏ chặn. | — |
| `chat.send` | `{channel, body, equipmentId?}` | Gửi chat. | — |
| `chat.report` | `{messageId, reason}` | Báo cáo chat. | — |
| `bond.invite` | `{name, kind}` | Mời đạo lữ/ kết nghĩa. | — |
| `bond.cancel` | `{bondId}` | Hủy lời mời. | — |
| `bond.sign` | `{bondId}` | Ký khế. | — |
| `bond.end` | `{bondId}` | Chấm dứt quan hệ. | — |
| `bond.share` | `{on: boolean}` | Bật/ tắt chia sẻ bóng. | — |
| `bond.assist` | `{on: boolean}` | Bật/ tắt trợ chiến. | — |
| `npc.talk` | `{npcId}` | Nói chuyện NPC. | `result` |
| `npc.gift` | `{npcId, itemId, qty}` (guard) | Tặng quà. | — |
| `npc.claim` | `{npcId, tierId}` | Nhận mốc thiện cảm. | — |
| `npc.heart` | `{npcId, choice:'friend'\|'romance'}` | Chọn hướng quan hệ. | — |
| `npc.marry` | `{npcId}` | Kết/ chấm dứt đạo lữ. | — |
| `npc.pin` | `{npcId, on: boolean}` | Ghim/ bỏ ghim NPC. | — |
| `npc.quest` | `{questId, choice}` | Làm nhiệm vụ NPC. | `result` |
| `npc.errand` | `{npcId}` | Sai vặt NPC. | `result` |
| `guild.create` | `{name}` | Tạo bang. | — |
| `guild.apply` | `{guildId}` | Xin vào bang. | — |
| `guild.review` | `{characterId, accept}` | Duyệt đơn. | — |
| `guild.kick` | `{characterId}` | Kick thành viên. | — |
| `guild.setRole` | `{characterId, role}` | Đổi chức vụ. | — |
| `guild.transfer` | `{characterId}` | Nhường bang chủ. | — |
| `guild.leave` | `{}` | Rời bang. | — |
| `guild.rename` | `{name}` | Đổi tên bang. | — |
| `guild.notice` | `{notice}` | Sửa thông báo. | — |
| `guild.emblem` | `{image}` | Đổi/ gỡ huy hiệu. | — |
| `guild.checkin` | `{}` | Điểm danh. | — |
| `guild.donate` | `{stones}` | Đóng góp quỹ. | — |
| `guild.upgrade` | `{}` | Nâng cấp bang. | — |
| `guild.research` | `{techId}` | Nghiên cứu bang. | — |
| `guild.skill` | `{skillId}` | Học/ nâng kỹ năng bang. | — |
| `guild.shop` | `{shopId}` | Đổi shop bang. | — |
| `market.list` | `{kind, itemId?, equipmentId?, qty?, price}` | Đăng bán chợ. | — |
| `market.buy` | `{listingId}` | Mua chợ. | — |
| `market.cancel` | `{listingId}` | Hủy niêm yết. | — |
| `auction.list` | `{kind, itemId?, equipmentId?, qty?, startPrice, hours}` | Đăng đấu giá. | — |
| `auction.bid` | `{auctionId, amount}` | Đặt giá. | — |
| `auction.cancel` | `{auctionId}` | Hủy đấu giá. | — |
| `shop.buy` | `{offerId}` | Mua shop thường. | — |
| `sect.join` | `{sectId}` | Bái nhập tông môn. | — |
| `sect.leave` | `{}` | Rời tông môn. | — |
| `sect.donate` | `{itemId, qty}` | Cống hiến vật phẩm. | `result.gain` |
| `sect.task` | `{taskId}` | Làm nhiệm vụ tông môn. | — |
| `sect.buy` | `{shopId}` | Đổi shop tông môn. | — |
| `season.buy` | `{shopId}` | Đổi shop mùa. | — |
| `x2.shop.buy` | `{itemId, qty, currency}` | Mua shop mở rộng 2. | — |
| `x2.manual.get` | `{manualId}` | Nhận công pháp miễn phí. | — |
| `x2.skill.learn` | `{skillId}` | Học kỹ năng mở rộng 2. | — |
| `vault.deposit` | `{equipmentId}` hoặc `{itemId, qty}` | Gửi vào kho chung. | — |
| `vault.withdraw` | `{equipmentId}` hoặc `{itemId, qty}` | Lấy từ kho chung. | — |
| `vault.depositMany` | `{equipmentIds: string[], items: {itemId}[]}` | Gửi nhiều món. | `result.{equipment,items,skipped}` (số lượng) |
| `vault.withdrawMany` | `{equipmentIds: string[], items: {itemId}[]}` | Lấy nhiều món. | `result.{equipment,items,skipped}` |

### 4.8 Linh thú / khôi lỗi / đồng hành / quan hệ

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `hunt.run` | `{petId}` | Đi săn khế ấn. | `result` |
| `pet.adopt` | `{petId}` | Thu nhận linh thú. | — |
| `pet.condition` | `{petId}` | Xem/ chuẩn bị điều kiện tiến hóa. | `result` |
| `pet.evolve` | `{petId}` | Tiến hóa. | — |
| `pet.feed` | `{petId}` | Nuôi/ tăng thân thiết. | — |
| `pet.set` | `{petId}` hoặc `{petId:null}` | Xuất chiến/ cho nghỉ. | — |
| `pet.trial` | `{petId}` | Thử thách linh thú. | `result.{battle,passed,petAlive}` |
| `puppet.craft` | `{puppetId}` | Luyện khôi lỗi. | — |
| `puppet.set` | `{puppetId}` hoặc `{puppetId:null}` | Xuất chiến/ cho nghỉ. | — |
| `puppet.skill` | `{puppetId}` | Nâng kỹ năng khôi lỗi. | — |
| `puppet.upgrade` | `{puppetId}` | Nâng cấp khôi lỗi. | — |
| `v3.comp.quest` | `{compId}` | Nhiệm vụ phối hợp đồng hành. | `result` |
| `v3.comp.set` | `{compId, mode:'assist'\|'companion'}` | Đặt đồng hành trợ chiến. | — |
| `assist.set` | `{npcId: string \| 'bond' \| null}` | Chọn NPC/ đạo lữ làm trợ chiến; `null` để bỏ. | — |
| `v2.rel.talk` | `{relId}` | Nói chuyện quan hệ. | `result` |
| `v2.rel.gift` | `{relId, itemId, qty}` | Tặng quà. | `result` |
| `v2.rel.quest` | `{relId}` | Nhiệm vụ quan hệ. | — |
| `v2.rel.claim` | `{relId, tierId}` | Nhận mốc quan hệ. | — |

### 4.9 Mở rộng 2 / 3 và sự kiện đặc biệt

| Command | Payload | Mục đích | Response thêm |
|---|---|---|---|
| `clone.set` | `{clone}` | Chọn clone/ phân thân. | — |
| `domain.attune` | `{domainId, branch:'atk'\|'def'}` | Lĩnh ngộ domain. | — |
| `domain.set` | `{main, echo}` | Đặt domain chính/ echo. | — |
| `domain.unlock` | `{domainId, node}` | Mở node domain. | — |
| `origin.combo` | `{comboId}` | Nghiên cứu combo nguyên. | — |
| `origin.exchange` | `{originId, sealId, qty}` | Đổi mảnh nguyên. | — |
| `origin.set` | `{main, secondary}` | Đặt nguyên chính/ phụ. | — |
| `origin.unlock` | `{originId}` | Mở nguyên. | — |
| `x3.cos.equip` | `{kind, id}` hoặc `{kind, id:null}` | Trang bị/ bỏ cosmetic. | — |
| `x3.pet.skin` | `{petId, skinId}` hoặc `{petId, skinId:null}` | Đổi skin linh thú. | — |
| `v3.run.step` | `{runId, option?}` | Đi bước bí cảnh mở rộng 3. | `result.{battleId,done,first}` |
| `v3.run.abandon` | `{}` | Rời lượt chạy. | — |
| `dungeon.abandon` | `{}` | Rời dungeon, không nhận thưởng. | — |
| `dungeon.advance` | `{option?}` | Đi tiếp dungeon. | `result` |
| `dungeon.exchange` | `{defId}` | Đổi vật phẩm dungeon. | — |
| `dungeon.leave` | `{}` | Rời dungeon (trả vé). | — |
| `dungeon.run` | `{dungeonId, picks?, option?}` | Chạy dungeon. | `result.{battleId,done,coins}` |
| `dungeon.start` | `{dungeonId}` | Bắt đầu dungeon. | — |

---

## 5. State snapshot — các nhóm chính

Client không có schema cứng, nhưng các nhóm sau được dùng trực tiếp:

| Nhóm | Ví dụ field / mục đích |
|---|---|
| `stateVersion`, `serverNow` | So sánh snapshot, đồng bộ đồng hồ. |
| `character` | `id`, `name`, `gender`, `level`, `realm`, `exp`, `expNeed`, `attrs`, `autoMinor`, `originId`, `portrait`, `tint`… |
| `wallet`, `materials`, `items`, `equipment` | Tài nguyên, vật liệu, túi đồ, trang bị. |
| `loadout`, `assist`, `passives`, `variants`, `learnedSkills`, `skillList` | Bộ kỹ năng. |
| `presets` | `farm`, `boss`, `pvp` + rule/ loadout riêng. |
| `quests`, `chapters`, `daily`, `weekly`, `achievements`, `titles` | Nhiệm vụ/ thưởng. |
| `character.craftSlots`, `craftJobs`/`jobs` | Lò luyện. |
| `fields`, `habitats`, `cave` | Nông trại/ sinh cảnh/ động phủ. |
| `pets`, `puppets`, `v3.comp` | Linh thú/ khôi lỗi/ đồng hành. |
| `x2`, `x3` | Nội dung mở rộng 2/ 3. |
| `v2`, `v3` | Vườn/ quan hệ/ khu vực/ pháp bảo. |
| `guild`, `sect`, `arena`, `market`, `auction`, `mail`, `friends`, `bond`, `npc` | Xã hội/ chợ/ thư. |
| `periodic` | `resetHour`, `dayId`, mốc reset. |
| `tradeOverrides`, `dropRates` | Bảng điều chỉnh client dùng để hiển thị. |

Ghi chú: tên field chính xác có thể khác giữa `tn` và `cm`; luôn đọc từ state thực tế thay vì hard-code.

---

## 6. Quy tắc an toàn khi tích hợp

1. **Luôn gửi `expectedVersion`** cho world `tn` (`state.stateVersion`). World `cm` dùng endpoint `/api/cm/cmd` không có version.
2. **Mỗi mutation một `idempotency-key`**; chỉ retry khi lỗi `NETWORK`, dùng lại đúng key.
3. **Không retry mù** các lệnh tiêu hao tài nguyên/ vật phẩm/ lượt.
4. Sau mỗi lệnh, **áp dụng `state` server trả về**, không tự cộng trừ local.
5. `VERSION_CONFLICT` → GET state mới rồi quyết định, không gửi lại ngay.
6. Kiểm tra `result`/`settle` trước khi báo thành công; client gốc coi lệnh trả JSON là thành công, nhưng logic thực tế nằm trong `result`.
7. Với lệnh có `maxStones`/`maxCoins`, server có thể tiêu ít hơn hoặc đúng ngưỡng; đọc `result.stones`/`result.coins`.
8. Không dùng endpoint `/api/admin/*` cho mini client.

---

## 7. Khoảng trống / cần xác minh

- Chưa có response schema đầy đủ cho từng command; bảng chỉ ghi field client đọc.
- Chưa xác minh hành vi server khi thiếu `expectedVersion`, khi gửi sai `payload`, hoặc khi state đổi giữa 2 request.
- Chưa xác minh `cm` world có dùng chung toàn bộ command hay không; một số command `x2.*`, `x3.*`, `v3.*` chỉ thấy trong UI mở rộng.
- Đã đối chiếu lại danh mục command bằng regex trên `main` và `store`; các lệnh từng nghi vấn đã chốt:
  - `activity.set`: `tn` dùng `{type}`/`{type:'farm',targetId}`, `cm` dùng `{activity}`.
  - `chapter.step`: `{step, branch?}` cho chương x2, `{chapterId, stepId}` cho chương `cm`.
  - `item.dispose`: client không đọc `result`, chỉ cần envelope `ok`.
  - Bổ sung các lệnh bị thiếu: `equip`, `unequip`, `assist.set`, `tech.learn/set/upgrade`, `timer.rush`, `camp.upgrade`.
- `gw2.register`/`gw2.cancel` gọi với payload rỗng; quyền trưởng/ phó bang do UI kiểm tra trước, server vẫn có thể chặn.
- Tên field `settle` (`validMs`, `layerUps`, `equipment`, `craftsCompleted`) đã thấy trong store; các field khác có thể có.

---

## 8. Bảng tra nhanh theo từ khóa

| Cần làm | Command |
|---|---|
| Kết toán offline | `settle` |
| Đổi hoạt động | `activity.set` |
| Tự mặc đồ | `equip.best` / `equip` / `unequip` |
| Dọn túi | `item.dispose` |
| Bỏ qua thời gian chờ | `timer.rush` |
| Luyện đan | `craft.start` / `craft.cancel` / `craft.rush` |
| Dùng đan/ thuốc | `item.use` / `medicine.use` |
| Đánh boss vùng | `boss.fight` |
| Boss thế giới | `worldboss.attack` / `worldboss.claim` |
| Đấu trường | `arena.fight` |
| Gieo/ thu | `field.plant` / `field.harvest` / `field.rush` |
| Nhận nhiệm vụ | `quest.claim` / `daily.claim` / `weekly.claim` / `achievement.claim` |
| Nhận thư | `mail.claimAll` |
| Tông môn | `sect.task.claim` / `sect.donate` |
| Mùa | `season.task.claim` |
| Danh hiệu | `title.claim` |
| Linh thú | `pet.adopt` / `hunt.run` / `pet.trial` |
| Bang hội | `guild.*` |
| Chợ/ đấu giá | `market.*` / `auction.*` |
| Kho chung | `vault.*` |
| Chat/ bạn bè | `chat.send` / `friend.*` / `block.*` |
| Sự kiện | `event.*` / `ev.*` / `x3.*` |
