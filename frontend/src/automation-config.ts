import type { Config, IconName } from "./types";

export type AutoFlag = { key: string; label: string; description: string; risk?: boolean };
export type AutoGroup = { id: string; name: string; icon: IconName; description: string; flags: AutoFlag[] };
export const AUTO_GROUPS: AutoGroup[] = [
  { id: "cultivation", name: "Tu luyện & hành trình", icon: "compass", description: "Giữ nhịp tu hành, chọn hoạt động và điểm săn phù hợp.", flags: [
    { key: "autoMinor", label: "Lên tiểu tầng", description: "Dùng thiết lập lên tầng tự động của game khi đủ tu vi." },
    { key: "autoMinorTrial", label: "Thử thách tiểu cảnh giới", description: "Chỉ thử khi đủ điều kiện. Cách nhau ít nhất 10 phút; không đột phá lớn." },
    { key: "autoActivity", label: "Giữ hoạt động & điểm săn", description: "Áp dụng hoạt động đã chọn ở mỗi vòng tự động." },
    { key: "autoFallbackHunt", label: "Lùi điểm săn khi thua", description: "Chọn bãi dễ hơn, hoặc bế quan khi không có bãi phù hợp." },
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
    { key: "autoTitles", label: "Danh hiệu", description: "Nhận danh hiệu đã đạt; không tự mang hoặc thay danh hiệu." },
  ] },
  { id: "equipment", name: "Trang bị & túi đồ", icon: "bag", description: "Chọn trang bị và giữ túi đồ gọn gàng theo thiết lập game.", flags: [
    { key: "autoEquipBest", label: "Tự trang bị", description: "Dùng bộ chọn của game. Khóa món bạn muốn giữ trước khi bật.", risk: true },
    { key: "autoSalvage", label: "Dọn trang bị rơi", description: "Áp dụng ngưỡng phân giải hoặc bán đồ mới rơi trong game.", risk: true },
  ] },
  { id: "alchemy", name: "Đan dược", icon: "spark", description: "Luyện và dùng đan có kiểm soát; các thao tác tiêu hao cần bật riêng.", flags: [
    { key: "autoCraft", label: "Luyện đan", description: "Kiểm tra nguyên liệu, linh thạch, số lò và giới hạn tuần.", risk: true },
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
  { id: "cave", name: "Động phủ & linh điền", icon: "leaf", description: "Thu hoạch trước, gieo trồng sau; giữ lại linh thạch theo hạn mức.", flags: [
    { key: "autoFarm", label: "Quản lý linh điền", description: "Bật để chạy các tùy chọn thu hoạch / gieo trồng bên dưới.", risk: true },
    { key: "farmHarvest", label: "Thu hoạch ô chín", description: "Chỉ có tác dụng khi đã bật Quản lý linh điền." },
    { key: "farmPlant", label: "Gieo ô trống", description: "Tiêu linh thạch mua giống theo điều kiện game.", risk: true },
    { key: "farmIncludeHabitats", label: "Bao gồm sinh cảnh", description: "Chỉ gieo trong những ô sinh cảnh đã mở." },
  ] },
];
export const FLAGS = AUTO_GROUPS.flatMap((group) => group.flags);
const subordinate = new Set(["autoFallbackHunt", "autoUseBuffs", "autoUseOnlyBest", "autoUseExp", "farmHarvest", "farmPlant", "farmIncludeHabitats"]);
export const activeAutos = (config: Config) => FLAGS.filter((flag) => !subordinate.has(flag.key) && config[flag.key]);
export const configEqual = (left: Config, right: Config) => JSON.stringify(Object.keys(left).sort().map((key) => [key, left[key]])) === JSON.stringify(Object.keys(right).sort().map((key) => [key, right[key]]));
