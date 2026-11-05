# Vấn Đạo: Nghịch Mệnh — kiến thức từ bundle game gốc (Chrome cache)

Tài liệu tóm tắt để dùng lại khi phát triển Mini. Nguồn: bundle frontend của `https://vandaonghichmenh.hongvan.net:60010`, đọc **từ cache Chrome** (`%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache\Cache_Data`) ngày 2026-11-05, phân tích **tĩnh** (TypeScript AST + regex; không chạy code bundle). Đây là logic/dữ liệu phía client; điều kiện, công thức và phần thưởng cuối cùng do server quyết định. Bổ sung cho `api_knowledge.md` (kiểm tra API thật), không thay thế.

## 1. Phạm vi và quyền riêng tư

- Chỉ trích **tài nguyên tĩnh** (JS/CSS/JSON motion). **Không** đọc entry API trong cache (`/api/state`, `/api/chat`, `/api/auth/*`, `/api/battles/*`…), không đọc cookie/session, không gửi request nào tới game.
- Cache dạng blockfile (`data_0..3` + `f_XXXXXX`); body nén **zstd** (Python 3.14 `compression.zstd` hoặc Node `zlib.zstdDecompressSync` giải được).
- Bản trích thô và công cụ nằm ở `.bundle_cache/` (đã thêm vào `.gitignore`, **không commit** vì là nội dung của bên phát hành): `tools/extract.py` (cache → file), `tools/dump.cjs` (literal → JSON), `tools/toplevel.cjs` (liệt kê khai báo lớn), `tables/*.json` (các bảng dữ liệu).

## 2. Bundle gồm những gì

SHA-256 là của nội dung **sau khi giải nén** (khác bảng hash trong `api_knowledge.md`, vốn tính trên bản tải về lưu UTF-8; tên file Vite giống nhau → cùng build).

| File `/assets/` | Giải nén | SHA-256 (giải nén, rút gọn) | Vai trò |
|---|---|---|---|
| `main-Bmv0z3VX.js` | 874 KB | `1ff59a09…cecaf9a` | React UI: toàn bộ trang/tab, gọi lệnh |
| `store-BU-hRQPl.js` | 2,7 MB | `f4554199…53214` | React + zustand store + HTTP wrapper + **manifest asset ảnh** (`Ct`, 2,4 MB) + thông báo khóa tính năng (`Z`) |
| `i18n-DxMaxujG.js` | 1,06 MB | `6a338979…ba3638` | **Dữ liệu nội dung game** + bản dịch vi/en |
| `scene-n3fvB4Ln.js` | 64 KB | `a4ca5c6c…ad5` | Phaser Scene phát lại trận đánh (kỹ năng, VFX) |
| `phaser-wjeKs800.js` | 1,2 MB | `2eb97bfe…ee7` | thư viện Phaser |
| `phaserI18n-CTAoeiJK.js` | 348 B | — | patch `Text.setText` dịch sang `en` |
| `main-Dl8iUS-g.css` | 232 KB | `46c4b4d1…bb7b9e5` | CSS |
| `motion/hero_wanderer_male_idle_01.json` | 148 KB | — | dữ liệu animation |

Hệ quả kiến trúc: **server-authoritative**. Client không chứa công thức tu vi/rơi đồ; chỉ chứa bảng nội dung (tên, mô tả, hệ số hiển thị), UI và gọi lệnh. Mọi thay đổi đi qua `POST /api/cmd/{lệnh}`.

## 3. Giao thức HTTP (xác nhận lại từ `store`)

- `fetch` với `credentials: same-origin`; JSON; timeout **30 s**; GET dedupe theo URL.
- Lỗi: `!res.ok || body.ok === false` → `ApiError(errorCode ?? "INTERNAL", status, details, stateVersion)`. JSON không parse được: status ≥ 500 hoặc abort → `NETWORK`.
- Lệnh: `POST /api/cmd/{command}` body `{payload, expectedVersion}` + header `idempotency-key` (UUID **một lần cho cả vòng retry**). Retry tối đa 2 lần (chờ 800 ms, 1600 ms) **chỉ** khi `NETWORK`. `expectedVersion` chỉ gửi khi UI gọi với `guard:true` (= `state.stateVersion`); lệnh không guard gửi `undefined`.
- Mọi lệnh được **xếp hàng tuần tự** (chuỗi promise); riêng `settle` được dedupe (đang chạy thì dùng lại promise).
- `applyState`: bỏ state cũ hơn (`stateVersion` nhỏ hơn, hoặc bằng nhau mà `serverNow` cũ hơn); tính `clockOffset = serverNow − Date.now()`; so ví/vật liệu/trang bị mới để hiện loot.
- `VERSION_CONFLICT` → client tự GET `/api/state` lại. `UNAUTHENTICATED` → về màn đăng nhập. `NETWORK` → chế độ offline, `boot()` thử lại sau 3 s.
- `boot()`: `GET /api/auth/me` → (`paymentRequired` → phase `payment`; `maintenance` → `maintenance`; `!hasCharacter` → `create`) → `GET /api/state` → **`settle` (silent)**. `settle` trả `{settle:{validMs, discardedMs, layerUps, equipment, craftsCompleted, equipSkippedCycles…}, state}`; offline ≥ 60 s hiện báo cáo; ≥ 6 giờ (216e5 ms) có cảnh báo riêng.
- Mã lỗi biết: `NETWORK INTERNAL MAINTENANCE UNAUTHENTICATED VERSION_CONFLICT REQUIREMENT_NOT_MET INSUFFICIENT_RESOURCES LEVEL_TOO_LOW REGION_LOCKED RANK_TOO_LOW SECT_REQUIRED QUEST_NOT_COMPLETE DAILY_LIMIT WEEKLY_LIMIT NOT_READY BAG_FULL SKILL_NOT_LEARNED SLOT_LOCKED GUILD_REQUIRED FEATURE_UNAVAILABLE AT_CONTENT_CAP`. UI coi nhóm “chưa đủ điều kiện” (mọi mã trên trừ `NETWORK/INTERNAL/MAINTENANCE/UNAUTHENTICATED`) là lỗi nghiệp vụ, không retry.
- Nhánh **Cầu Ma** dùng `/api/cm/state|gw|tl` và `POST /api/cm/cmd/{lệnh}` (không có `expectedVersion`, không dùng cho game thường).

### Route khác trong UI
`/api/auth/{login,register,recover,recovery-code,me,logout,sessions,sessions/revoke}`, `/api/character(s)[/select]`, `/api/state`, `/api/battles/{id}` (log trận; retry mạng 1/3/6/10 s), `/api/online[/events]`, `/api/payment/{fee,registration,events}`, `/api/discord/{link,link/code,unlink}`, `/api/maintenance`, `/api/announcements`, `/api/events`, `/api/mail`, `/api/vault`, `/api/market?kind&q&rarity&slot&maxPrice&sort|mine|bought`, `/api/auctions[?mine=1]`, `/api/arena?pick=`, `/api/chat?channel=&after=`, `/api/friends`, `/api/guild(s)`, `/api/guild-emblem/{id}?v=`, `/api/guildquests`, `/api/guildwar`, `/api/gw2[/match/{id}|/battle/{id}]`, `/api/worldboss?scope=`, `/api/ranking?type=&group=`, `/api/cm/ranking`, `/api/x3/ranking?event=`, `/api/profile/{id}`, `/api/breakthrough/odds`, và nhóm quản trị `/api/admin/{audit,ban,character,economy,mail,overview,reports}` (cần role admin; Mini không dùng).

## 4. Danh mục lệnh game (`POST /api/cmd/{lệnh}`)

Trích từ các chỗ gọi trong `main`: **~255 lệnh**. Ngoặc là khóa payload quan sát được; `*` = UI gửi `expectedVersion` (guard). Chưa xác minh server-side với tài khoản thật, trừ các lệnh đã ghi trong `api_knowledge.md`.

| Nhóm | Lệnh `(khóa payload)` — `*` = UI gửi `expectedVersion` (guard) |
|---|---|
| `achievement` | `achievement.claim`(achievementId) |
| `activity` | `activity.set`(type,activity) |
| `ancient` | `ancient.puppet`() · `ancient.resonate`(picks,stat) · `ancient.runes`(runeIds) · `ancient.temper`() · `ancient.train`(on) · `ancient.trial`(chapterId) |
| `arena` | `arena.buy`(shopId) · `arena.fight`(defenderId,ranked) |
| `artifact` | `artifact.set`(skillId) |
| `ascend` | `ascend.trial`() |
| `assist` | `assist.set`(npcId) |
| `attrs` | `attrs.reset`(attrs)* |
| `auction` | `auction.bid`(auctionId,amount) · `auction.cancel`(auctionId) |
| `block` | `block.add`(characterId) · `block.remove`(characterId) |
| `body` | `body.refine`(axis) |
| `bond` | `bond.assist`(on) · `bond.cancel`(bondId) · `bond.end`(bondId) · `bond.invite`(name,kind) · `bond.share`(on) · `bond.sign`(bondId) |
| `bone` | `bone.temper`() |
| `boss` | `boss.fight`(bossId) |
| `breakthrough` | `breakthrough.major`()* · `breakthrough.minor`() · `breakthrough.trial`()* |
| `camp` | `camp.upgrade`() |
| `cave` | `cave.rush`(roomId,maxStones) · `cave.upgrade`(roomId) |
| `ch1` | `ch1.choose`(choice) |
| `chain` | `chain.act`(action) · `chain.start`() |
| `chapter` | `chapter.break`(chapterId,stepId) · `chapter.choose`(chapterId,choice) · `chapter.claim`(chapterId) · `chapter.fight`(chapterId,stepId) · `chapter.step`(chapterId,stepId) |
| `character` | `character.rename`(name) |
| `chat` | `chat.send`(channel,body,equipmentId) |
| `clone` | `clone.set`(clone) |
| `control` | `control.step`(step) |
| `core` | `breakthrough`() · `equip`(itemId)* · `settle`() · `unequip`(itemId)* |
| `craft` | `craft.cancel`(jobId) · `craft.rush`(jobId,maxStones) · `craft.start`(recipeId,count)* |
| `daily` | `daily.claim`(taskId) |
| `dao` | `dao.research`(daoId) · `dao.setMain`(daoId) · `dao.trial`() |
| `demonic` | `demonic.calm`() · `demonic.join`(branch) · `demonic.switch`(path,branch) · `demonic.tier`(branch) · `demonic.trial`() |
| `domain` | `domain.set`(main,echo) · `domain.unlock`(domainId,node) |
| `dungeon` | `dungeon.abandon`() · `dungeon.exchange`(defId) · `dungeon.leave`() · `dungeon.start`(dungeonId) |
| `encounter` | `encounter.resolve`(encounterId,choice) |
| `equip` | `equip.best`()* |
| `essence` | `essence.research`(essenceId) · `essence.set`(main,secondary) |
| `ev` | `ev.draw`(eventId,count,useTickets) · `ev.fight`(eventId,kind,n) · `ev.shop`(eventId,skinId) · `ev.tickets`(eventId) |
| `event` | `event.daily`() · `event.exchange`() · `event.stage`(stageId) |
| `evidence` | `evidence.claim`(evidenceId) |
| `field` | `field.harvest`(plot) · `field.plant`(plot,seedId) · `field.rush`(plot,maxStones) |
| `friend` | `friend.accept`(characterId) · `friend.remove`(characterId) · `friend.request`(name) |
| `gate` | `gate.attempt`(gateId) |
| `gear` | `gear.buy`(slot) |
| `giftcode` | `giftcode.redeem`(code) |
| `guide` | `guide.set`(done) |
| `guild` | `guild.apply`(guildId) · `guild.checkin`() · `guild.create`(name) · `guild.donate`(stones) · `guild.emblem`(image) · `guild.kick`(characterId) · `guild.leave`() · `guild.notice`(notice) · `guild.quest.claim`(questId) · `guild.rename`(name) · `guild.research`(techId) · `guild.review`(characterId,accept) · `guild.shop`(shopId) · `guild.skill`(skillId) · `guild.transfer`(characterId) · `guild.upgrade`() |
| `guildwar` | `guildwar.attack`(nodeId) · `guildwar.garrison`(nodeId) |
| `gw` | `gw.register`() · `gw.shop`(offerId) |
| `gw2` | `gw2.lineup`(order) |
| `habitat` | `habitat.open`(habitatId) · `habitat.rush`(habitatId,maxStones) |
| `hunt` | `hunt.run`(petId) |
| `immortal` | `immortal.refine`(qty) · `immortal.setForm`(form) · `immortal.train`(form)* |
| `item` | `item.dispose`(itemIds,mode)* · `item.enhance`(itemId)* · `item.favorite`(itemId,favorite) · `item.lock`(itemId,locked) · `item.transfer`(fromId,toId)* · `item.use`(itemId,qty) |
| `journey` | `journey.enter`() · `journey.return`() |
| `legacy` | `legacy.view`() |
| `loadout` | `loadout.set`(rules,passives,preset)* |
| `look` | `look.set`(tint,portrait) |
| `mail` | `mail.claim`(mailId) · `mail.claimAll`() · `mail.delete`(mailId) |
| `manvan` | `manvan.rebranch`(branch,memories) · `manvan.research`(nodeId) · `manvan.set`(memories,branch) |
| `market` | `market.buy`(listingId) · `market.cancel`(listingId) |
| `medicine` | `medicine.use`(itemId,withQingChen) |
| `meridian` | `meridian.attune`(meridianIds) · `meridian.core`(core) · `meridian.open`() · `meridian.unlock`(meridianId) |
| `minor` | `minor.trial`() |
| `mortal` | `mortal.begin`(lineId) · `mortal.choose`(lineId,choice) · `mortal.rechoose`(lineId,step,choice) |
| `npc` | `npc.claim`(npcId,tierId) · `npc.errand`(npcId) · `npc.gift`(npcId,itemId,qty)* · `npc.marry`(npcId) · `npc.pin`(npcId,on) · `npc.quest`(questId,choice) · `npc.talk`(npcId) |
| `origin` | `origin.combo`(comboId) · `origin.exchange`(originId,sealId,qty) · `origin.set`(main,secondary) · `origin.unlock`(originId) · `origin.weekly`(originId) |
| `pet` | `pet.adopt`(petId) · `pet.condition`(petId) · `pet.evolve`(petId) · `pet.feed`(petId) · `pet.set`(petId) · `pet.trial`(petId) |
| `practice` | `practice.fight`(encounterId) |
| `preset` | `preset.clear`(preset) |
| `profile` | `profile.showBond`(show) |
| `puppet` | `puppet.craft`(puppetId) · `puppet.set`(puppetId) · `puppet.skill`(puppetId) · `puppet.upgrade`(puppetId) |
| `quest` | `quest.claim`(questId) |
| `research` | `research.branch`(branch) · `research.node`(nodeId) · `research.reset`() |
| `rules` | `rules.set`(preset) |
| `season` | `season.buy`(shopId)* · `season.task.claim`(taskId) |
| `secret` | `secret.enter`(realmId) |
| `sect` | `sect.buy`(shopId)* · `sect.donate`(itemId,qty) · `sect.join`(sectId) · `sect.leave`() · `sect.task`(taskId) · `sect.task.claim`(taskId) |
| `settings` | `settings.set`(autoMinor) |
| `shop` | `shop.buy`(offerId) |
| `skill` | `skill.learn`(skillId) |
| `skin` | `skin.claim`(skinId) · `skin.equip`(skinId) · `skin.set`(skinId) |
| `stance` | `stance.set`(stance) |
| `story` | `story.recall`(chapterId) · `story.step`(chapterId,step) |
| `survey` | `survey.run`(surveyId) |
| `tech` | `tech.learn`(techId)* · `tech.set`(main,subs)* · `tech.upgrade`(techId)* |
| `timer` | `timer.rush`(maxCoins) |
| `title` | `title.claim`(titleId) · `title.equip`(titleId) |
| `tl` | `tl.fight`() |
| `tower` | `tower.climb`() |
| `training` | `training.dummy`(preset,kind,seconds) |
| `treasure` | `treasure.bind`(treasureId) · `treasure.branch`(branch) · `treasure.nurture`() |
| `v2` | `v2.flower`() · `v2.rel.claim`(relId,tierId) · `v2.rel.gift`(relId,itemId,qty) · `v2.rel.quest`(relId) · `v2.rel.talk`(relId) |
| `v3` | `v3.area.farm`(areaId,option) · `v3.area.unlock`(areaId) · `v3.art.equip`(artId) · `v3.art.forge`(artId) · `v3.art.upgrade`(artId,branch) · `v3.comp.quest`(compId) · `v3.gear.craft`(gearId) · `v3.manual.choose`(manualId,choice) · `v3.manual.learn`(manualId) · `v3.manual.slot`(main,aux) · `v3.run.abandon`() · `v3.run.step`(runId) |
| `weekly` | `weekly.claim`(taskId) |
| `worldboss` | `worldboss.attack`(scope) · `worldboss.claim`(scope,milestoneId,originId) |
| `x2` | `x2.daily.claim`() · `x2.manual.get`(manualId) · `x2.shop.buy`(itemId,qty,currency) · `x2.skill.learn`(skillId) |
| `x2t` | `x2t.ascend`(treasureId) · `x2t.exchange`(treasureId,qty) · `x2t.forge`(treasureId) |
| `x3` | `x3.alchemy`(mode) · `x3.cos.equip`(kind,id) · `x3.daily`() · `x3.ladder`(floor,mode) · `x3.lwheel.draw`(wheelId,count,maxStones) · `x3.mirror`(choices,mode) · `x3.pet.skin`(petId,skinId) · `x3.shop`(eventId,itemId) · `x3.story`(n,branch,preset) · `x3.trial`(n,preset) · `x3.wheel.draw`(count,maxStones,useTickets) · `x3.wheel.exchange`(skinId) · `x3.wheel.mission`(missionId) |
| *(bổ sung, payload phức tạp)* | `tribulation.fight`(trialId,originId,responses) · `npc.heart`(npcId,choice=`friend`\|`romance`) · `chat.report`(messageId,reason) · `guild.setRole`(characterId,role) · `domain.attune`(domainId,branch) · `x3.cloud`(mode) · `encounter.fight`(encounterId) · `skills.set`(loadout,assist,passives,…) · `dungeon.run`(dungeonId,picks) · `v3.comp.set`(compId,mode=`assist`\|`companion`) · `v2.garden`(action=`plant`\|`harvest`,slot) · `v2.cure`(action=`start`\|`collect`,slot) |

Ghi chú payload: `item.dispose` `{itemIds[], mode:'sell'|'salvage'}` (UI cắt 60 ID/lệnh); `item.use` `{itemId, qty}`; `*.rush` nhận `maxStones` (chuỗi số) hoặc `maxCoins` (trần được phép tiêu — **luôn đặt trần**); `activity.set` có hai dạng khóa (`type`/`activity`) tùy màn hình — dùng dạng đã xác minh trong `game_rules.py`; `breakthrough.major` `{insurance?, topUp?}`.

### Phân loại rủi ro cho auto (đề xuất của mình, theo ngữ nghĩa lệnh)
- **Nhận thưởng, ít rủi ro**: `settle`, `quest.claim`, `daily.claim`, `weekly.claim`, `achievement.claim`, `mail.claimAll`, `x2.daily.claim`, `sect.task.claim`, `season.task.claim`, `title.claim`, `npc.claim`, `guild.checkin`, `guild.quest.claim`, `chapter.claim`, `event.daily`, `x3.daily`, `evidence.claim`, `skin.claim`.
- **Tiêu tài nguyên, cần điều kiện chặt**: `craft.start/cancel`, `field.plant/harvest`, `v2.garden`, `pet.feed/evolve`, `item.use`, `item.enhance`, `equip.best`, `tech.*`, `skill.learn`, `sect.donate`, `guild.donate`, `hunt.run`, `boss.fight`, `minor.trial`, `npc.talk`, `pet.adopt`.
- **Có thể mất tài nguyên / không hoàn tác — không auto mặc định**: `*.rush` (linh thạch), `breakthrough.major/trial`, `item.dispose`, `item.transfer`, `attrs.reset`, `research.reset`, `npc.gift`, `x3.*wheel.draw`, `ev.draw`, `auction.bid`, `market.buy`, `shop.buy`, `*.exchange`.
- **Xã hội / ngoài phạm vi Mini**: `chat.*`, `friend.*`, `block.*`, `guild.create/kick/transfer/setRole/rename`, `guildwar.*`, `gw*`, `bond.*`, `npc.marry`, `giftcode.redeem`, `character.rename`, `arena.fight`.

## 5. Mô hình nội dung game (từ `i18n` + bản dịch)

### Cảnh giới (`realm.*`, 23 bậc; 4 loại: Cảnh giới / Chuyển tiếp / Thử thách / Danh hiệu)
Ngưng Khí → Trúc Cơ → Kết Đan → Nguyên Anh → Hóa Thần → Anh Biến → Vấn Đỉnh → Âm Hư → Dương Thực → Khuy Niết → Tịnh Niết → Toái Niết → Thiên Nhân ngũ suy → Không Niết → Không Linh → Không Huyền → Huyền Kiếp → Không Kiếp → Đạp Thiên → Kim Tôn → Thiên Tôn → Dược Thiên Tôn → Đại Thiên Tôn. Id: `ngung_khi, truc_co, ket_dan, nguyen_anh, hoa_than, anh_bien, van_dinh, am_hu, duong_thuc, khuy_niet, tinh_niet, toai_niet, thien_nhan_ngu_suy, khong_niet, khong_linh, khong_huyen, huyen_kiep, khong_kiep, dap_thien, kim_ton, thien_ton, duoc_thien_ton, dai_thien_ton`. Mỗi cảnh giới chia tầng (`layer`), rồi sơ/trung/hậu kỳ/viên mãn.

### Tài nguyên, hoạt động, thuộc tính
- Tiền tệ: `spirit_stone` Linh thạch, `exp` Tu vi, `sect_contribution` Cống hiến, `festival_token` Lễ phù. Số lớn là **chuỗi BigInt** (`wallet`), hiển thị K/M/B/T.
- Hoạt động (`activity.set`): `farm` Săn yêu thú (tu vi 100% + thưởng mỗi chu kỳ), `seclusion` Bế quan (180%, không thưởng), `gather_herb` Hái dược (70%, 1–2 linh thảo/30 s), `mine_ore` Đào khoáng (70%, 1–2 thiết khoáng/30 s), `body_training` Luyện thể Cổ Thần (100%, 1 tôi cốt/10 phút), `none` Tĩnh tọa.
- Thuộc tính gốc: Căn cốt (+1,5% HP, +1% Thủ/điểm), Ngộ tính (+2% tốc độ tu vi/điểm), Đạo tâm (+0,8% Kháng, +1% Linh lực/điểm), Cơ duyên (+2% tỉ lệ rơi/điểm).
- 22 chỉ số: hp mp atk matk def res speed acc eva crit critDmg pen mpen regen cdr mpRegen healRecv shieldPct ctrlRes dotRes mpCost buffDur.
- Phẩm (7): Phàm < Linh < Huyền < Địa < Thiên < Tiên < Đạo. Ô trang bị (8): weapon robe head bracer belt boots ring pendant.
- Nhiệm vụ ngày: 150 chu kỳ săn, 40 lượt hái/đào, 1 chế tạo, 1 boss vùng, 1 cường hóa, 1 quyên góp tông môn. Tuần: 2.500 chu kỳ săn, 5 boss vùng, 8 chế tạo. Thành tựu: 1k/10k/100k trận, 20 chế tạo, 10/50 boss, 20 cường hóa, 30 thu hoạch linh điền, 10 nâng động phủ.
- Chuỗi 40 nhiệm vụ mở đầu `q01…q40` (mục tiêu: `counter, reach_level, realm_reached, equipped_slot, active_skills, boss_cleared, sect_joined, cave_room, treasure_bound, mortal_done, dao_level, stance_set, essence_level, gate_passed`); q01 = thắng 1 chu kỳ săn, q40 = đạt `dap_thien` (thưởng 10 tỷ linh thạch).

### Chiến đấu
71 kỹ năng (`basic`/`active`) có `mpCost, cooldownMs, castMs, targeting`, `effects[{type, school: physical|magic, coef}]`, `iconId`, `vfxId`; 51 loại quái (`archetype`, `level`, `regionId`, hệ số `hp/atk/def`, `speed`, `eva`); 29 trạng thái (`shock burn freeze silence stun bleed shield regen slow frenzy armor_break` + các ấn kiếm ý/điện/cương/hồn/cấm/sát). Trận mô phỏng ở **server**; client phát lại log từ `/api/battles/{id}` bằng `scene` (Phaser).

### Mở rộng V2 (bảng `da`, nguồn `docs/VAN_DAO_MO_RONG_V2_CLAUDE_CODE.txt`)
40 linh thú `x2_pet_001..040` (tối đa 3 dạng tiến hóa; `hunt` `x2_hunt_01..10` theo cảnh giới Trúc Cơ → Không Kiếp, `perRun` 4→20, `contract` 20→480 khế ấn); 24 dược liệu (`hours` 2→30); 100 công thức (nghề luyện đan/luyện khí…, `profLevel`, `inputs`, `stones`, `minutes`); 100 trang bị / 10 bộ `x2_set_01..10` (2/4/6 món); 12 bí cảnh `x2_dungeon_01..12` (`band` 3→10, nhiều phòng + boss); 16 chương `x2_ch_01..16` (Nguyên Anh → Đạp Thiên); 9 sao Cổ Thần; 12 NPC đạo hữu; 24 pháp bảo; 12 boss bản đồ + 12 world boss; 12 bản nguyên + 24 tổ hợp; 12 bộ công pháp / 60 kỹ năng `x2_skill_*`; 24 ngoại hình; 30 vật liệu; 16 ý cảnh; 10 mỏ; 5 suy + 9 kiếp; 8 vật liệu phụ.

### Nhánh Cầu Ma / Phase 2–3 (bảng `bf`, `tp`)
16 cảnh giới theo 4 trục: Ngưng Huyết, Khai Trần, Tế Cốt, Man Hồn · Mệnh Cách, Mệnh Khuyết, Mệnh Cung, Mệnh Giới · Chưởng, Duyên, Sinh, Diệt · Hiên, Bất Khả Ngôn, Cửu Trọng Đạo Thần, Đạo Vô Nhai; 12 chương (7–18), 11 chạm trán, 16 lần đột phá có `failurePolicy`, 13 nút nghiên cứu, 4 đồng hành. V3: 20 bản đồ `cm3_map_*`, 30 đồng hành, 30 pháp khí, 50 công pháp, 30 trang bị; V2: 16 bản đồ + 8 bí cảnh.

### Điều hướng (`nav.*`) và cấu trúc `state`
Tab: Tu luyện, Nhân vật, Công pháp, Túi đồ, Kho đồ, Bản đồ, Đột phá, Chế tạo, Nhiệm vụ, Linh thú, Khôi lỗi, Hành trình, Động phủ, Tông môn, Pháp bảo, Kinh mạch, Cổ Thần, Ma tu, Cây ý cảnh, Bản nguyên, Đấu giá, Ngoại hình, Hoạt động, Chiến Tuyến, Đồ giám, Ngộ đạo, Bí cảnh, Thư, Bạn bè, Bang hội, Xếp hạng, Đấu trường, Chợ, Boss chung, Chứng đạo, Tâm pháp, Đạo hữu, Lễ hội, Cài đặt.
Khóa `state` quan sát được: `character{id,realm,level,gender,autoMinor,…}`, `wallet{}`, `materials{}`, `equipment[{id,defId,location,locked,favorite,…}]`, `stateVersion`, `serverNow`, `periodic{resetHour}`, `tradeOverrides`, `dropRates`, `sect`, `season`, `ascend`, `pets`, `puppets`, `secret`, `control`, `essence`, `journey`, `unreadMail`, `guideDone`, và cụm `x2.*` (meridians, domains, origins, demonic, hunt…), `x3.*` (wheel…), `v3.*`. Schema đầy đủ **chưa** xác minh; mọi truy cập phải phòng thủ khi thiếu trường.

## 6. Dùng lại cho Mini
1. Allowlist/lệnh mới: lấy payload ở mục 4, đối chiếu `api_knowledge.md`, thử có kiểm soát trước.
2. Dùng `expectedVersion` cho lệnh đổi trang bị/tiêu tài nguyên; `VERSION_CONFLICT` → GET state rồi **replan**, không retry mù. Giữ nguyên `idempotency-key` trong một lần gửi.
3. Bảng nội dung (`.bundle_cache/tables/*.json`) làm nguồn điều kiện/tên cho `game_rules.py` thay vì hardcode (ví dụ `da.hunts[].contract`, `da.pets[].hunt`, chuỗi quest `Xn`).
4. Cập nhật khi game đổi build: đóng Chrome, mở game để nạp bundle mới, chạy `python -I .bundle_cache/tools/extract.py "<Cache_Data>" <thư mục ra>`, giải nén zstd, rồi `node .bundle_cache/tools/dump.cjs <i18n.js> <ra> da tp bf _ Cv Dc bt Xn …`. Tên biến minified **đổi theo build** — dò bằng `toplevel.cjs`. (`extract.py` ghi file còn nén zstd; chạy tiếp `python -I .bundle_cache/tools/unzstd.py <thư mục ra>`.)

## 7. Giới hạn
- Tên biến (`da`, `tp`, `bf`, `_`, `Cv`, `Xn`…) chỉ đúng với build `main-Bmv0z3VX` / `i18n-DxMaxujG`.
- Một số trường gọi hàm helper nên không trích tĩnh được (`bt[].rules`, `Dc[].acts[].effects`, `ds[].make` → `{"__unresolved":true}`).
- Danh mục lệnh lấy từ UI; server có thể từ chối/khóa theo cảnh giới, sự kiện, phiên bản. Chưa gửi lệnh nào trong lần phân tích này.
