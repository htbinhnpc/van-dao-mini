"""Reviewed static rules from the public game client, not server-side guarantees.

Source: assets/i18n-DxMaxujG.js (2026-11-04), declarations Xi, Fe,
da.hunts/da.pets and the loop extending Ia. See api_knowledge.md for hashes.
No downloaded JavaScript is executed by this application.
"""

NPC_REWARD_TIERS = (
    ("acquainted", 100), ("close", 250), ("trusted", 450),
    ("confidant", 700), ("bonded", 1000),
)

# Each group contains four pets in the public client. Levels come from Fe,
# not realm order (which also includes non-level tribulation gates).
_HUNT_GROUPS = (
    (16, 20, ("Bích Nhĩ Linh Thỏ", "Thiết Trảo Sơn Ly", "Thanh Đằng Mộc Miêu", "Kim Giáp Trùng")),
    (20, 40, ("Băng Nha Linh Xà", "Hỏa Vĩ Điêu", "Mặc Văn Linh Lộc", "Huyết Giác Tê")),
    (24, 60, ("Hàn Phách Ngọc Thiềm", "Tử Điện Ưng", "Dạ Mục Hồn Bức", "Thạch Tích Xuyên Sơn")),
    (28, 90, ("Liệt Diễm Toan Nghê", "Tịnh Liên Bạch Lộ", "Song Sinh Ảnh Miêu", "Huyền Âm Minh Điệp")),
    (36, 120, ("Kim Cương Ma Viên", "Lưu Sa Huyễn Hạt", "Cấm Văn Thiên Chu", "Thương Vũ Lôi Bằng")),
    (42, 160, ("Tinh Hỏa Kỳ Lân", "U Thủy Giác Giao", "Toái Tinh Cốt Lang", "La Sát Hồn Sư")),
    (50, 220, ("Thôn Khoáng Cổ Ngạc", "Nghịch Triều Hải Mã", "Cửu Nhĩ Linh Hầu", "Táng Nguyệt Minh Nga")),
    (54, 280, ("Hư Không Du Ngư", "Tinh Giáp Bàn Long", "Chấp Niệm Mộng Lộc", "Tịch Lôi Thần Thiềm")),
    (62, 360, ("Thiên Cấm Huyền Xà", "Nhân Quả Huyền Ô", "Luân Hồi Kim Thiền", "Phệ Ảnh Ma Bằng")),
    (66, 480, ("Cổ Đạo Thạch Hống", "Quy Khư Hư Bạng", "Văn Thú Tinh Vực", "Hỗn Nguyên Giới Kình")),
)

HUNT_TARGETS = {
    pet_id: {
        "id": pet_id, "name": name, "reqLevel": level,
        "contractSeals": seals, "huntId": f"x2_hunt_{group + 1:02d}",
    }
    for group, (level, seals, names) in enumerate(_HUNT_GROUPS)
    for offset, name in enumerate(names)
    for pet_id in (f"x2_pet_{group * 4 + offset + 1:03d}",)
}
