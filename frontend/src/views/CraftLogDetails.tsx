import { display, number } from "../lib";
import type { LogEntry } from "../types";

const actions = ["craft.plan", "craft.start"];
const statuses: Record<string, string> = {
  started: "Đã ghi nhận yêu cầu; đang chờ game xác nhận",
  succeeded: "Game xác nhận đã xếp mẻ",
  blocked: "Đã chặn trước khi gửi lệnh",
  uncertain: "Chưa rõ kết quả; đồng bộ lò trước khi thử tiếp",
  deferred: "Hoãn sang vòng sau để giữ ngân sách lệnh",
  disabled: "Tự chế tạo đang tắt; không gửi lệnh",
  mastery_disabled: "Cày tay nghề đang tắt; không gửi lệnh",
  production_disabled: "Sản xuất đang tắt; không gửi lệnh",
  waiting_furnaces: "Đang chờ lò trống hoặc game kết toán",
  waiting_level: "Đang chờ đủ mẻ để lên cấp kế",
  waiting_breakthrough: "Đang chờ vật liệu/lò cho đột phá đại cảnh",
  waiting_policy: "Không có món hợp chính sách sản xuất",
  unknown: "Thiếu dữ liệu; không suy đoán",
};
const decisions: Record<string, string> = {
  ready: "Có việc có thể làm", blocked: "Tất cả lựa chọn đang bị chặn", uncertain: "Kết quả trước chưa xác nhận",
  disabled: "Tính năng đang tắt", mastery_disabled: "Cày tay nghề đang tắt", production_disabled: "Sản xuất đang tắt",
  waiting_furnaces: "Chờ lò", waiting_level: "Chờ lên cấp", waiting_breakthrough: "Chờ đột phá", waiting_policy: "Chờ chính sách",
  unknown: "Thiếu dữ liệu",
};
const scopes: Record<string, string> = {
  full: "Đầy đủ: ưu tiên → cày nghề → sản xuất", major_only: "Chỉ chuẩn bị đột phá đại cảnh", disabled: "Không chạy",
};
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const lines = (value: unknown): string[] => list(value).filter((entry): entry is string => typeof entry === "string").slice(0, 12);

export function craftLogSearch(log: LogEntry): string {
  if (!actions.includes(log.action)) return "";
  const data = record(log.details), action = record(data.action);
  const blocked = list(data.blocked).map(record);
  return [
    ...lines(data.settingLines), ...lines(data.resourceLines),
    ...blocked.flatMap((entry) => [display(entry.name), display(entry.reason), display(entry.nextStep)]),
    display(data.nextStep), display(data.reason), display(action.name), display(action.recipeId),
  ].join(" ");
}

export function CraftLogDetails({ log }: { log: LogEntry }) {
  if (!actions.includes(log.action) || !log.details) return null;
  const data = record(log.details), action = record(data.action), runtime = record(data.runtime);
  const settingLines = lines(data.settingLines), resourceLines = lines(data.resourceLines);
  const blocked = list(data.blocked).map(record).slice(0, 8);
  const scope = scopes[String(data.scope)] || "Chưa rõ";
  return <details className="cleanup-log-details craft-log-details"><summary>Chi tiết chế tạo</summary><dl>
    <div><dt>Kết quả</dt><dd>{statuses[String(data.status)] || decisions[String(data.decision)] || "Chưa rõ"}</dd></div>
    {data.scope != null && <div><dt>Phạm vi</dt><dd>{scope}</dd></div>}
    {data.decision != null && <div><dt>Quyết định</dt><dd>{decisions[String(data.decision)] || display(data.decision)}</dd></div>}
    {data.reason != null && <div><dt>Lý do</dt><dd>{display(data.reason)}</dd></div>}
    {action.name != null && <div><dt>Mẻ dự kiến</dt><dd>{display(action.name)} ×{display(action.count)} · {number(action.stones)} linh thạch</dd></div>}
    {data.stateVersionAfter != null && <div><dt>State version</dt><dd>{display(data.stateVersion)} → {display(data.stateVersionAfter)}</dd></div>}
    {(runtime.attempts != null || runtime.timeLeftMs != null) && <div><dt>Ngân sách vòng</dt><dd>Đã dùng {display(runtime.attempts)}/{display(runtime.maxCommands)} lệnh · còn {display(runtime.timeLeftMs)} ms{runtime.stopped === true ? " · vòng đã dừng" : ""}</dd></div>}
    {data.nextStep != null && <div><dt>Phương hướng</dt><dd>{display(data.nextStep)}</dd></div>}
    {settingLines.length > 0 && <div><dt>Cấu hình</dt><dd><ul>{settingLines.map((line, index) => <li key={index}>{line}</li>)}</ul></dd></div>}
    {resourceLines.length > 0 && <div><dt>Tài nguyên</dt><dd><ul>{resourceLines.map((line, index) => <li key={index}>{line}</li>)}</ul></dd></div>}
  </dl>{blocked.length > 0 && <div><b>Chốt chặn đã ghi nhận</b><ul>{blocked.map((entry, index) => <li key={index}><b>{display(entry.name)}</b>: {display(entry.reason)}<code>Tiếp: {display(entry.nextStep)}</code></li>)}</ul></div>}</details>;
}
