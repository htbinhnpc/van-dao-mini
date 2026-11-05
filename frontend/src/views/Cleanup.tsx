import { useEffect, useRef, useState } from "react";
import { ConfirmDialog, ErrorState, Icon, Panel, Spinner } from "../components";
import { api, display, errorMessage, isAbort, number } from "../lib";
import type { Account, Config, GameMeta } from "../types";

type Rules = { mode: "salvage" | "sell"; maxRarity: string; maxTier: number; keepPerDefinition: number; maxItems: number; slots: string[] };
type Gear = { id: string; name: string; rarity?: string; tier?: number; slot?: string; reasonLabel: string; keptItemId?: string };
type Preview = { previewId: string | null; expiresAt: number; plan: { stateVersion: number; items: Gear[]; kept: Gear[]; scanned: number; candidateCount: number; deferredCount: number; summary: { reason: string; label: string; count: number }[] } };
const rarities = ["pham", "linh", "huyen", "dia", "thien", "tien", "dao"];

export function CleanupPanel({ account, meta, onState, onBusyChange, onSaveConfig }: { account: Account; meta: GameMeta; onState: (state: Record<string, any>, disposed: boolean) => void; onBusyChange: (busy: boolean) => void; onSaveConfig: (config: Config) => Promise<Config | null> }) {
  const config = account.config;
  const [rules, setRules] = useState<Rules>({ mode: config.cleanupMode || "salvage", maxRarity: config.cleanupMaxRarity || "pham", maxTier: config.cleanupMaxTier ?? 0, keepPerDefinition: config.cleanupKeepPerDefinition ?? 1, maxItems: config.cleanupMaxItems ?? 20, slots: config.cleanupSlots || [] });
  const [preview, setPreview] = useState<Preview | null>(null), [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false), [executing, setExecuting] = useState(false), [confirm, setConfirm] = useState(false);
  const [error, setError] = useState(""), [message, setMessage] = useState("");
  const [now, setNow] = useState(Date.now());
  const [savingOption, setSavingOption] = useState(false);
  const skipConfirmation = config.cleanupSkipConfirmation === true;
  const blocked = executing || savingOption;
  const request = useRef<AbortController | null>(null), executionLock = useRef(false);
  const expired = !!preview && preview.expiresAt * 1000 <= now;
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (!preview) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [preview]);
  const change = (patch: Partial<Rules>) => {
    request.current?.abort(); setLoading(false); setRules((current) => ({ ...current, ...patch }));
    setPreview(null); setSelected([]); setError(""); setMessage("");
  };
  const inspect = async () => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setLoading(true); setError(""); setMessage(""); setPreview(null); setSelected([]);
    try {
      const result = await api<Preview & { state: Record<string, any> }>(`/api/v1/accounts/${account.id}/cleanup/preview`, { method: "POST", body: JSON.stringify({ rules }), signal: controller.signal });
      if (controller.signal.aborted || request.current !== controller) return;
      setPreview(result); setSelected(result.plan.items.map((item) => item.id)); setNow(Date.now());
      onState(result.state, false);
    } catch (error) { if (!isAbort(error) && !controller.signal.aborted) setError(errorMessage(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  };
  const saveSkipConfirmation = async (value: boolean) => {
    if (executionLock.current) return;
    executionLock.current = true; setSavingOption(true); setError(""); setMessage("");
    try {
      const saved = await onSaveConfig({ cleanupSkipConfirmation: value });
      if (!saved) setError("Chưa lưu được tùy chọn. Chế độ xác nhận vẫn theo cấu hình đã lưu.");
      else setMessage(value ? "Đã bật dọn không hỏi xác nhận cho tài khoản này. Chưa dọn món nào; bấm Tự chọn và dọn ngay để xử lý một mẻ." : "Đã bật lại hộp xác nhận trước khi dọn.");
    } finally { executionLock.current = false; setSavingOption(false); }
  };
  const execute = async (fresh = false) => {
    if (executionLock.current || (fresh && !skipConfirmation) || (!fresh && (!preview?.previewId || preview.expiresAt * 1000 <= Date.now() || !selected.length))) return;
    executionLock.current = true; setExecuting(true); onBusyChange(true); setError(""); setMessage("");
    try {
      let batch = preview, ids = selected;
      if (fresh) {
        request.current?.abort(); setLoading(false); setPreview(null); setSelected([]);
        const result = await api<Preview & { state: Record<string, any> }>(`/api/v1/accounts/${account.id}/cleanup/preview`, { method: "POST", body: JSON.stringify({ rules, skipConfirmation: true }) });
        batch = result; ids = result.plan.items.map((item) => item.id); onState(result.state, false);
        if (!ids.length) { setMessage("Không có bản trùng phù hợp; chưa gửi lệnh bán/phân giải."); return; }
      }
      if (!batch?.previewId || batch.expiresAt * 1000 <= Date.now()) throw new Error("Bản xem trước đã hết hạn. Hãy xem trước lại.");
      const result = await api<{ state: Record<string, any>; removedCount: number; mode: string }>(`/api/v1/accounts/${account.id}/cleanup/execute`, { method: "POST", body: JSON.stringify({ previewId: batch.previewId, itemIds: ids, skipConfirmation }) });
      onState(result.state, true);
      setMessage(`Đã ${result.mode === "sell" ? "bán" : "phân giải"} ${result.removedCount} món. Không thể hoàn tác thao tác game này.`);
    } catch (error) { setError(errorMessage(error)); }
    finally {
      // Never offer the same batch again, even after an uncertain timeout.
      setPreview(null); setSelected([]); setConfirm(false); setExecuting(false); onBusyChange(false); executionLock.current = false;
    }
  };
  const numeric = (label: string, key: "maxTier" | "keepPerDefinition" | "maxItems", min: number, max: number, hint: string) => <label className="field">{label}<input type="number" inputMode="numeric" value={rules[key]} required min={min} max={max} step={1} onChange={(event) => change({ [key]: Number(event.target.value) })} /><small>{hint}</small></label>;
  return <Panel title="Dọn túi Mini" eyebrow="BỘ LỌC RIÊNG · KHÔNG DÙNG BỘ CHỌN CỦA GAME" className="cleanup-panel" action={<Icon name="shield" />}>
    <p className="cleanup-intro">Chỉ dọn bản trùng <b>cùng mẫu trang bị</b> khi có món được giữ không kém ở bất kỳ chỉ số nào. Không chấm điểm sức mạnh tùy ý, không so chéo bộ/loại vũ khí.</p>
    <div className="cleanup-protection"><Icon name="shield" size={17} /><span>Luôn giữ đồ đang mặc/kho, khóa/yêu thích, cường hóa, chưa đủ cấp hoặc thiếu dữ liệu an toàn. Các món có chỉ số đánh đổi khác nhau cũng được giữ.</span></div>
    <label className="toggle-row cleanup-no-confirm"><span className="toggle-copy"><span className="toggle-title">Dọn không hỏi xác nhận</span><span className="toggle-description">Lưu riêng cho tài khoản này. Khi bấm dọn, bán/phân giải ngay theo bộ lọc, không hiện hộp xác nhận và không thể hoàn tác. Bật tùy chọn chưa chạy dọn.</span></span><span className="switch"><input type="checkbox" role="switch" aria-label="Dọn không hỏi xác nhận" checked={skipConfirmation} disabled={blocked || loading} onChange={(event) => void saveSkipConfirmation(event.target.checked)} /><span className="switch-track" /></span></label>
    <p className="settings-note"><Icon name="clock" size={16} />Muốn tự dọn theo lịch khi không mở trang: bật Dọn túi Mini và Trợ lý tự động trong Tự động. Các lượt theo lịch không hỏi xác nhận, đều ghi nhật ký.</p>
    {Number(account.state?.settings?.autoSalvageTier) > 0 && <div className="alert alert-warning"><Icon name="warning" /><span>Bộ dọn đồ rơi gốc vẫn đang bật. Nên tắt trong game; bật auto Dọn túi Mini sẽ yêu cầu tắt bộ dọn gốc trước khi kết toán.</span></div>}
    <form onSubmit={(event) => { event.preventDefault(); if (!blocked) void inspect(); }}><fieldset disabled={blocked}><div className="field-grid cleanup-filters"><label className="field">Cách xử lý<select value={rules.mode} onChange={(event) => change({ mode: event.target.value as Rules["mode"] })}><option value="salvage">Phân giải lấy vật liệu</option><option value="sell">Bán lấy linh thạch</option></select></label><label className="field">Phẩm chất tối đa<select value={rules.maxRarity} onChange={(event) => change({ maxRarity: event.target.value })}>{rarities.map((rarity) => <option key={rarity} value={rarity}>{meta.rarities[rarity]?.label || rarity}</option>)}</select><small>Không nhầm phẩm chất với cấp đồ (tier).</small></label>{numeric("Cấp đồ tối đa (tier)", "maxTier", 0, 99, "0: không giới hạn tier; vẫn giữ đồ chưa đủ cấp.")}{numeric("Giữ ít nhất mỗi mẫu", "keepPerDefinition", 1, 10, "Chỉ dọn khi có bản khác cùng mẫu không kém về chỉ số.")}{numeric("Số món tối đa một mẻ", "maxItems", 1, 60, "Giới hạn tối đa 60 món theo lệnh game.")}</div><fieldset className="cleanup-slots"><legend>Vị trí cần xét <span>· để trống = tất cả</span></legend><div className="category-filters">{Object.entries(meta.slots).map(([slot, label]) => <button key={slot} type="button" aria-pressed={rules.slots.includes(slot)} className={rules.slots.includes(slot) ? "active" : ""} onClick={() => change({ slots: rules.slots.includes(slot) ? rules.slots.filter((value) => value !== slot) : [...rules.slots, slot] })}>{label}</button>)}</div></fieldset><div className="cleanup-inspect"><button className="button secondary" type="submit" disabled={loading}>{loading ? <Spinner /> : <Icon name="search" size={17} />}{loading ? "Đang đọc túi mới từ game…" : "Xem trước đồ sẽ dọn"}</button><span>Xem trước chỉ đọc state, không bán/phân giải. Bộ lọc tại đây không tự lưu cho auto.</span></div>
      {skipConfirmation && <div className="cleanup-inspect"><button type="button" className="button danger" aria-label="Tự chọn và dọn ngay" aria-busy={executing} disabled={loading} onClick={(event) => { if (event.currentTarget.form?.reportValidity()) void execute(true); }}>{executing ? <Spinner /> : <Icon name="warning" size={17} />}{executing ? "Đang dọn, không gửi lại…" : "Tự chọn và dọn ngay"}</button><span>Tự đọc túi mới và dọn tối đa {rules.maxItems} món một mẻ. Không hỏi lại; kết quả xem ở Nhật ký.</span></div>}
    </fieldset></form>
    {error && <ErrorState message={error} />}{message && <div className="alert cleanup-success" role="status"><Icon name="check" /><span>{message}</span></div>}
    {preview && <div className="cleanup-preview"><div className="cleanup-preview-head"><div><h3>{preview.plan.items.length ? `${selected.length} món được chọn / ${preview.plan.items.length} món an toàn` : "Không có món phù hợp để dọn"}</h3><p>Đã xét {number(preview.plan.scanned)} món · state v{preview.plan.stateVersion}{preview.plan.deferredCount > 0 ? ` · ${preview.plan.deferredCount} món để lại cho mẻ sau` : ""}</p></div>{preview.previewId && <span className={`pill ${expired ? "warning" : "neutral"}`}>{expired ? "Đã hết hạn — xem trước lại" : `Còn ${Math.max(0, Math.ceil((preview.expiresAt * 1000 - now) / 1000))} giây`}</span>}</div>
      {preview.plan.items.length > 0 && <><div className="cleanup-select-actions"><button type="button" className="text-button" disabled={blocked || expired} onClick={() => setSelected(preview.plan.items.map((item) => item.id))}>Chọn các món an toàn</button><button type="button" className="text-button" disabled={blocked} onClick={() => setSelected([])}>Bỏ chọn tất cả</button></div><ul className="cleanup-items">{preview.plan.items.map((item) => <li key={item.id}><label><input type="checkbox" aria-label={`Dọn ${item.name} ${item.id}`} checked={selected.includes(item.id)} disabled={blocked || expired} onChange={(event) => setSelected((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /><span><b>{item.name}</b><small>{meta.rarities[item.rarity || ""]?.label || item.rarity} · Tier {item.tier} · {meta.slots[item.slot || ""] || item.slot}</small><small>{item.reasonLabel}</small><code>ID: {item.id} · Giữ: {item.keptItemId}</code></span></label></li>)}</ul><button className="button danger cleanup-execute" disabled={blocked || expired || !selected.length} onClick={() => { if (skipConfirmation) void execute(); else setConfirm(true); }}><Icon name="warning" size={17} />{rules.mode === "sell" ? "Bán" : "Phân giải"} {selected.length} món đã chọn</button></>}
      <div className="cleanup-summary">{preview.plan.summary.map((item) => <span key={item.reason}>{item.label}: <b>{item.count}</b></span>)}</div>
      {preview.plan.kept.length > 0 && <details className="cleanup-kept"><summary>Xem đồ được giữ và lý do ({preview.plan.kept.length})</summary><ul>{preview.plan.kept.slice(0, 40).map((item, index) => <li key={`${display(item.id)}-${index}`}><b>{item.name}</b><span>{item.reasonLabel}</span></li>)}</ul>{preview.plan.kept.length > 40 && <p>Đang hiển thị 40 món đầu. Toàn bộ {preview.plan.kept.length} món này được giữ.</p>}</details>}
    </div>}
    <ConfirmDialog open={confirm} title={rules.mode === "sell" ? "Bán các món đã chọn?" : "Phân giải các món đã chọn?"} confirmLabel={rules.mode === "sell" ? `Xác nhận bán ${selected.length} món` : `Xác nhận phân giải ${selected.length} món`} danger busy={executing} confirmDisabled={expired} onCancel={() => setConfirm(false)} onConfirm={() => void execute()}><p><b>{account.label}</b> sẽ xử lý <b>{selected.length} món</b> trong đúng bản xem trước này. Thao tác game <b>không thể hoàn tác</b>.</p><p>Backend đọc lại state, kiểm tra version/bộ lọc và chỉ cho phép xác nhận dùng một lần. Nếu state thay đổi, bạn cần xem trước lại.</p>{expired && <p className="danger-text">Bản xem trước đã hết hạn. Quay lại và xem trước lại trước khi xác nhận.</p>}</ConfirmDialog>
  </Panel>;
}
