import { useEffect, useRef, useState } from "react";
import { EmptyState, ErrorState, Icon, Panel, Spinner } from "../components";
import { api, dateTime, duration, errorMessage, isAbort, number } from "../lib";
import type { Account } from "../types";

type Profession = { id: string; name: string; known: boolean; level?: number; crafted?: number; next?: number | null; maxed?: boolean; pending: number; nextEtaMs: number | null; maxEtaMs: number | null };
type Action = { name: string; profession: string; reason: string; count: number; stones: number; durationMs: number; phase: string };
type Block = { name: string; reason: string; code?: string; nextStep?: string };
type Diagnostics = { decision?: string; nextStep?: string; scope?: string; settingLines?: string[]; resourceLines?: string[]; blockedTotal?: number };
type CraftStatus = { stateVersion: number | null; lastTickAt?: string | null; plan: {
  phase: string; reason: string; nextStep?: string; slots: number; freeSlots: number; build: string; action: Action | null;
  professions: Profession[]; budget: { day: string; limit: number; spent: number; remaining: number };
  jobs: { id: string; name: string; recipeId: string; finishAt?: number; reason: string }[];
  blocked: Block[]; diagnostics?: Diagnostics;
} };
const phases: Record<string, string> = { breakthrough: "Chuẩn bị đột phá đại cảnh", leveling: "Cày tay nghề", production: "Sản xuất", unknown: "Chưa đủ dữ liệu tay nghề", disabled: "Tự chế tạo đang tắt" };
const decisions: Record<string, string> = { ready: "Có việc có thể làm", blocked: "Tất cả lựa chọn đang bị chặn", uncertain: "Kết quả trước chưa xác nhận", disabled: "Tính năng đang tắt", waiting_furnaces: "Chờ lò", waiting_level: "Chờ lên cấp", waiting_breakthrough: "Chờ đột phá", waiting_policy: "Chờ chính sách", unknown: "Thiếu dữ liệu" };
const builds: Record<string, string> = { sword: "Kiếm tu", thunder: "Lôi tu", body: "Thể tu", soul: "Hồn tu", formation: "Trận tu", unknown: "Chưa xác định" };
const eta = (ms: number | null) => ms == null ? "Chưa tính được" : duration(ms / 1000);

export function Crafting({ account, onSettings }: { account: Account; onSettings: () => void }) {
  const [status, setStatus] = useState<CraftStatus | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [now, setNow] = useState(Date.now()), [reload, setReload] = useState(0);
  const refresh = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setStatus(null);
    const readGame = refresh.current; refresh.current = false;
    void api<CraftStatus>(`/api/v1/accounts/${account.id}/crafting?refresh=${readGame}`, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setStatus(result); })
      .catch((err) => { if (!isAbort(err) && !controller.signal.aborted) setError(errorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [account.id, account.config, account.state?.stateVersion, reload]);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const sync = () => { refresh.current = true; setReload((value) => value + 1); };
  const plan = status?.plan;
  return <div className="crafting-page">
    <Panel title="Chế tạo & tay nghề" eyebrow="4 NGHỀ · CÀY TUẦN TỰ → SẢN XUẤT" action={<button type="button" className="button secondary compact" disabled={loading} onClick={sync}>{loading ? <Spinner /> : <Icon name="refresh" size={16} />}Đồng bộ lò</button>}>
      <p className="muted">Trang này chỉ đọc tiến độ và kế hoạch, không bắt đầu mẻ hay tiêu tài nguyên. Bật Tự chế tạo và lưu các hạn mức trong Tự động để worker chạy.</p>
      <button type="button" className="text-button" onClick={onSettings}>Cài đặt chế tạo <Icon name="arrow" size={15} /></button>
      {loading && <div role="status" className="craft-loading"><Spinner /> Đang đọc trạng thái lò…</div>}
      {error && <ErrorState message={error} onRetry={() => setReload((value) => value + 1)} />}
      {plan && <><div className="craft-phase" role="status"><b>Giai đoạn: {phases[plan.phase] || plan.phase}</b><p>{plan.reason}</p><small>Hệ tu: {builds[plan.build] || plan.build} · {plan.freeSlots}/{plan.slots} lò trống · state v{status.stateVersion ?? "—"}</small>{plan.nextStep && <p className="craft-direction"><b>Phương hướng:</b> {plan.nextStep}</p>}</div>
        {plan.diagnostics && !!((plan.diagnostics.settingLines?.length || 0) + (plan.diagnostics.resourceLines?.length || 0)) && <details className="craft-diagnostics"><summary>Cấu hình đang áp dụng & vì sao chờ</summary>
          {!!plan.diagnostics.settingLines?.length && <><h4>Cấu hình</h4><ul>{plan.diagnostics.settingLines.map((line, index) => <li key={index}>{line}</li>)}</ul></>}
          {!!plan.diagnostics.resourceLines?.length && <><h4>Tài nguyên & ngân sách</h4><ul>{plan.diagnostics.resourceLines.map((line, index) => <li key={index}>{line}</li>)}</ul></>}
          {plan.diagnostics.decision && <p className="muted small">Quyết định: {decisions[plan.diagnostics.decision] || plan.diagnostics.decision}{plan.diagnostics.blockedTotal ? ` · ${plan.diagnostics.blockedTotal} chốt chặn đã ghi nhận` : ""}</p>}
        </details>}
        <div className="craft-professions">{plan.professions.map((p) => <article className="craft-profession" key={p.id}>
          <div className="row"><h3>{p.name}</h3><span className="pill neutral">{p.known ? `Cấp ${p.level}${p.maxed ? " · Max" : ""}` : "Chưa có dữ liệu"}</span></div>
          <progress aria-label={`Tiến độ ${p.name}`} value={p.maxed ? 1 : p.crafted ?? 0} max={p.maxed ? 1 : p.next || 1} />
          <p>{p.known ? p.maxed ? `${number(p.crafted)} mẻ · Đã tối đa` : `${number(p.crafted)}/${number(p.next)} mẻ` : "Không suy đoán nghề đã max từ dữ liệu thiếu."}</p>
          <small>{p.pending} mẻ đang chạy · ETA cấp kế: {eta(p.nextEtaMs)}<br />ETA tới max (ước tính): {eta(p.maxEtaMs)}</small>
        </article>)}</div>
        <p className="settings-note"><Icon name="clock" size={16} />ETA giả định đủ nguyên liệu và dùng mọi lò; không tính thời gian chờ Cron. Các mốc tương lai 115/150 mẻ là ước tính theo tài liệu; quyết định lên cấp/max luôn dùng state game.</p>
        <dl className="craft-budget"><div><dt>Ngân sách cày/ngày (UTC)</dt><dd>{number(plan.budget.limit)} linh thạch</dd></div><div><dt>Đã dùng / giữ chỗ</dt><dd>{number(plan.budget.spent)}</dd></div><div><dt>Còn lại</dt><dd>{number(plan.budget.remaining)}</dd></div></dl>
        {plan.action && <div className="craft-next"><h3>Lựa chọn tiếp theo</h3><p><b>{plan.action.name} ×{plan.action.count}</b> · {eta(plan.action.durationMs)}/mẻ · {number(plan.action.stones)} linh thạch</p><small>{plan.action.reason} · Chưa gửi lệnh; worker sẽ kiểm tra lại state và tài nguyên.</small></div>}
        {!!plan.blocked.length && <details className="craft-blocked"><summary>Công thức/nghề bị chặn ({plan.diagnostics?.blockedTotal ?? plan.blocked.length})</summary><ul>{plan.blocked.map((entry, index) => <li key={index}><b>{entry.name}</b>: {entry.reason}{entry.nextStep && <small>Tiếp: {entry.nextStep}</small>}</li>)}</ul></details>}
        <p className="muted small">Snapshot gần nhất: {dateTime(status.lastTickAt)}. Đồng bộ lò để lấy dữ liệu mới từ game.</p>
      </>}
    </Panel>
    {plan && <Panel title={`Lò chế tạo (${plan.jobs.length}/${plan.slots})`} eyebrow="KHÔNG HỦY / KHÔNG BỎ QUA THỜI GIAN">
      {!plan.slots ? <EmptyState icon="spark" title="Chưa có dữ liệu lò">Đồng bộ game để đọc số lò đã mở.</EmptyState> : <ol className="craft-furnaces">{Array.from({ length: Math.max(plan.slots, plan.jobs.length) }, (_, index) => {
        const job = plan.jobs[index], left = job?.finishAt ? Math.max(0, job.finishAt - now) : null;
        return <li key={job?.id || `idle-${index}`}><span className="pill neutral">Lò {index + 1}</span><div><h3>{job?.name || "Lò trống"}</h3><p>{job?.reason || plan.reason}</p><small>{job ? left === 0 ? "Đã đến giờ · chờ game kết toán" : `Còn ${eta(left)}` : "Chưa gửi lệnh chế tạo"}</small></div></li>;
      })}</ol>}
    </Panel>}
  </div>;
}
