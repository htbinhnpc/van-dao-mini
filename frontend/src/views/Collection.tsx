import { useDeferredValue, useEffect, useId, useMemo, useRef, useState } from "react";
import { AddAccount } from "./Auth";
import { CleanupPanel } from "./Cleanup";
import { CleanupLogDetails, cleanupLogSearch } from "./CleanupLogDetails";
import { EmptyState, ErrorState, Icon, Panel, Skeleton, trapDialogFocus } from "../components";
import { activeAutos } from "../automation-config";
import { api, dateTime, display, errorMessage, isAbort, normalize, number, realmName } from "../lib";
import type { Account, Config, Definition, GameMeta, LogEntry } from "../types";

type Item = Definition & { kind: string; qty: unknown };
const kindNames: Record<string, string> = { material: "Nguyên liệu", consumable: "Tiêu hao", equipment: "Trang bị", currency: "Tiền tệ" };
const currencyNames: Record<string, string> = { spirit_stone: "Linh thạch", insight: "Cảm ngộ", sect_contribution: "Cống hiến tông môn", festival_token: "Lễ phù", x2_gw_badge: "Huy hiệu chiến tuyến" };
function ItemDetail({ item, meta, onClose }: { item: Item; meta: GameMeta; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null), id = useId();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog className="confirm-dialog item-dialog" ref={ref} aria-labelledby={id} onKeyDown={trapDialogFocus} onCancel={(event) => { event.preventDefault(); onClose(); }}><div className="item-dialog-head"><span className={`item-symbol ${item.kind}`}><Icon name={item.kind === "equipment" ? "sword" : item.kind === "currency" ? "coin" : "leaf"} size={35} /></span><button className="icon-button" onClick={onClose} aria-label="Đóng chi tiết"><Icon name="close" /></button></div><p className="eyebrow">{kindNames[item.kind] || "VẬT PHẨM"}</p><h2 id={id}>{item.name}</h2><p className="item-description">{typeof item.desc === "string" ? item.desc : "Vật phẩm trong hành trang đã lưu của tài khoản game."}</p><dl className="detail-list"><div><dt>Số lượng</dt><dd>{number(item.qty)}</dd></div>{item.slot && <div><dt>Vị trí</dt><dd>{meta.slots[item.slot] || item.slot}</dd></div>}{item.reqLevel != null && <div><dt>Yêu cầu cấp</dt><dd>{number(item.reqLevel)}</dd></div>}{item.rarity && <div><dt>Phẩm cấp</dt><dd>{meta.rarities[item.rarity]?.label || item.rarity}</dd></div>}{item.location && <div><dt>Trạng thái</dt><dd>{item.location === "equipped" ? "Đang trang bị" : "Trong túi"}{item.locked ? " · Đã khóa" : ""}</dd></div>}</dl><p className="security-line"><Icon name="shield" size={15} />Chế độ xem · không tự dùng hoặc thay đổi vật phẩm.</p><button className="button secondary full" onClick={onClose}>Đóng chi tiết</button></dialog>;
}
export function Inventory({ account, meta, onState, onBusyChange, onSaveConfig }: { account: Account; meta: GameMeta; onState: (state: Record<string, any>) => void; onBusyChange: (busy: boolean) => void; onSaveConfig: (config: Config) => Promise<Config | null> }) {
  const [materials, setMaterials] = useState<Item[]>([]), [wallet, setWallet] = useState<Record<string, unknown>>(account.state?.wallet || {});
  const [loading, setLoading] = useState(true), [error, setError] = useState(""), [revision, setRevision] = useState(0);
  const [query, setQuery] = useState(""), [kind, setKind] = useState(""), [limit, setLimit] = useState(30), [layout, setLayout] = useState("grid");
  const [detail, setDetail] = useState<Item | null>(null);
  const deferredQuery = useDeferredValue(query);
  useEffect(() => { if (account.state?.wallet) setWallet(account.state.wallet); }, [account.state?.wallet]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError("");
    api<{ items: Item[]; wallet: Record<string, unknown> }>(`/api/v1/accounts/${account.id}/items`, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) { setMaterials(result.items || []); setWallet(result.wallet || {}); } })
      .catch((error) => { if (!isAbort(error) && !controller.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [account.id, revision]);
  const items = useMemo(() => {
    const equipment = (account.state?.equipment || []).map((item: any): Item => ({ ...meta.equipment[item.defId], ...item, name: meta.equipment[item.defId]?.name || item.name || item.defId || "Trang bị", kind: "equipment", qty: 1 }));
    const currencies = Object.entries(wallet).filter(([, value]) => Number(value) > 0).map(([id, qty]): Item => ({ id, qty, name: currencyNames[id] || id, kind: "currency" }));
    return [...materials, ...equipment, ...currencies];
  }, [materials, wallet, account.state, meta.equipment]);
  const filtered = useMemo(() => {
    const needle = normalize(deferredQuery.trim());
    return items.filter((item) => (!kind || item.kind === kind) && (!needle || normalize(`${item.name} ${item.id}`).includes(needle)));
  }, [items, kind, deferredQuery]);
  useEffect(() => setLimit(30), [query, kind]);
  return <><CleanupPanel account={account} meta={meta} onSaveConfig={onSaveConfig} onBusyChange={onBusyChange} onState={(state, disposed) => { onState(state); if (disposed) setRevision((value) => value + 1); }} /><Panel title="Hành trang" eyebrow={`${items.length} MỤC VẬT PHẨM ĐÃ LƯU`} action={<button className="button ghost compact" onClick={() => setRevision((value) => value + 1)} disabled={loading}><Icon name="refresh" size={16} />Tải lại</button>}>
    <div className="collection-toolbar"><div className="search-input"><Icon name="search" size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm tên hoặc mã vật phẩm…" aria-label="Tìm vật phẩm" />{query && <button className="icon-button" aria-label="Xóa tìm kiếm" onClick={() => setQuery("")}><Icon name="close" size={16} /></button>}</div><label className="sr-only" htmlFor="kind-filter">Loại vật phẩm</label><select id="kind-filter" value={kind} onChange={(event) => setKind(event.target.value)}><option value="">Mọi loại vật phẩm</option>{Object.entries(kindNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><div className="segmented" aria-label="Kiểu hiển thị"><button className={layout === "grid" ? "active" : ""} aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}>Ô đồ</button><button className={layout === "list" ? "active" : ""} aria-pressed={layout === "list"} onClick={() => setLayout("list")}>Danh sách</button></div></div>
    {error && <ErrorState message={error} onRetry={() => setRevision((value) => value + 1)} />}
    {loading ? <Skeleton lines={5} /> : <><div className="collection-caption"><span>{filtered.length} kết quả{query && ` cho “${query}”`}</span><span><Icon name="shield" size={13} />Chỉ xem, không tiêu vật phẩm</span></div>{filtered.length ? <div className={`inventory-${layout}`} aria-label="Danh sách vật phẩm">{filtered.slice(0, limit).map((item, index) => <button key={`${item.kind}:${item.id}:${index}`} className={`item-card rarity-${item.rarity || "default"}`} onClick={() => setDetail(item)}><span className={`item-symbol ${item.kind}`}><Icon name={item.kind === "equipment" ? "sword" : item.kind === "currency" ? "coin" : item.kind === "consumable" ? "spark" : "leaf"} size={25} /></span><span className="item-info"><b>{item.name}</b><small>{kindNames[item.kind] || "Vật phẩm"}{item.location === "equipped" ? " · Đang mặc" : ""}</small></span><strong className="item-quantity">×{number(item.qty)}</strong><Icon name="chevron" size={14} className="item-chevron" /></button>)}</div> : !error && <EmptyState icon="bag" title={query || kind ? "Chưa tìm thấy vật phẩm" : "Hành trang còn trống"}>{query || kind ? "Thử từ khóa khác hoặc bỏ bộ lọc để xem toàn bộ hành trang." : "Đồng bộ game để cập nhật vật phẩm mới nhất."}</EmptyState>}{filtered.length > limit && <button className="button secondary load-more" onClick={() => setLimit((value) => value + 30)}>Xem thêm {Math.min(30, filtered.length - limit)} vật phẩm</button>}</>}
    {detail && <ItemDetail item={detail} meta={meta} onClose={() => setDetail(null)} />}
  </Panel></>;
}

const logLevels: Record<string, string> = { success: "Thành công", info: "Thông tin", warning: "Cần chú ý", error: "Lỗi" };
const actionLabels: Record<string, string> = { settle: "Kết toán tu vi", "equip.best": "Tự trang bị", "npc.talk": "Trò chuyện đạo hữu", "npc.claim": "Quà thiện cảm", "hunt.run": "Săn khế ấn", "pet.adopt": "Thu nhận linh thú", "craft.start": "Luyện đan", "item.use": "Dùng vật phẩm", "boss.fight": "Đánh boss", "activity.set": "Đổi hoạt động", "field.plant": "Gieo trồng", "field.harvest": "Thu hoạch", "settings.set": "Thiết lập game", "automation.tick": "Vòng tự động", "cleanup.manual": "Dọn túi Mini (thủ công)", "item.dispose": "Dọn túi Mini (auto)", "cleanup.config": "Thiết lập dọn túi Mini" };
export function Logs({ accountId }: { accountId: string }) {
  const [logs, setLogs] = useState<LogEntry[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [revision, setRevision] = useState(0), [level, setLevel] = useState(""), [query, setQuery] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError("");
    api<{ logs: LogEntry[] }>(`/api/v1/accounts/${accountId}/logs`, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setLogs(result.logs || []); })
      .catch((error) => { if (!isAbort(error) && !controller.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [accountId, revision]);
  const filtered = logs.filter((log) => (!level || log.level === level) && (!query.trim() || normalize(`${log.message} ${log.action} ${actionLabels[log.action] || ""} ${cleanupLogSearch(log)}`).includes(normalize(query.trim()))));
  return <Panel title="Nhật ký tu hành" eyebrow="THAO TÁC GẦN NHẤT" action={<button className="button ghost compact" onClick={() => setRevision((value) => value + 1)} disabled={loading}><Icon name="refresh" size={16} />Tải lại</button>}>
    <div className="collection-toolbar"><div className="search-input"><Icon name="search" size={18} /><input aria-label="Tìm nhật ký" placeholder="Tìm thao tác, nội dung hoặc ID món…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><label className="sr-only" htmlFor="level-filter">Mức nhật ký</label><select id="level-filter" value={level} onChange={(event) => setLevel(event.target.value)}><option value="">Mọi trạng thái</option>{Object.entries(logLevels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
    {error && <ErrorState message={error} onRetry={() => setRevision((value) => value + 1)} />}
    {loading ? <Skeleton lines={5} /> : filtered.length ? <ol className="timeline">{filtered.map((log) => <li key={log.id} className={`timeline-${log.level}`}><span className="timeline-symbol"><Icon name={log.level === "success" ? "check" : log.level === "warning" || log.level === "error" ? "warning" : "scroll"} size={17} /></span><div className="timeline-content"><div className="timeline-title"><b>{actionLabels[log.action] || log.action}</b><span className={`pill ${log.level === "success" ? "jade" : log.level === "error" ? "error" : log.level === "warning" ? "warning" : "neutral"}`}>{logLevels[log.level] || log.level}</span></div><p>{log.message}</p><time dateTime={log.created_at}>{dateTime(log.created_at)}</time><CleanupLogDetails log={log} /></div></li>)}</ol> : !error && <EmptyState icon="scroll" title={query || level ? "Không có nhật ký phù hợp" : "Chưa có dấu chân tu hành"}>{query || level ? "Thử bỏ bộ lọc để xem các thao tác khác." : "Sau khi chạy một vòng, các thao tác và kết quả sẽ xuất hiện ở đây."}</EmptyState>}
  </Panel>;
}

export function Accounts({ accounts, selectedId, meta, busy, onAdd, onSelect, onDelete }: { accounts: Account[]; selectedId: string; meta: GameMeta; busy: boolean; onAdd: (account: Account) => void; onSelect: (id: string) => void; onDelete: (account: Account) => void }) {
  const [adding, setAdding] = useState(false);
  return <><div className="account-intro"><span className="muted">{accounts.length} tài khoản đã liên kết · Cấu hình được lưu riêng</span><button className="button primary" disabled={adding || busy} onClick={() => setAdding(true)}><Icon name="plus" size={17} />Liên kết tài khoản</button></div>{(adding || !accounts.length) && <AddAccount onAdded={(account) => { onAdd(account); setAdding(false); }} onCancel={accounts.length ? () => setAdding(false) : undefined} />}<div className="account-grid">{accounts.map((account) => <section className={`panel account-card ${selectedId === account.id ? "selected" : ""}`} key={account.id}><div className="account-card-head"><span className="account-avatar">{account.label.slice(0, 1).toUpperCase()}</span><div><h2>{account.label}</h2><span>{account.gameUsername}</span></div><span className={`pill ${account.status === "active" ? "jade" : "warning"}`}><i />{account.status === "active" ? "Đã liên kết" : "Phiên cần kiểm tra"}</span></div><p className="account-realm">{realmName(account.state?.character?.realm, meta.realms)}</p><dl className="account-details"><div><dt>Trợ lý tự động</dt><dd>{account.enabled ? "Đang bật" : "Đang tắt"}</dd></div><div><dt>Tính năng đã chọn</dt><dd>{activeAutos(account.config || {}).length}</dd></div><div><dt>Lần chạy gần nhất</dt><dd>{dateTime(account.lastTickAt)}</dd></div></dl>{account.lastError && <p className="account-error">{display(account.lastError)}</p>}<div className="account-card-actions"><button className="button secondary" disabled={busy || selectedId === account.id} onClick={() => onSelect(account.id)}>{selectedId === account.id ? <><Icon name="check" size={16} />Đang chọn</> : "Chọn tài khoản"}</button><button className="text-button danger-text" disabled={busy} onClick={() => onDelete(account)}>Gỡ liên kết</button></div></section>)}</div></>;
}
