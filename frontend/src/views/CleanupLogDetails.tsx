import { display } from "../lib";
import type { LogEntry } from "../types";

const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string").slice(0, 60) : [];
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const statuses: Record<string, string> = { started: "Đã ghi nhận yêu cầu; đang chờ kết quả game", succeeded: "Game xác nhận hoàn tất", partial: "Game xác nhận một phần; không tự gửi lại", uncertain: "Chưa rõ kết quả; đồng bộ game, không tự gửi lại", blocked: "Đã chặn trước khi gửi lệnh", skipped: "Không có món phù hợp; không gửi lệnh", configured: "Đã lưu tùy chọn; chưa chạy dọn" };

export function cleanupLogSearch(log: LogEntry): string {
  if (!["cleanup.manual", "item.dispose", "cleanup.config"].includes(log.action)) return "";
  const details = record(log.details);
  return [...strings(details.itemIds), ...(Array.isArray(details.items) ? details.items.slice(0, 60).map((item) => display(record(item).name)) : [])].join(" ");
}

export function CleanupLogDetails({ log }: { log: LogEntry }) {
  if (!["cleanup.manual", "item.dispose", "cleanup.config"].includes(log.action) || !log.details) return null;
  const data = record(log.details), rules = record(data.rules);
  const ids = strings(data.itemIds), removed = strings(data.removedIds), remaining = strings(data.remainingIds);
  const items = (Array.isArray(data.items) ? data.items.slice(0, 60) : []).map(record);
  const confirmation = data.confirmation === "skipped" ? "Bỏ hỏi xác nhận (đã bật riêng)" : data.confirmation === "not_required" ? "Auto — không hỏi từng lần" : data.confirmation === "dialog" ? "Có hộp xác nhận" : "—";
  return <details className="cleanup-log-details"><summary>Chi tiết dọn đồ</summary><dl>
    <div><dt>Kết quả</dt><dd>{statuses[String(data.status)] || "Chưa rõ"}</dd></div>
    {data.source != null && <div><dt>Nguồn</dt><dd>{data.source === "autoCleanup" ? "Tự động theo vòng" : data.source === "quick" ? "Tự chọn và dọn ngay" : "Dọn danh sách đã chọn"}</dd></div>}
    {data.confirmation != null && <div><dt>Xác nhận</dt><dd>{confirmation}</dd></div>}
    {(data.mode != null || rules.mode != null) && <div><dt>Cách xử lý</dt><dd>{(data.mode || rules.mode) === "sell" ? "Bán lấy linh thạch" : "Phân giải"}</dd></div>}
    {data.stateVersionBefore != null && <div><dt>State version</dt><dd>{display(data.stateVersionBefore)} → {data.stateVersionAfter == null ? "chưa xác nhận" : display(data.stateVersionAfter)}</dd></div>}
    {Object.keys(rules).length > 0 && <div><dt>Bộ lọc</dt><dd>Phẩm tối đa: {display(rules.maxRarity)} · tier: {rules.maxTier === 0 ? "không giới hạn" : display(rules.maxTier)} · {rules.keepPerDefinition === 0 ? "chỉ giữ đồ đang mặc (và đồ được bảo vệ)" : `giữ/mẫu: ${display(rules.keepPerDefinition)}`} · tối đa: {display(rules.maxItems)} món · vị trí: {strings(rules.slots).join(", ") || "tất cả"}</dd></div>}
    {data.cleanupSkipConfirmation != null && <div><dt>Bỏ hỏi xác nhận</dt><dd>{data.cleanupSkipConfirmation === true ? "Bật" : "Tắt"}</dd></div>}
    {data.autoCleanup != null && <div><dt>Auto dọn</dt><dd>{data.autoCleanup === true ? "Bật" : "Tắt"}</dd></div>}
    {ids.length > 0 && <div><dt>ID yêu cầu ({ids.length})</dt><dd><code>{ids.join(", ")}</code></dd></div>}
    {Array.isArray(data.removedIds) && <div><dt>Đã dọn ({removed.length})</dt><dd><code>{removed.join(", ") || "Chưa món nào"}</code></dd></div>}
    {remaining.length > 0 && <div><dt>Còn trong túi</dt><dd><code>{remaining.join(", ")}</code></dd></div>}
  </dl>{items.length > 0 && <ul>{items.map((item, index) => <li key={index}><b>{display(item.name)}</b><code>ID: {display(item.id)} · Mẫu: {display(item.defId)} · Giữ: {display(item.keptItemId)}</code></li>)}</ul>}</details>;
}
