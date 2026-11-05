# Vấn Đạo — Kỹ năng, 5 tông môn và gợi ý build (từ bundle game gốc)

Bổ sung cho `game_bundle_knowledge.md`. Nguồn: bảng kỹ năng/nội tại/tâm pháp/pháp bảo trong `i18n-DxMaxujG.js` (Chrome cache, build `main-Bmv0z3VX`), phân tích tĩnh. Số liệu dưới đây là **hệ số hiển thị phía client**; công thức cuối cùng (Công, Sinh lực, kháng, tốc độ đánh…) do server quyết định.

> **Về “lực chiến dự kiến”:** client **không** chứa công thức `power`; con số lực chiến thật do server trả (`power` trong state/hồ sơ, UI ghi rõ “chỉ là chỉ báo ước tính, thắng thua do mô phỏng quyết định”). Vì vậy mục 4 là **chỉ số tương đối do mình tự mô phỏng** từ hệ số kỹ năng (Kiếm tu = 100), dùng để so sánh các tông với nhau, **không phải** lực chiến tuyệt đối. Muốn có số thật cần đọc `power` từ tài khoản và hiệu chỉnh.

## 1. Khung hệ thống

- **5 tông môn = 5 build**: Thanh Vân Kiếm Các (Kiếm tu), Lôi Đình Cốc (Lôi pháp), Thiết Sơn Môn (Luyện thể), Hồn Đăng Các (Hồn tu), Cấm Văn Sơn Trang (`sect_cam_van`, Cấm trận). Mỗi build có **5 chủ động + 3 nội tại** (+ 1 tâm pháp nhập môn, 1 tâm pháp thượng thừa, 1 pháp bảo, linh thú hỗ trợ). Chiêu khởi đầu của tông: Thanh Vân → nội tại Kiếm Tâm; Lôi Đình → Lôi Tiễn; Thiết Sơn → Thiết Cốt; Hồn Đăng → Dẫn Hồn; Cấm Văn → Cấm Ấn.
- **Bậc trong tông**: Ngoại môn (0 cống hiến) → Nội môn (600) → Chân truyền (3.000). Có cửa hàng tông môn (theo bậc, giới hạn tuần).
- **Vòng đánh tự động**: kỹ năng chạy theo `loadout.rules` — mỗi quy tắc = `{skillId, condition}`. Điều kiện: `always, self_hp_below, target_hp_below, target_has_status, target_lacks_status, enemy_count_at_least, enemy_casting, self_lacks_status, self_mp_above, self_has_shield, self_lacks_shield, self_debuffed`. Nhắm mục tiêu: `enemy_first, enemy_lowest_hp, enemy_highest_hp, enemy_marked, self`. Đánh thường = 100% Công, miễn phí. Lệnh liên quan: `skills.set`, `loadout.set`, `rules.set`, `preset.clear`, `skill.learn`.
- **Cơ chế “dấu → nổ”**: mỗi build có 1 dấu (Kiếm Ấn / Nhiễm điện / Hồn Ấn / Cấm Ấn) tăng sát thương nhận vào, rồi chiêu cuối (`finisher`) **tiêu hết dấu** để cộng thêm sát thương mỗi tầng. Luyện thể không có dấu, đi theo Sinh lực.
- **Boss**: chỉ chịu **nửa thời lượng** choáng/cấm kỹ năng và miễn khống chế 6 giây sau đó → khống chế kém giá trị khi đánh boss.
- **Kỹ năng Kiếm (đã biết cách mở)** qua chuỗi nhiệm vụ: Kiếm Ấn (lv 3), Kiếm Thể (lv 5), Hồi Phong (hạ boss Thanh Khê), Phá Giáp (lv 9), Nhất Tuyến Trảm (lv 12). Cách mở kỹ năng của 4 tông còn lại **chưa xác định được từ client** (qua `skill.learn`/tông môn).
- **Tâm pháp** (`tech.*`): nhập môn (lv 16; 6.000 linh thạch + 300 cống hiến) và thượng thừa (lv 24; 60.000 linh thạch + 1.500 cống hiến); nâng cấp tốn `400·n·(cấp+1)²` linh thạch (n=1/4/12 theo bậc) và cảm ngộ `cấp·n` từ bậc lv16 trở lên. Chỉ số cộng nằm ở bảng mục 3. Hai trường `ratePct/ratePerLevel` (6/2 và 14/3) có vẻ là tốc độ tu vi — suy đoán, chưa xác minh.

## 2. Bảng kỹ năng theo tông

Ký hiệu: **D**=sát thương, **K**=khống chế, **H**=hồi phục, **Kh**=khiên/giảm sát thương, **B**=buff/debuff, **Đ**=đặt dấu. `MP/CD/Niệm` đơn vị: linh lực / giây / giây. Hệ số theo Công (vật lý: Công; pháp thuật: Công pháp thuật).

### Thanh Vân Kiếm Các — Kiếm tu (vật lý, mục tiêu đơn)
| Kỹ năng | MP/CD/Niệm | Vai trò | Tác dụng |
|---|---|---|---|
| Phi Kiếm | 8/4/0 | D | 170% Công, 1 mục tiêu |
| Kiếm Ấn | 10/7/0 | D·Đ | 80% Công + 1 Kiếm Ấn (12 s, tối đa 3); mỗi ấn +6% sát thương nhận |
| Hồi Phong | 14/9/0 | D (diện rộng) | 95% Công lên mọi địch |
| Phá Giáp | 12/11/0 | K·B | 100% Công, −30% Phòng ngự 8 s, choáng 1 s (ngắt niệm) |
| Nhất Tuyến Trảm | 24/16/0,4 | D (kết liễu) | 240% Công, tiêu dấu: +60%/ấn; mục tiêu <30% HP ×1,4 |
Nội tại: Kiếm Thể (+8% bạo kích; đòn thường thứ 3 ×1,5), Kiếm Tâm (+10% xuyên giáp), Tật Phong (+8% tốc độ, +3% né).
Pháp bảo: Thanh Phong Kiếm Hoàn — 160% Công lên mọi địch + Kiếm Ấn, hồi 20 s. Tâm pháp: Thanh Vân Kiếm Quyết (+6% Công, +1% bạo) → Kiếm Tâm Thông Minh Quyết (+10% Công, +2% xuyên giáp).

### Lôi Đình Cốc — Lôi pháp (pháp thuật, diện rộng + khống chế)
| Kỹ năng | MP/CD/Niệm | Vai trò | Tác dụng |
|---|---|---|---|
| Lôi Tiễn | 8/3,5/0 | D·Đ | 160% Công PT + 1 Nhiễm điện (8 s, tối đa 3); mỗi tầng +5% sát thương nhận |
| Dẫn Điện | 12/8/0 | D (AoE)·Đ | 75% lên mọi địch + 1 Nhiễm điện mỗi mục tiêu |
| Lôi Võng | 14/11/0 | K (AoE) | 50% lên mọi địch, làm chậm 5 s, **cấm kỹ năng 2 s** (ngắt niệm) |
| Tĩnh Điện Hộ Thể | 10/16/0 | Kh | Khiên 14% HP tối đa 8 s, phản 25% sát thương trực tiếp |
| Thiên Lôi Giáng | 26/18/0,8 | D (kết liễu) | 260% Công PT, tiêu Nhiễm điện: +50%/tầng |
Nội tại: Lôi Tâm (+12% Công PT; đòn thường 25% gây Nhiễm điện), Tụ Điện (+25% Linh lực, +8% giảm hồi chiêu), Dư Chấn (+5% bạo, +8% xuyên kháng).
Pháp bảo: Tử Điện Lôi Châu — 130% lên mọi địch + 2 Nhiễm điện, 20 s. Tâm pháp: Lôi Đình Dẫn Khí Thuật (+6% Công PT, +6% Linh lực) → Cửu Tiêu Lôi Quyết (+10% Công PT, +2% giảm hồi chiêu).

### Thiết Sơn Môn — Luyện thể (đỡ đòn, sát thương theo Sinh lực)
| Kỹ năng | MP/CD/Niệm | Vai trò | Tác dụng |
|---|---|---|---|
| Thiết Cốt | 8/14/0 | Kh·B | +40% Phòng ngự 8 s |
| Chấn Sơn | 12/8/0 | D (AoE)·K | 60% Công + 3% HP tối đa, làm chậm 4 s |
| Hộ Mạch | 10/15/0 | H | Hồi 14% HP tối đa, gỡ tối đa 2 trạng thái xấu (đặt điều kiện “HP thấp”/“đang bị debuff”) |
| Phản Chấn | 10/16/0 | Kh (phản) | 6 s phản 40% sát thương trực tiếp nhận vào (sát thương chuẩn) |
| Phá Trận Quyền | 16/10/0 | D·K·B | 130% Công + 7% HP tối đa, −30% Phòng ngự 6 s, choáng 0,8 s |
Nội tại: Cường Thể (+15% HP), Bất Động (+12% Thủ, +5% Kháng), Phản Kích (đòn thường thứ 4 ×1,8).
Pháp bảo: Huyền Thiết Ấn — 80% Công + 5% HP, choáng 1,2 s, khiên 16% HP, 22 s. Linh thú: Huyền Giáp Quy (+5% Thủ; khiên 12% HP cho đồng đội <55% HP, 14 s). Tâm pháp: Thiết Sơn Đoán Thể Công (+7% HP, +4% Thủ) → Bất Hoại Kim Thân Quyết (+12% HP, +6% Thủ). Cổ Thần/“thể” còn có hướng x2 (Mục 5).

### Hồn Đăng Các — Hồn tu (đánh dài, boss, hút máu)
| Kỹ năng | MP/CD/Niệm | Vai trò | Tác dụng |
|---|---|---|---|
| Dẫn Hồn | 8/4/0 | D·Đ | 130% Công PT + 1 Hồn Ấn (10 s, tối đa 3); mỗi ấn +5% sát thương nhận |
| Hồn Ấn | 12/9/0 | D·Đ·B | 60% + 2 Hồn Ấn + Suy hồn 6 s (−20% Công địch) |
| U Ảnh | 10/10/0 | D (DoT) | Hồn ảnh 8 s: mỗi giây 30% Công, cộng dồn tối đa 2 |
| Nhiếp Phách | 14/12/0 | K | 100% + **cấm kỹ năng 2,5 s** |
| Hồn Bạo | 24/16/0,6 | D (kết liễu) | 220% Công PT, tiêu Hồn Ấn: +60%/ấn |
Nội tại: Hồn Lực (+10% Công PT, **hồi 4% sát thương gây ra**), Âm Hồn (+8% Kháng, +15% Linh lực), Truy Hồn (đòn thường 30% khắc Hồn Ấn).
Pháp bảo: U Minh Dẫn Hồn Đăng — 120% lên mọi địch, Hồn Ấn từng mục tiêu, hồi 4% HP, 20 s. Linh thú: Linh Hồ Vân Vĩ (+3% né; hồi 10% HP đồng đội <65%, 10 s). Tâm pháp: Hồn Đăng Tịnh Tâm Quyết (+5% Công PT, +1,5% Kháng) → U Minh Dưỡng Hồn Kinh (+9% Công PT, +3% Kháng).

### Cấm Văn — Cấm trận (đánh lâu, nổ diện rộng)
| Kỹ năng | MP/CD/Niệm | Vai trò | Tác dụng |
|---|---|---|---|
| Cấm Ấn | 7/3/0 | D·Đ | 150% Công PT + 2 Cấm Ấn (12 s, tối đa 6); mỗi ấn +5% sát thương nhận |
| Tụ Linh Trận | 12/18/0 | B | 10 s: +15% Công vật lý và Công PT |
| Phong Mạch | 12/12/0 | K | 60% Công PT, làm chậm 5 s, cấm kỹ năng 1,5 s |
| Liên Hoàn Cấm | 14/10/0 | D (AoE)·Đ | 70% lên mọi địch + 2 Cấm Ấn mỗi mục tiêu |
| Phá Cấm Bạo | 28/12/0,8 | D (AoE kết liễu) | 180% lên mọi địch, tiêu Cấm Ấn: **+90%/ấn** |
Nội tại: Trận Tâm (+10% giảm hồi chiêu, +12% Công PT), Cố Trận (+10% Thủ, +8% HP, +20% Linh lực), Cấm Văn (+8% xuyên kháng PT, +5% bạo; đòn thường 30% đặt Cấm Ấn).
Pháp bảo: Cửu Cung Trận Bàn — 100% lên mọi địch, 2 Cấm Ấn mỗi mục tiêu, khiên 10% HP, 22 s. Tâm pháp: Trận Văn Sơ Giải (+5% Công PT, +1,5% giảm hồi chiêu) → Vạn Tượng Trận Kinh (+9% Công PT, +5% Thủ).

## 3. Gợi ý theo tông (vòng đánh, nội tại, đối tượng phù hợp)

Thứ tự ưu tiên là cách dùng hợp lý theo hệ số/cd (đề xuất, hãy thử trong trận), cấu hình qua `loadout.rules`.

| Tông | Vòng ưu tiên (trên xuống) | 3 nội tại | Mạnh | Yếu | Hợp với |
|---|---|---|---|---|---|
| **Thanh Vân (Kiếm)** | Nhất Tuyến Trảm khi mục tiêu ≥2 Kiếm Ấn → Kiếm Ấn (nếu <3 ấn) → Phá Giáp (boss/đánh ngắt) → Hồi Phong khi ≥2 địch → Phi Kiếm → đánh thường | Kiếm Thể, Kiếm Tâm, Tật Phong | Sát thương đơn mục tiêu cao, MP/giây thấp nhất; nhiệm vụ dẫn dắt mở sẵn kỹ năng | Gần như không hồi/khiên/khống chế; nhờ đúng nhịp ấn | Người mới, săn boss/đơn mục tiêu, nhiệm vụ boss vùng |
| **Lôi Đình (Lôi)** | Thiên Lôi Giáng khi ≥2 tầng điện → Dẫn Điện (≥2 địch) → Lôi Võng (khi địch niệm/nhóm) → Lôi Tiễn; Tĩnh Điện khi HP thấp | Lôi Tâm, Tụ Điện, Dư Chấn | AoE tốt, khống chế diện rộng, có khiên; tự dựng Nhiễm điện từ đòn thường | Tốn linh lực; nên mang pháp khí | Săn nhóm/farm nhiều quái, PvE chung |
| **Thiết Sơn (Luyện thể)** | Hộ Mạch (HP thấp / bị debuff) → Thiết Cốt khi vào đánh/boss → Phá Trận Quyền → Chấn Sơn (≥2 địch) → Phản Chấn khi boss đánh mạnh | Cường Thể, Bất Động, Phản Kích | Chịu đòn nhất (HP/Thủ/khiên/hồi), nhẹ MP | Sát thương thấp nhất, dọn nhóm chậm | AFK dài/offline, boss khó, thiếu trang bị |
| **Hồn Đăng (Hồn)** | Hồn Bạo khi ≥3 Hồn Ấn → Hồn Ấn (suy yếu) → Nhiếp Phách (ngắt niệm) → Dẫn Hồn; U Ảnh luôn trên mục tiêu máu cao | Hồn Lực, Âm Hồn, Truy Hồn | Có hút máu, DoT, suy yếu địch, bền hơn Kiếm/Lôi | Ít AoE; sát thương trung bình | Boss/trận dài, đánh bền không cần dọn nhóm |
| **Cấm Văn (Cấm trận)** | Phá Cấm Bạo khi ≥4 Cấm Ấn → Liên Hoàn Cấm (≥2 địch) → Cấm Ấn (tích 2 ấn/3 s) → Phong Mạch; Tụ Linh Trận mở đầu mỗi trận | Trận Tâm, Cố Trận, Cấm Văn | Tiềm năng sát thương cao nhất, nhất là AoE; giảm hồi chiêu; có khiên pháp bảo | Mở đầu chậm; ngốn nhiều linh lực nhất | Nhóm đông, trận dài, ai có nguồn linh lực |

Lưu ý chung: pháp bảo và linh thú chọn **cùng hệ** (kiếm → Kiếm Hoàn; lôi → Lôi Châu; thể → Thiết Ấn + Huyền Giáp Quy; hồn → Dẫn Hồn Đăng + Linh Hồ; trận → Trận Bàn). Linh thú hồi/khiên chỉ kích hoạt khi đồng đội thấp máu nên không thay được hồi phục chủ động.

## 4. Lực chiến dự kiến (chỉ số tương đối do mô phỏng)

Mô phỏng 120 s, 1 hành động/giây, đúng ưu tiên ở mục 3, **đã gồm** nội tại + tâm pháp thượng thừa + pháp bảo, **chưa gồm** trang bị, linh thú, cảnh giới, MP thực tế, kháng/né của địch. Hệ số cộng trên cùng thang để so sánh; Kiếm tu (1 mục tiêu) = 100. Giả định: bạo kích tăng sát thương theo `critDmg` mặc định 1,5; xuyên giáp/kháng hiệu lực một nửa; Sinh lực ≈ 5× Công (chỉ ảnh hưởng hệ số theo Sinh lực của Luyện thể).

| Tông | Dame 1 mục tiêu | Dame 3 mục tiêu | Chỉ số chung* | MP/giây | Khống chế† | Hồi+khiên (%HP/phút) | Sức bền cộng thêm |
|---|---:|---:|---:|---:|---|---:|---|
| Cấm Văn | **125** | **207** | **166** | 7,9 | Trung bình | ~25 | +8% HP, +15% Thủ |
| Thanh Vân | 100 | 120 | 110 | 5,8 | Thấp | 0 | — |
| Lôi Đình | 87 | 119 | 103 | 7,0 | **Cao** (AoE 2 s cấm + chậm) | ~56 | — |
| Hồn Đăng | 88 | 94 | 91 | 6,7 | Thấp–TB | ~21 (hút máu) | +11% Kháng |
| Thiết Sơn | 50 | 61 | 56 | 5,0 | TB (choáng ngắn, chậm) | ~96 | **+27% HP, +18% Thủ, +5% Kháng** |

\* Chỉ số chung = trung bình dame 1 mục tiêu và 3 mục tiêu. † Khống chế là mức độ phủ tương đối (ngắt niệm/cấm/choáng/chậm), không phải tỉ lệ thật.

Cách đọc: thứ hạng sát thương **Cấm Văn > Thanh Vân > Lôi Đình ≈ Hồn Đăng > Thiết Sơn**; thứ hạng sống sót **Thiết Sơn ≫ Hồn Đăng > Lôi Đình > Cấm Văn > Thanh Vân**. Thiết Sơn đền bù ≈ nửa sát thương bằng độ bền (và hệ số theo Sinh lực tăng theo cảnh giới). Cấm Văn đứng đầu trên giấy nhưng là kiểu “càng đánh lâu càng mạnh” và đòi nhiều linh lực; nếu linh lực không đủ, sát thương thực sẽ thấp hơn. Chỉ nên dùng để **chọn hướng**, không để tính số lực chiến thật.

## 5. Kỹ năng mở rộng V2 (`da.skills`, `da.manuals`, `Dc`)

- 12 bộ công pháp x2, mỗi bộ 5 kỹ năng (4 chủ động + 1 nội tại), tổng 60 kỹ năng `x2_skill_001..060`. Mỗi kỹ năng có MP/CD (thường 8/10, 10/14, 18/30, 12/24), điều kiện dùng, hiệu ứng (hệ số `% A`), và điểm ngộ (80–480).
- Bộ công pháp theo hướng (cảnh giới yêu cầu): Kiếm — Tàng Phong Tâm Quyết (Nguyên Anh), Đoạn Giới Thiên Kiếm Kinh (Khuy Niết); Lôi — Ngự Lôi Linh Kinh (Hóa Thần), Cửu Kiếp Lôi Điển (Không Niết); Luyện thể — Huyền Cốt Chân Pháp (Nguyên Anh), Cổ Diệu Tinh Thể Kinh (Toái Niết); Hồn — Tịch Hồn Khế Điển (Anh Biến), Vô Sinh Ngự Hồn Kinh (Không Linh); Cấm trận — Thiên Văn Cấm Lục (Vấn Đỉnh), Vạn Giới Cấm Thư (Không Huyền); Ma tu — Hắc Hà Tự Chủ Kinh (Nguyên Anh), Nghịch Mệnh Ma Đạo Lục (Không Niết).
- Bộ trang bị theo hướng (`x2_set_01..10`, bonus 2/4/6 món): Tàng Phong & Đoạn Giới (Kiếm), Thừa Lôi & Táng Lôi (Lôi), Huyền Cốt & Cổ Diệu (Luyện thể), Tịch Hồn & Vô Sinh (Hồn), Thiên Văn & Quy Tắc (Cấm trận).
- Nhánh 23 bộ “manual” (`Dc`, Tịch Diệt Sát Kiếm Lục, Thiên Kiếp Dẫn Lôi Chân Kinh, Cổ Thần Đạp Tinh Quyết, Vạn Hồn Phiên Bí Lục, Nghịch Thiên Cấm Chế Thư…) dùng 4 chiêu cùng khuôn MP/CD 8/10, 14/16, 18–20/28–30, 12/24 (chiêu 4 là phòng thủ/hộ thân). Phần hiệu ứng chi tiết gọi hàm helper nên không trích tĩnh được.

## 6. Giới hạn của tài liệu này
- Không có công thức Công/Sinh lực/tốc độ đánh/xác suất bạo; các giả định ở mục 4 chỉ để so sánh tương đối.
- Chưa biết số ô kỹ năng tối đa theo cấp, cách mở kỹ năng ngoài tuyến Kiếm, và điều kiện gia nhập tông (nhiệm vụ `q13_join_sect` chỉ ghi nhận “đã gia nhập”).
- Linh lực tối đa/hồi linh lực không nằm trong bundle nên mô phỏng không kiểm tra được kỹ năng nào hết MP.
- Mô hình mô phỏng ở `.bundle_cache/tools/estimate.cjs`; chạy lại bằng `node .bundle_cache/tools/estimate.cjs` sau khi giải nén bảng (cần `tables/_`, `tables/lt`).
