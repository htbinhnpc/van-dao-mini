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
  - **Tự chế tạo 4 nghề:** ưu tiên nhiệm vụ/đột phá, bổ sung đan/trận kỳ, rồi dồn lò cho nghề nhanh lên cấp kế nhất; khi cả 4 nghề max, mỗi lò một công thức khác nhau. Có ngân sách cày/ngày, dự trữ nguyên liệu/linh thạch, giới hạn tồn kho và bảo vệ túi gần đầy.
  - **Chế tạo:** tab riêng hiển thị 4 cấp nghề, tiến độ, ETA, ngân sách, món đang chế và lý do chọn/chặn. Xem/đồng bộ chỉ đọc, không bắt đầu mẻ.
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
cave.upgrade
item.use
boss.fight
field.plant
field.harvest
field.rush
equip.best
item.transfer
minor.trial
sect.task.claim
season.task.claim
title.claim
title.equip
pet.adopt
npc.talk
npc.claim
hunt.run
item.dispose
arena.fight
encounter.resolve
```

Không chỉnh sửa dữ liệu máy chủ hay vượt qua giới hạn của game. Trên Vercel, Cron xử lý lần lượt các tài khoản đến hạn và dừng trước deadline Function; các tài khoản còn lại tiếp tục ở lượt Cron sau. Nhịp gọi Cron thực tế do `vercel.json` quyết định.

### Dọn túi Mini — bộ chọn đồ riêng

- Vào **Túi đồ → Dọn túi Mini**: chọn bán/phân giải, phẩm chất tối đa, tier tối đa (0 = không giới hạn tier), giới hạn mẻ và vị trí. Bấm **Mặc đồ tốt nhất & xem trước dọn** sẽ gọi `equip.best`, sau đó chuyển mức cường hóa cao nhất cùng ô từ túi sang món đang mặc bằng `item.transfer`. **Bước này thay trang bị và có thể tiêu phí chuyển cường hóa**, nhưng chưa bán/phân giải. Bộ lọc xem trước không tự ghi vào cấu hình auto.
- **Bỏ giới hạn giữ 1 bản/mẫu:** không giữ dự phòng theo `defId`, không giữ riêng roll đánh đổi, đồ độc bản hoặc đồ chưa đủ cấp. Sau khi chuẩn bị, đồ không mặc trong bộ lọc được đưa vào danh sách dọn. Bộ chọn mạnh nhất do game quyết định; theo mô tả client game, không thay đồ đang khóa hay đổi loại vũ khí.
- Luôn bảo vệ đồ đang mặc/kho, khóa/yêu thích, ID trùng, thiếu dữ liệu an toàn và ô chưa có món đang mặc hợp lệ. Nếu cường hóa của đồ dư cao hơn đồ đang mặc nhưng trần món nhận chưa cho phép chuyển hết, giữ món dư thay vì cắt mất cấp. Chuyển lỗi/thiếu phí/timeout hoặc chưa có state xác nhận thì dừng, không dọn. Đồ dư có cường hóa thấp hơn hoặc bằng món đang mặc vẫn có thể bị dọn; không cộng dồn các cấp cường hóa. Không tự mở khóa hay rút kho.
- Bản xem trước có danh sách và lý do giữ/bỏ. Có thể bỏ chọn từng món. **Xác nhận bán/phân giải là thao tác không hoàn tác trong game.** Backend kiểm tra owner, hạn 120 giây, state version, bộ lọc và tập con ID một lần nữa; thay đổi state thì phải xem trước lại. `automation_runs` lưu xác nhận dùng một lần với cập nhật trạng thái nguyên tử; ID này cũng là idempotency key gửi game. Không retry tự động sau timeout/lỗi.
- Luồng thủ công dùng lease theo tài khoản, lưu snapshot thực tế và nhật ký kết quả/ID. Không báo thành công nếu response thiếu state mới hoặc game chưa xác nhận xóa đủ danh sách. Preview dùng bảng `automation_runs` trong migration hiện có, không cần migration mới; job xem trước bỏ dở không tự thực thi khi hết hạn.
- **Dọn không hỏi xác nhận** (`cleanupSkipConfirmation`, mặc định **false**): bật tại Túi đồ để lưu ngay riêng cho tài khoản, hoặc tại Tự động rồi lưu cấu hình. Bật tùy chọn **không chạy dọn** và không tự bật trợ lý. Sau khi bật, nút **Tự chọn và dọn ngay** mặc đồ tốt nhất, chuyển cường hóa (có phí), lập một mẻ theo bộ lọc rồi xử lý không hiện hộp xác nhận; vẫn có thể xem trước, bỏ chọn món và dọn đúng tập đã chọn. Tắt tùy chọn để dùng lại hộp xác nhận. Backend kiểm tra tùy chọn đã lưu; vẫn giữ lease, version, expiry, hạn mức và cơ chế dùng một lần. Không tự retry hoặc tự dọn tiếp các mẻ sau.
- **Auto theo lịch** không hỏi xác nhận từng mẻ và không cần mở trang: bật `autoCleanup` cùng **Trợ lý tự động** (`enabled`) rồi lưu; cần Cron đã triển khai. Khi đã chọn `cleanupSkipConfirmation`, lưu/bật riêng auto dọn Mini cũng không hiện hộp xác nhận rủi ro. Xác nhận của các tính năng khác (tự trang bị, dùng đan, săn…) không bị bỏ qua.
- **Nhật ký → Chi tiết dọn đồ**: có nguồn chạy, có/bỏ xác nhận, bộ lọc, tên/mẫu/ID món, ID bản được giữ, version trước/sau, ID yêu cầu, ID đã dọn và ID còn lại. Có thể tìm theo tên/ID món. Ghi riêng bắt đầu và kết quả thành công/một phần/chưa rõ; state thay đổi thì ghi đã chặn, không có món thì ghi bỏ qua. Không ghi được log bắt đầu thì không gửi lệnh dọn; timeout không được ghi là thành công. Thay đổi tùy chọn auto/bỏ xác nhận cũng được ghi log. Bản ghi bắt đầu mà chưa có kết quả **không có nghĩa đã dọn thành công** — cần đồng bộ game trước khi chạy lại.
- Auto: bật riêng **Tự động → Trang bị & túi đồ → Dọn túi Mini** (`autoCleanup`, mặc định **false**). Luôn chuẩn bị trang bị/chuyển cường hóa trước khi dọn, kể cả khi tắt `autoEquipBest`; hết ngân sách chuẩn bị thì chưa dọn. Các khóa `cleanupMode`, `cleanupMaxRarity`, `cleanupMaxTier`, `cleanupMaxItems`, `cleanupSlots` dùng cùng policy. `cleanupKeepPerDefinition` cũ không còn giữ bản dự phòng. Mặc định mới xét mọi phẩm chất, tối đa 20 món/vòng; giữ giới hạn game **60 món/lệnh**. Bộ lọc phẩm chất/tier đã lưu vẫn có hiệu lực. Preview cũ `cleanup_v1` bị từ chối, cần tạo lại sau cập nhật.
- `autoSalvage` cũ không tự được chuyển thành dọn túi mới: tính năng cũ chỉ xử lý đồ rơi theo game, còn Mini có thể xử lý đồ có sẵn trong túi. Khi chủ động bật Mini, config tắt `autoSalvage`; worker yêu cầu đặt `settings.autoSalvageTier=0` trước lần `settle` rõ ràng tiếp theo. Nếu game tự kết toán trong lệnh thiết lập, Mini không thể đảm bảo cứu lại đồ đã bị bộ dọn gốc xử lý — nên tắt bộ dọn gốc trực tiếp trong game trước khi chuyển.

Các lệnh bán/phân giải mới chỉ được kiểm thử bằng mock và trình duyệt dùng API fixtures; không thử trên tài khoản thật. `item.dispose` bị chặn ở endpoint gửi lệnh tùy ý: phải qua luồng cleanup hoặc policy auto.

### Chọn bãi săn tối ưu tu vi

Khi `autoActivity` bật với `activityType=farm` (và không ghim `huntSpotId`), Mini chọn bãi có **`expPerCycle` cao nhất** trong các bãi thường thuộc vùng đã mở và đạt `reqLevel` — không dựa vào cấp khuyến nghị (`recLevel`). Bãi `x2_spot_hunt_*` và `spot_puppet_*` bị bỏ qua. Vì tu vi chỉ được cộng khi thắng, Mini thử bãi cao nhất rồi học theo `state.activity.win`: nếu game báo thua, nhớ bãi đó trong `automation_data.farmSpotLosses` và chuyển xuống bãi nhiều tu vi kế tiếp, không quay lại ngay (tránh nhảy qua lại). Bãi bị thua được thử lại sau 30 phút, hoặc sớm hơn khi `state.power` tăng ≥ 10% so với lúc thua. Nếu mọi bãi đủ điều kiện đều vừa thua thì chuyển sang bế quan. Tắt `autoFallbackHunt` để luôn ở bãi cao nhất, kể cả khi thua. Logic ở `api/services/farming.py`.

### Auto mở rộng (tất cả mặc định tắt)

Đối chiếu JavaScript **công khai** của game ngày 2026-11-04 (Chrome đang khóa cache; đã dùng bundle công khai thay thế theo lựa chọn người dùng). Đây là logic/payload quan sát từ client, không phải mã xử lý trên server hoặc cam kết API ổn định. Xem bằng chứng trong `api_knowledge.md`.

| Cấu hình | Điều kiện / giới hạn |
|---|---|
| `autoEquipBest` | Khi có đồ trong túi, gọi `equip.best`; game tự chọn. Không tự bán, phân giải, mở khóa hay thay loại vũ khí bằng lệnh riêng. Có thể đổi bộ đồ theo bộ chọn của game. |
| `autoMinorTrial` | Chỉ `character.next=minor`, đủ tu vi, `minorGate.kind=trial` chưa đạt; tối đa 1 lần/10 phút, kể cả thua/lỗi. Không tự đột phá lớn; auto lên tầng của game áp dụng ở lần settle sau. |
| `autoSectTasks`, `autoSeasonTasks` | Nhận nhiệm vụ tông môn/lễ hội có `claimed=false`, đủ `current/target`; không đóng góp, mua hàng hay làm nhiệm vụ tốn vật phẩm. |
| `autoTitles` | Chỉ nhận danh hiệu `earned=true`, `owned=false`; không tự mang/thay danh hiệu. Ba nhóm thưởng này tổng cộng tối đa 3 lệnh/vòng. Việc đeo do `autoEquipTitle` riêng. |
| `autoEquipTitle` | Chỉ đeo danh hiệu `owned=true`, tối đa **một** `title.equip {titleId}`/vòng. Hệ lấy từ `craftBuild` nếu đã chọn, nếu không từ tông môn/vũ khí đang mặc: kiếm/thân thể dùng Công, lôi/hồn/trận dùng Pháp công. Chấm thêm crit/critDmg khi có trong `state.stats`; danh hiệu chỉ có hp/def không được coi là tăng sát thương. Không đổi nếu danh hiệu hiện tại đã tốt hơn hoặc bằng, không có dữ liệu hệ/crit/titles thì không gửi lệnh. Phản hồi phải tăng `stateVersion`, mục tiêu còn `owned` và là danh hiệu duy nhất `equipped`; sai/timeout thì dừng, không retry. |
| `autoPetAdopt` | Tối đa 1 linh thú/vòng khi `canAdopt=true`, `owned=false`; có thể tiêu khế ấn hợp khế. Không tự xuất chiến, nuôi hay tiến hóa. |
| `autoNpcTalk` | Tối đa 2 đạo hữu đã gặp/vòng, chưa trò chuyện ngày và thiện cảm dưới 1000; không tặng quà hay tự chọn quan hệ. |
| `autoNpcRewards` | Tối đa 2 quà mốc thiện cảm/vòng; dùng state mới sau trò chuyện và bỏ qua mốc đã nhận. |
| `autoHunt` | Bắt buộc chọn `huntPetId` trong 40 linh thú khế ấn; đủ cấp, còn lượt trên `huntReserveRuns`, chưa đủ khế ấn và chưa thu nhận. Tối đa 1 lượt/vòng, chờ `huntIntervalMin` (mặc định 10 phút) kể cả thua. Không mua thêm lượt. |
| `autoEncounter` | Kỳ ngộ ở trang Bí cảnh (xuất hiện khoảng mỗi 400 chu kỳ săn, chờ tối đa 3): `encounter.resolve` `{encounterId, choice}` cho từng mục trong `state.encounters`. **Ưu tiên phương án cho cảm ngộ**: Bia đá cũ (+12), Động phủ bỏ hoang (+20), Kiếm ảnh dưới trăng (+30), Tu sĩ hấp hối (+35, tốn 1 Tụ Linh Đan), Hạc bị thương (+8, tốn 5 Linh thảo). Thương nhân lạc đường không có phương án cảm ngộ nên chọn 300 linh thạch (không tốn gì). `encounterAllowCost=false` chỉ cho phép phương án không tốn vật phẩm. Thiếu vật phẩm trả phí thì chọn phương án miễn phí; kỳ ngộ lạ (chưa có trong bảng) bị bỏ qua, không đoán. Tối đa 3 lệnh/vòng, không gửi lại cùng một `encounterId`. Bảng lấy từ client game (`api/services/encounters.py`). |
| `autoArena` | Đấu hạng đấu trường (`arena.fight` với `ranked:true`), cấp ≥ 10, còn `rankedLeft`. Đọc bảng bằng `GET /api/arena?pick=N`; chỉ chọn đối thủ **cùng nhóm cảnh giới** có `power` thấp hơn `state.power` của bạn ít nhất `arenaMinPowerEdge` (mặc định 5.000), ưu tiên chênh lệch lớn nhất (rồi điểm hạng cao hơn). Không có ai phù hợp thì "làm mới" bằng cách tăng `pick`, tối đa `arenaMaxRefresh` lần (mặc định 3); vẫn không có thì không đánh và nghỉ 15 phút. Tối đa `arenaMaxFights` trận/vòng (mặc định 3); không luận bàn, không mua đồ bằng điểm. Không biết `state.power` thì không đánh. Thua thì tránh đánh lại người đó 1 giờ. Lực chiến chỉ là chỉ báo ước tính của server; `arena.fight` bị chặn ở endpoint gửi lệnh tùy ý. |
| `autoCaveUpgrade` | Tối đa **một** `cave.upgrade {roomId}`/vòng; không gọi `cave.rush`. Ưu tiên tuyệt đối phòng mà nhiệm vụ `active` có objective `cave_room` cần; phòng đó thiếu tài nguyên dư thì chờ, không tiêu sang phòng khác. Sau đó theo `caveRoomOrder` (`craft` mặc định: Đan Phòng → Khí Phòng → Linh Điền → Kho → Tụ Linh → Tàng Bảo → Tĩnh Thất; `cultivation`; `balanced` theo tỷ lệ cấp thấp nhất). Không gửi khi đã có phòng `upgradeFinishAt`; giữ `caveReserveStones`/`caveMatFloor`, và khi `autoCraft` bật thì cộng thêm linh thạch/nguyên liệu cho nhiệm vụ chế tạo cùng đan đột phá đại cảnh kế tiếp. Phản hồi phải tăng `stateVersion`, đúng phòng, cấp giữ nguyên hoặc +1, `upgradeFinishAt` dương và chỉ một phòng active; sai/timeout thì dừng, không retry. |

Mỗi vòng dùng state/version mới từ phản hồi trước, tổng cộng **tối đa 12 lệnh**, chỉ bắt đầu lệnh trong cửa sổ 40 giây. Phần chưa chạy để vòng sau. Nếu lệnh lỗi, timeout, xung đột version hoặc phản hồi thiếu state, dừng phần còn lại và lưu lỗi; không retry lệnh có tác dụng phụ với key mới. Lịch sử khoảng nghỉ lưu trong `automation_data`, không chỉ giữ trong RAM. Các kiểm thử dùng mock, chưa bật/thử auto mới trên tài khoản game thật.

Chọn các auto trong tab **Tự động**, lưu cấu hình riêng cho từng tài khoản, rồi dùng **Chạy ngay** để chạy một vòng theo cấu hình đã lưu. Cron chỉ chạy khi tài khoản bật trợ lý; nhịp thực tế còn phụ thuộc lịch Cron của môi trường triển khai (cấu hình Vercel hiện tại là mỗi ngày một lần).

### Chế tạo & tay nghề (`craft_profession`)

Triển khai đặc tả `craft-professions.md` vào `api/services/craft_profession.py` (planner thuần) và worker `_craft` trong `api/services/automation.py`; không có cấu trúc worker TypeScript/economy/gear-opt của dự án được nhắc trong bản đề xuất.

- Bật **Tự động → Chế tạo & đan dược → Tự chế tạo** (`autoCraft`, mặc định **false**). Hai tùy chọn con `craftMastery=true`, `craftProduce=true` chỉ có tác dụng khi bật parent; lưu cấu hình không chạy chế tạo.
- Thứ tự: công thức nhiệm vụ đang làm → đan đại cảnh tiếp theo → công thức ưu tiên đã ghim → Dưỡng Khí Đan mục tiêu → trận kỳ tu luyện tốt nhất đã mở → cày nghề / sản xuất. Không hủy hoặc chiếm lò đang chạy. Nguyên liệu/tiền cho nhiệm vụ và đan đột phá còn thiếu được giữ khỏi các bước bổ sung/cày/sản xuất.
- **Cày nghề:** chọn công thức khả dụng có thời gian ngắn nhất cho từng nghề, so `(next-crafted-pending) × duration × (1−3%×(level−1)) / slots`. `craftLevelOrder=fastest` chọn ETA cấp kế nhỏ nhất; `all-max-first` chọn nghề còn nhiều thời gian tới max nhất (ước tính). Dồn các lò trống vào một nghề, giữ focus tới khi lên cấp, không xếp vượt số điểm cần cho cấp kế. Nghề bị thiếu nguyên liệu dư/cấp/ngân sách được bỏ qua; nếu đã xếp đủ mẻ lên cấp thì chờ kết toán.
- **Tài nguyên:** `craftReserveStones=1000`, `craftMatFloor=20` là mặc định. Sàn nguyên liệu dùng cho bổ sung/cày/sản xuất; nhiệm vụ và đan đột phá có thể dùng nguyên liệu dự trữ của chính chúng. `craftLevelDaily=20` là **% linh thạch dư đầu ngày UTC**, không phải 20 viên. Base ngày được giữ cố định trong `automation_data.craftLevelBudget`, không tăng theo tiền kiếm thêm. Trước mỗi lệnh cày, lưu giữ chỗ cả chi phí dự kiến; timeout không hoàn lại ngân sách mù. 0% vẫn cho phép công thức miễn phí. Chỉ ngân sách cày bị giới hạn này; các mẻ nhiệm vụ/bổ sung/sản xuất vẫn tôn trọng khoản linh thạch dự phòng và ghi rõ chi phí.
- **Túi/tồn kho:** Rèn khí nghỉ nếu túi + thành phẩm lò đang chạy đạt ≥90%, chưa biết sức chứa hoặc không đủ chỗ cho bonus. `craftInsuranceKeep=30` (10–30) giới hạn Tị Lôi Phù/Hộ Thân Trận Bàn; đủ kho thì bỏ qua nghề đó. `craftQiTarget=10`, `craftCharmTarget=2`, `craftKeepQty=10` kiểm soát các mục tiêu bổ sung/sản xuất, tính cả lò đang chạy. Đặt mục tiêu 0 để bỏ bước bổ sung/sản xuất tương ứng (không cấm cày nghề bằng công thức đó).
- **Sản xuất:** chỉ khi **cả 4 nghề có `next=null` rõ ràng**; không đoán max từ cấp 10 hoặc dữ liệu thiếu. Mỗi lần `craft.start` đặt đúng 1 mẻ, không lặp công thức đang chạy; replan từ state mới để không tiêu trùng tài nguyên. Ưu tiên đan tu luyện, đan trực tiếp thuộc dải cấp cao nhất đã mở, trận kỳ và vũ khí cùng hệ có tier cao hơn/ô trống. `craftBuild=auto` nhận từ tông môn/vũ khí, hoặc chọn rõ sword/thunder/body/soul/formation. Metadata chưa đủ để so vũ khí x2, gear-opt hay định giá chợ: **không đoán chỉ số, không tự rèn loại chưa biết, không tự đăng chợ**. Bùa chiến đấu không tự sản xuất nếu chưa có dữ liệu nhu cầu trận cụ thể. Các lò không có lựa chọn đủ điều kiện được để trống.
- **Client khác bản đề xuất:** bundle công khai 2026-11-05 hiển thị bonus +1 ở cấp 5/+2 ở cấp 10 **cho cả Rèn khí**. Mini tính bonus đó khi dự trù tồn kho/túi. `next` lấy từ state là dữ liệu quyết định; mốc 115/150 trong tài liệu chỉ phục vụ ETA tương lai có ghi là ước tính.
- **Tab Chế tạo:** đọc `GET /api/v1/accounts/{id}/crafting` từ snapshot; **Đồng bộ lò** thêm `refresh=true` để GET state game mới. Không gửi `craft.start`. Ngân sách/focus/lý do từng job lưu trong `automation_data`, không cần migration. Worker dùng lease hiện có, tối đa 8 lượt bắt đầu chế tạo và vẫn nằm trong trần 12 lệnh/40 giây toàn vòng; lỗi/thiếu state/mẻ chưa được xác nhận thì dừng, không retry.

Kiểm thử dùng mock và fixtures, **chưa thực hiện thử chế tạo 1 giờ trên tài khoản thật** như bước thử nghiệm trong bản đề xuất.

### Nâng phòng động phủ (`cave_rooms`)

Planner thuần ở `api/services/cave.py`; worker `_cave` trong `api/services/automation.py` chỉ gửi lệnh sau khi planner xác định phòng đủ điều kiện. Không thêm tab mới: cấu hình nằm trong nhóm **Động phủ & linh điền**, tiến độ 7 phòng nằm trong panel **Động phủ** ở Tổng quan.

- Bật **Tự động → Động phủ & linh điền → Tự nâng phòng động phủ** (`autoCaveUpgrade`, mặc định **false**). Chỉ dùng `cave.upgrade {roomId}`; `cave.rush` không nằm trong allowlist.
- **Mỗi lúc một phòng:** nếu bất kỳ phòng nào có `upgradeFinishAt` thì không gửi lệnh. Chỉ đọc `state.cave.unlocked` và đủ 7 record `{id, level, upgradeFinishAt}`; thiếu/sai kiểu/dư phòng thì báo `unknown`, không suy đoán cấp.
- **Ưu tiên nhiệm vụ:** objective `cave_room {roomId, level}` của nhiệm vụ `active` được xét trước mọi thứ tự cấu hình. Nếu phòng đó chưa đủ tài nguyên dư, Mini chờ chứ không nâng phòng khác.
- **Thứ tự:** `caveRoomOrder=craft` (mặc định) ưu tiên Đan Phòng, Khí Phòng, Linh Điền, Kho rồi Tụ Linh, Tàng Bảo, Tĩnh Thất; `cultivation` ưu tiên Tụ Linh/Tĩnh Thất; `balanced` chọn phòng có tỷ lệ `level/maxLevel` thấp nhất.
- **Chi phí** lấy từ client công khai: `round(baseStones × 1.7^level)` linh thạch, `baseQty × (level+1)` nguyên liệu và `baseMinutes × (level+1)` phút. Bảy phòng: Tụ Linh (10 cấp, 300, Hàn Tinh ×4, 10 phút), Tĩnh Thất (12, 250, Thiết khoáng ×10, 8), Đan Phòng (6, 500, Linh thảo ×20, 15), Khí Phòng (5, 500, Thiết khoáng ×20, 15), Linh Điền (4, 800, Linh thảo ×30, 20), Kho (8, 200, Thú bì ×10, 5), Tàng Bảo Khố (5, 2.000, Thiết khoáng ×30, 30).
- **Dự trữ:** luôn giữ `caveReserveStones` (mặc định 1.000) và `caveMatFloor` (mặc định 20 mỗi loại). Khi `autoCraft` bật, cộng thêm linh thạch/nguyên liệu mà các ưu tiên **Nhiệm vụ đang làm** và **Đan đột phá đại cảnh kế tiếp** cần, cùng `craftReserveStones`/`craftMatFloor`; thiếu dữ liệu chế tạo thì tạm dừng nâng phòng.
- **Xác nhận:** response phải tăng `stateVersion`, đúng `roomId`, cấp giữ nguyên hoặc tăng 1, `upgradeFinishAt` dương, không phòng khác đổi cấp và chỉ đúng một phòng active. Lỗi/timeout/response không xác nhận: ghi nhật ký `uncertain`, dừng vòng, không gửi lại.
- `GET /api/v1/meta` trả `rooms` (id, tên, cấp tối đa, hiệu ứng) để UI hiển thị; state tài khoản vẫn là nguồn duy nhất cho cấp hiện tại.

Kiểm thử bằng mock/fixtures; **chưa nâng phòng trên tài khoản thật**.

### Cơ chế dùng đan

- **Tự chế tạo** chỉ gọi `craft.start` với `{ recipeId, count }`; không thêm lệnh rush/cancel/mua nguyên liệu. Các giới hạn và ưu tiên tay nghề được mô tả ở trên.
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
