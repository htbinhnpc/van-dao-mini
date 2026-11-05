# Plan — Chế tạo: cày tay nghề tuần tự → mỗi lò 1 món hợp hệ tu

> Trạng thái: ĐỀ XUẤT (2026-11-05). Module: `src/worker/systems/craft.ts` (bước 5 "mastery filler" + bước mới), dữ liệu
> `src/worker/systems/lib/craft-data.ts`, `src/shared/data/recipes.ts`.

## 1. Yêu cầu (người dùng)

1. Chế tạo có **4 tay nghề riêng**, mỗi nghề có cấp: **Luyện đan** (alchemy), **Rèn khí** (forging), **Chế phù**
   (talisman), **Trận pháp** (array).
2. **Giai đoạn 1 — Cày cấp:** khi còn nghề chưa đạt cấp tối đa (lv10), chế tạo **tuần tự**, ưu tiên **thời gian ngắn
   nhất** để lên cấp nhanh nhất.
3. **Giai đoạn 2 — Sản xuất:** khi **cả 4 nghề** đã max, **mỗi lò chế 1 món**, ưu tiên món **phù hợp hệ tu và cấp bậc**
   của nhân vật.

## 2. Cơ chế game (đọc từ client — EXACT trừ khi ghi khác)

| Cơ chế | Giá trị | Nguồn |
|---|---|---|
| 1 mẻ hoàn thành | +1 điểm tay nghề (mọi công thức như nhau) | `craft-data.ts` header |
| Cấp tối đa | lv10 (`professions[p].next = null` ⇒ max; Luyện đan của 3 acc chính đã hiện "max") | state live |
| Điểm cần để lên cấp (tổng) | lv2: 3 · lv3: 8 · lv4: 15 · lv5: 25 · lv6: 40 · lv7: 60 · lv8: 85 · lv9: 115 · lv10: 150 | `CRAFTED_TO_REACH` (lv8 = 85 khớp live; lv9/10 SUY RA) |
| Tốc độ | nhanh hơn 3%·(cấp − 1) (lv10 = −27% thời gian) | client "Nhanh hơn 3*(level-1)%" |
| Thêm sản phẩm | lv5 +1, lv10 +2 mỗi mẻ — **không áp dụng Rèn khí** (đồ) | `extraPerBatch` |
| Số lò | `state.crafting.slots` (Đan Phòng tăng lò; acc chính hiện 3–4) | state |

### Công thức "cày" rẻ/nhanh nhất mỗi nghề

Tổng thời gian lò để đi **lv1 → lv10** (150 mẻ, đã trừ bonus tốc độ theo từng cấp ⇒ ≈ 124,5 "mẻ chuẩn"):

| Nghề | Công thức nhanh nhất | Cấp mở | 1 mẻ | Tổng thời gian lò lv1→10 | Với 4 lò | Chi phí lv1→10 |
|---|---|---|---|---|---|---|
| Luyện đan | Dưỡng Khí Đan `recipe_qi_pill` | 2 | 30 s, 0 đá, 4 linh thảo | ≈ 62 phút | ≈ 16 phút | 600 linh thảo |
| Rèn khí | Thiết kiếm `recipe_iron_sword` | 2 | 45 s, 15 đá, 6 thiết khoáng | ≈ 93 phút | ≈ 23 phút | 2.250 đá, 900 khoáng (ra đồ t1 rác → phân giải) |
| Chế phù | Tị Lôi Phù `recipe_aid_thunder_ward` | 12 | 180 s, 120 đá, 20 linh thảo + 6 thú bì | ≈ 6,2 giờ | ≈ 1,6 giờ | 18.000 đá, 3.000 thảo, **900 thú bì** |
| Trận pháp | Hộ Thân Trận Bàn `recipe_aid_guard_array` | 16 | 240 s, 200 đá, 30 khoáng + 4 hàn tinh | ≈ 8,3 giờ | ≈ 2,1 giờ | 30.000 đá, 4.500 khoáng, 600 hàn tinh |

Nút thắt thật: **thú bì** (Chế phù) và **đá** (Trận pháp, Chế phù) — không phải thời gian lò.

## 3. Giai đoạn 1 — Cày cấp tuần tự

### 3.1 Thứ tự ưu tiên trong mỗi lượt lấp lò (giữ nguyên các mức trên, cày cấp chỉ dùng lò còn trống)

1. `ctx.want.crafts` (nhiệm vụ, đột phá — critical trước)
2. Đan đột phá đại cảnh kế tiếp
3. Dưỡng Khí Đan bổ sung tồn kho (qiPillLow/qiPillTarget)
4. Trận kỳ tu luyện (charms) — khi đủ cấp
5. **Cày cấp (mới)** — mục 3.2
6. Giai đoạn 2 (khi cả 4 nghề max) — mục 4

### 3.2 Chọn nghề: "thời gian ngắn nhất để lên cấp"

- Với mỗi nghề chưa max: `t_next = (điểm còn thiếu tới cấp kế) × thời gian mẻ nhanh nhất × (1 − 3%·(cấp−1)) / số lò`.
- **Chọn nghề có `t_next` nhỏ nhất** và **dồn tất cả lò trống** cho nghề đó (tuần tự). Lên cấp xong → tính lại.
- Hệ quả: Luyện đan & Rèn khí (30–45 s/mẻ) lên rất nhanh trước; Chế phù/Trận pháp (3–4 phút/mẻ) đi sau.
- Nghề **bị chặn** (thiếu cấp nhân vật mở công thức, thiếu nguyên liệu dư, thiếu đá mức "comfort") ⇒ bỏ qua, xét nghề
  kế tiếp trong danh sách; lý do hiện ở trạng thái lò.
- Tuỳ chọn thay thế (pref `craftLevelOrder`): `"fastest"` (mặc định, như trên) | `"all-max-first"` (giảm tổng thời gian
  tới khi cả 4 max: nghề còn nhiều việc nhất nhận lò trước).

### 3.3 Ràng buộc tài nguyên (giữ nguyên luật hiện tại)

- Chỉ dùng **nguyên liệu dư** trên sàn (`matFloor`, dự trữ của economy/đột phá), đá qua `economy.canSpend("comfort")`.
- Ngân sách cày/ngày (pref `craftLevelDaily`, mặc định 20% đá chi được) — tránh lặp lại vụ Trận pháp lv3→7 tiêu ~15k đá
  trong vài giờ.
- Sản phẩm phụ: Thiết kiếm t1 → để module equip phân giải/vứt; Hộ Thân Trận Bàn / Tị Lôi Phù → giữ 10–30 làm bảo hiểm
  đột phá, dư thì đăng chợ (nếu có giá) hoặc dừng nghề đó khi kho đầy.
- Túi gần đầy (≥ 90%) ⇒ tạm ngừng Rèn khí.

## 4. Giai đoạn 2 — Mỗi lò 1 món hợp hệ tu & cấp bậc

Kích hoạt khi **cả 4 nghề** `next = null`. Mỗi lò chọn **một món khác nhau** (không dồn cả 4 lò vào 1 món), theo điểm:

`điểm = giá trị món / thời gian lò`, giá trị theo loại:

| Loại | Điều kiện hợp | Giá trị dùng để chấm |
|---|---|---|
| Đan tu luyện (Tụ Linh Đan, Dưỡng Khí Đan, đan theo dải cảnh giới) | dải cảnh giới của nhân vật (`pill_band`) | tu vi/giờ tăng thêm × thời gian buff |
| Đan đột phá đại cảnh kế | cảnh giới kế tiếp | chặn tiến độ ⇒ ưu tiên cao nhất khi thiếu |
| Trận kỳ tu luyện (Dẫn Linh Trận Kỳ +5% lv28, Tụ Linh Đại Trận +10% lv46) | đủ cấp | % tu vi × 120 phút/lần |
| Vũ khí/đồ **đúng dòng hệ tu** ở bậc hiện tại (Rèn khí: kiếm → `frost_blade`…, lôi → `thunder_staff`, thể → `iron_gauntlet`, hồn → `soul_lantern`, trận → công thức trận) | `weaponFits(def, build)`, `reqLevel ≤ cấp` | mức tăng sát thương (gear-opt) hoặc giá chợ nếu bán |
| Bùa/trận chiến đấu đúng hệ | chỉ khi có boss/bí cảnh dùng | % sát thương trận dài |
| Hàng bán chợ | `valueOf` có giá tin cậy, lãi sau phí ≥ chi phí | lãi ròng |

Luật: giữ trần tồn kho từng món; món chặn tiến độ (đột phá/nhiệm vụ) luôn trước; không chế công thức tốn đá mà không
khai báo spend (`FILLER_NO_STONES`).

## 5. Hiển thị (trạng thái lò & tab Chế tạo)

- Thanh tiến độ 4 nghề: cấp, điểm/điểm cần, **ETA tới cấp kế & tới max** (theo số lò, tốc độ hiện tại).
- Dòng "Giai đoạn: Cày cấp → đang dồn lò cho Rèn khí (lv4 → lv5 còn ~6 phút)" / "Giai đoạn: Sản xuất".
- Mỗi lò: món đang chế, lý do chọn, thời gian còn lại.

## 6. Cài đặt

| Pref | Mặc định | Ý nghĩa |
|---|---|---|
| `craftMastery` | bật | bật/tắt giai đoạn 1 |
| `craftLevelOrder` | `fastest` | `fastest` \| `all-max-first` |
| `craftLevelDaily` | 20% đá chi được | trần đá/ngày cho cày cấp |
| `craftProduce` | bật | bật/tắt giai đoạn 2 |

## 7. Các bước làm

1. `craft-data.ts`: bảng "công thức cày" mỗi nghề (nhanh nhất theo cấp nhân vật) + hàm `timeToNextLevel(p, slots)`.
2. `craft.ts` bước 5: thay thứ tự `PROF_WEIGHT` bằng chọn nghề `t_next` nhỏ nhất; thêm Rèn khí; ngân sách ngày; dừng
   khi túi đầy.
3. `craft.ts` bước 6 (mới): giai đoạn 2 — chấm điểm món theo bảng mục 4, mỗi lò một món.
4. Trạng thái `furnace` + UI tab Chế tạo (tiến độ, ETA, giai đoạn).
5. Kiểm thử: unit cho `timeToNextLevel` và chọn nghề (bảng số trên); chạy thật 1 acc 1 giờ, đo: điểm tay nghề/giờ, đá
   tiêu, không chiếm lò của đột phá/nhiệm vụ.

## 8. Câu hỏi mở

- Cấp tối đa có đúng **lv10** cho cả 4 nghề không (mới xác nhận Luyện đan)? Nếu nghề khác cao hơn, giai đoạn 2 chờ lâu
  hơn — có thể cho phép "giai đoạn 2 từng phần": nghề nào max thì lò của nghề đó chuyển sang sản xuất.
- Rèn khí lv cao có tác dụng gì ngoài tốc độ (phẩm chất đồ chế ra?) — chưa thấy trong client; nếu không, có thể chỉ cày
  Rèn khí khi lò rảnh hoàn toàn.
- Thú bì là nút thắt của Chế phù (900 bì tới lv10): có nên cho NV2 farm bì riêng cho việc này?
