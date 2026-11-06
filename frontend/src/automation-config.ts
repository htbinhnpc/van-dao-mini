import type { Config, IconName } from "./types";

export type AutoFlag = { key: string; label: string; description: string; risk?: boolean };
export type AutoGroup = { id: string; name: string; icon: IconName; description: string; flags: AutoFlag[] };
export const AUTO_GROUPS: AutoGroup[] = [
  { id: "cultivation", name: "Tu luyện & hành trình", icon: "compass", description: "Giữ nhịp tu hành, chọn hoạt động và điểm săn phù hợp.", flags: [
    { key: "autoMinor", label: "Lên tiểu tầng", description: "Dùng thiết lập lên tầng tự động của game khi đủ tu vi." },
    { key: "autoMinorTrial", label: "Thử thách tiểu cảnh giới", description: "Chỉ thử khi đủ điều kiện. Cách nhau ít nhất 10 phút; không đột phá lớn." },
    { key: "autoMajorBreakthrough", label: "Tự đột phá đại cảnh giới", description: "Tự luyện đan cần thiết, chuẩn bị phù/đan bảo hiểm, nhận nhiệm vụ bắt buộc đã xong, vượt thử thách rồi đột phá. Có thể mất 20% vật liệu đánh dấu và tu vi khi thua. Không tự mua, chọn nhánh truyện, hóa phàm hay đánh cửa Chứng đạo.", risk: true },
    { key: "majorUseInsurance", label: "Yêu cầu bảo hiểm đột phá", description: "Nếu có rủi ro mất tu vi: chỉ đột phá khi có một phù/đan/trận bảo hiểm. Tiêu cả khi thành công; không bảo vệ vật liệu hoặc trận thử thách." },
    { key: "majorAllowTopUp", label: "Cho phép Bổ Khuyết Đan", description: "Tự luyện và tiêu một viên đúng loại khi tu vi đạt ngưỡng 85/90/95% của game. Không bù bằng linh thạch hay tự mua.", risk: true },
    { key: "autoActivity", label: "Giữ hoạt động & điểm săn", description: "Áp dụng hoạt động đã chọn ở mỗi vòng tự động. Săn yêu thú sẽ chọn bãi cho nhiều tu vi nhất trong số bãi đã mở và đủ cấp tối thiểu." },
    { key: "autoFallbackHunt", label: "Lùi điểm săn khi thua", description: "Khi game báo thua ở bãi, tạm bỏ bãi đó (30 phút, hoặc sớm hơn khi lực chiến tăng 10%) và chọn bãi nhiều tu vi kế tiếp; hết bãi thì bế quan." },
    { key: "autoBoss", label: "Đánh boss khu vực", description: "Chỉ đánh lại boss đã vượt, đủ cấp và hết hồi chiêu.", risk: true },
  ] },
  { id: "rewards", name: "Nhiệm vụ & phần thưởng", icon: "scroll", description: "Nhận những phần thưởng bạn đã hoàn thành điều kiện.", flags: [
    { key: "autoQuests", label: "Nhiệm vụ chính", description: "Nhận các nhiệm vụ ở trạng thái có thể nhận thưởng." },
    { key: "autoDaily", label: "Mốc ngày", description: "Tôn trọng giới hạn nhận thưởng ngày của game." },
    { key: "autoWeekly", label: "Mốc tuần", description: "Nhận nhiệm vụ tuần đã hoàn tất." },
    { key: "autoAchievements", label: "Thành tựu", description: "Nhận các thành tựu đã đạt mốc." },
    { key: "autoMail", label: "Thư có quà", description: "Nhận quà trong thư khi có thư chưa nhận." },
    { key: "autoX2Daily", label: "Quà mở rộng ngày", description: "Nhận phần thưởng ngày của bản mở rộng." },
    { key: "autoSectTasks", label: "Nhiệm vụ tông môn", description: "Chỉ nhận thưởng; không quyên góp hay tiêu vật tư làm nhiệm vụ." },
    { key: "autoSeasonTasks", label: "Nhiệm vụ lễ hội", description: "Chỉ nhận mốc đã xong; không tự đổi lễ phù." },
    { key: "autoEncounter", label: "Kỳ ngộ bí cảnh", description: "Tự chọn thưởng kỳ ngộ (khoảng 400 chu kỳ săn một lần, chờ tối đa 3), ưu tiên cảm ngộ; kỳ ngộ không có cảm ngộ thì chọn phần thưởng không tốn vật phẩm.", risk: true },
    { key: "encounterAllowCost", label: "Cho phép tiêu vật phẩm để lấy cảm ngộ", description: "Hạc bị thương tốn 5 Linh thảo, Tu sĩ hấp hối tốn 1 Tụ Linh Đan. Tắt thì chỉ chọn phương án không tốn gì. Chỉ có tác dụng khi đã bật Kỳ ngộ." },
    { key: "autoTitles", label: "Danh hiệu", description: "Nhận danh hiệu đã đạt; việc đeo do tùy chọn riêng bên dưới." },
    { key: "autoEquipTitle", label: "Tự đeo danh hiệu tốt nhất", description: "Chỉ đeo danh hiệu đã sở hữu có sát thương cao nhất cho hệ đang chơi. Hệ vật lý dùng Công, hệ pháp thuật dùng Pháp công; danh hiệu bạo kích chỉ được chấm khi biết crit/critDmg. Thiếu dữ liệu thì không đổi.", risk: true },
  ] },
  { id: "equipment", name: "Trang bị & túi đồ", icon: "bag", description: "Trang bị theo game, dọn túi bằng bộ lọc Mini có kiểm soát.", flags: [
    { key: "autoEquipBest", label: "Tự trang bị", description: "Dùng bộ chọn game rồi so lại ở cùng mức cường hóa có thể chuyển. Chỉ đổi thêm khi không giảm dòng chỉ số/bonus bộ; có thể tiêu phí chuyển cường hóa. Khóa món muốn giữ trước khi bật.", risk: true },
    { key: "autoCleanup", label: "Dọn túi Mini", description: "Mặc đồ mạnh nhất theo game, chuyển cường hóa cao nhất cùng ô (có phí), rồi dọn đồ không mặc trong bộ lọc; không giữ 1 bản/mẫu. Bảo vệ đồ khóa/yêu thích và cường hóa chưa chuyển được.", risk: true },
    { key: "autoSalvage", label: "Dọn đồ rơi gốc (cũ)", description: "Chỉ để tương thích thiết lập cũ. Tự tắt khi bật Dọn túi Mini; không bật cả hai bộ dọn.", risk: true },
  ] },
  { id: "alchemy", name: "Chế tạo & đan dược", icon: "spark", description: "Ưu tiên nhiệm vụ/đột phá, cày tuần tự 4 nghề, rồi sản xuất mỗi lò một món.", flags: [
    { key: "autoCraft", label: "Tự chế tạo", description: "Có thể tiêu linh thạch và nguyên liệu cho cả 4 nghề. Tôn trọng sàn tài nguyên, lò trống và giới hạn tuần.", risk: true },
    { key: "craftMastery", label: "Cày tay nghề", description: "Dồn lò trống cho một nghề chưa max; tính lại khi lên cấp. Chỉ dùng tài nguyên dư và ngân sách cày/ngày.", risk: true },
    { key: "craftProduce", label: "Sản xuất sau khi max", description: "Chỉ khi cả 4 nghề có next=null: mỗi lò một công thức khác nhau, hợp cấp/hệ tu và trần tồn kho.", risk: true },
    { key: "autoUse", label: "Dùng đan", description: "Tối đa một đan mỗi vòng, không vượt thời lượng buff.", risk: true },
    { key: "autoUseBuffs", label: "Cho phép đan tăng tốc", description: "Chỉ có tác dụng khi đã bật Dùng đan." },
    { key: "autoUseOnlyBest", label: "Giữ buff tốt nhất", description: "Tránh dùng thêm khi buff cùng loại vẫn còn hiệu lực." },
    { key: "autoUseExp", label: "Đan tu vi trực tiếp", description: "Có thể tiêu vật phẩm quý. Chỉ có tác dụng khi đã bật Dùng đan.", risk: true },
  ] },
  { id: "companions", name: "Linh thú & đạo hữu", icon: "users", description: "Săn khế ấn, thu nhận linh thú và duy trì thiện cảm mỗi ngày.", flags: [
    { key: "autoPetAdopt", label: "Thu nhận linh thú", description: "Tối đa một linh thú đủ điều kiện mỗi vòng; có thể tiêu khế ấn.", risk: true },
    { key: "autoHunt", label: "Săn khế ấn", description: "Tiêu lượt săn cho đúng linh thú mục tiêu; không mua thêm lượt.", risk: true },
    { key: "autoNpcTalk", label: "Trò chuyện đạo hữu", description: "Tối đa hai đạo hữu mỗi vòng, lấy thiện cảm lần đầu ngày." },
    { key: "autoNpcRewards", label: "Quà thiện cảm", description: "Nhận mốc đã đạt, không tặng quà hay tự chọn quan hệ." },
  ] },
  { id: "arena", name: "Đấu trường", icon: "sword", description: "Chỉ đấu hạng với đối thủ yếu hơn bạn một khoảng lực chiến; không có đối thủ phù hợp thì làm mới danh sách.", flags: [
    { key: "autoArena", label: "Tự đấu hạng đấu trường", description: "Chỉ đánh khi lực chiến của bạn cao hơn đối thủ cùng nhóm ít nhất mức đã đặt. Không luận bàn, không đổi điểm đấu trường.", risk: true },
  ] },
  { id: "cave", name: "Động phủ & linh điền", icon: "leaf", description: "Nâng phòng theo tài nguyên dư, thu hoạch trước rồi gieo trồng; giữ lại linh thạch theo hạn mức.", flags: [
    { key: "autoCaveUpgrade", label: "Tự nâng phòng động phủ", description: "Ưu tiên phòng mà nhiệm vụ đang làm cần, rồi theo thứ tự đã chọn. Mỗi lúc một phòng, không dùng rush và không vượt sàn dự trữ.", risk: true },
    { key: "autoFarm", label: "Quản lý linh điền", description: "Bật để chạy các tùy chọn thu hoạch / gieo trồng bên dưới.", risk: true },
    { key: "farmHarvest", label: "Thu hoạch ô chín", description: "Chỉ có tác dụng khi đã bật Quản lý linh điền." },
    { key: "farmPlant", label: "Gieo ô trống", description: "Tiêu linh thạch mua giống theo điều kiện game.", risk: true },
    { key: "farmIncludeHabitats", label: "Bao gồm sinh cảnh", description: "Chỉ gieo trong những ô sinh cảnh đã mở." },
  ] },
];
export const FLAGS = AUTO_GROUPS.flatMap((group) => group.flags);
const subordinate = new Set(["majorUseInsurance", "majorAllowTopUp", "craftMastery", "craftProduce", "encounterAllowCost", "autoFallbackHunt", "autoUseBuffs", "autoUseOnlyBest", "autoUseExp", "farmHarvest", "farmPlant", "farmIncludeHabitats"]);
export const activeAutos = (config: Config) => FLAGS.filter((flag) => !subordinate.has(flag.key) && config[flag.key]);
export const configEqual = (left: Config, right: Config) => JSON.stringify(Object.keys(left).sort().map((key) => [key, left[key]])) === JSON.stringify(Object.keys(right).sort().map((key) => [key, right[key]]));
