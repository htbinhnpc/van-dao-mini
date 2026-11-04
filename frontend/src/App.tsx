import { FormEvent, useCallback, useEffect, useState } from "react";

type Account = {
  id: string; label: string; gameUsername?: string; status: string; enabled: boolean;
  state?: any; config: Record<string, any>; lastTickAt?: string; lastError?: string;
};
type LogEntry = { id: number; level: string; action: string; message: string; created_at: string };
type ServerStatus = { status: "active" | "maintenance" | "unknown"; checkedAt?: string; maintenance?: { message?: string; from?: number; until?: number } | null };
type GameMeta = {
  realms: Record<string, { id: string; name: string; stageModel?: string }>;
  activities: Record<string, { id: string; name: string }>;
  spots: Record<string, { id: string; name: string }>;
};
const sections = ["Tổng quan", "Vật phẩm", "Tự động", "Tài khoản", "Nhật ký"];

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || `HTTP ${response.status}`);
  return data as T;
}

export default function App() {
  const [user, setUser] = useState<{ id: string; username: string } | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [active, setActive] = useState(sections[0]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [serverStatus, setServerStatus] = useState<ServerStatus>({ status: "unknown" });
  const [meta, setMeta] = useState<GameMeta>({ realms: {}, activities: {}, spots: {} });
  const selected = accounts.find((account) => account.id === selectedId) || accounts[0];

  const refresh = useCallback(async (accountId?: string) => {
    const result = await api<{ accounts: Account[]; selectedAccountId?: string }>("/api/v1/dashboard/overview");
    setAccounts(result.accounts || []);
    const nextId = accountId || result.selectedAccountId || result.accounts?.[0]?.id || "";
    setSelectedId(nextId);
    if (nextId) {
      const [state, config] = await Promise.all([
        api<{ state: any }>(`/api/v1/accounts/${nextId}/state?refresh=false`),
        api<{ config: Record<string, any> }>(`/api/v1/accounts/${nextId}/config`),
      ]);
      setAccounts((rows) => rows.map((row) => row.id === nextId ? { ...row, state: state.state, config: config.config } : row));
    }
  }, []);

  useEffect(() => {
    api<{ user: { id: string; username: string } }>("/api/v1/auth/me")
      .then(async (result) => { setUser(result.user); await refresh(); })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    api<GameMeta>("/api/v1/meta").then(setMeta).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!user) { setServerStatus({ status: "unknown" }); return; }
    let alive = true;
    const check = () => api<ServerStatus>("/api/v1/game/server-status")
      .then((status) => { if (alive) setServerStatus(status); })
      .catch(() => { if (alive) setServerStatus({ status: "unknown" }); });
    void check();
    const timer = window.setInterval(check, 30_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [user]);

  const run = async (action: () => Promise<unknown>, success: string, keepSelection = true) => {
    setBusy(true); setNotice("");
    try { await action(); setNotice(success); await refresh(keepSelection ? selectedId : undefined); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Có lỗi xảy ra."); }
    finally { setBusy(false); }
  };

  const logout = async () => {
    setBusy(true);
    try { await api("/api/v1/auth/logout", { method: "POST" }); setUser(null); setAccounts([]); setSelectedId(""); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Không đăng xuất được."); }
    finally { setBusy(false); }
  };

  if (loading) return <main className="auth-wrap"><div className="card">Đang kiểm tra phiên…</div></main>;
  if (!user) return <AuthScreen onLogin={async (nextUser) => { setUser(nextUser); await refresh(); }} />;

  return (
    <main className="shell">
      <aside className="sidebar">
        <a className="brand" href="#overview">Vấn Đạo <span>MINI</span></a>
        <p className="muted">Nghịch Mệnh · Dashboard</p>
        <nav aria-label="Điều hướng chính">
          {sections.map((section) => <button className={active === section ? "nav-item active" : "nav-item"} key={section} onClick={() => setActive(section)}>{section}</button>)}
        </nav>
        <div className="sidebar-footer"><span className="dot" />Đăng nhập · {user.username}</div>
      </aside>
      <section className="content">
        <header className="topbar">
          <div><p className="eyebrow">BẢNG ĐIỀU KHIỂN</p><h1>{active}</h1></div>
          <div className="toolbar">
            <ServerStatusTag status={serverStatus} />
            {accounts.length > 0 && <select value={selected?.id || ""} onChange={(e) => { setSelectedId(e.target.value); void refresh(e.target.value); }} aria-label="Tài khoản game">
              {accounts.map((account) => <option value={account.id} key={account.id}>{account.label}</option>)}
            </select>}
            <button className="button secondary" onClick={() => void logout()} disabled={busy}>Đăng xuất</button>
          </div>
        </header>
        {notice && <div className="notice" role="status">{notice}</div>}
        {!selected && active !== "Tài khoản" && <AddAccount onAdded={(account) => { setAccounts((rows) => [...rows, account]); setSelectedId(account.id); }} />}
        {selected && active === "Tổng quan" && <Overview account={selected} meta={meta} busy={busy} onTick={() => run(() => api(`/api/v1/accounts/${selected.id}/tick`, { method: "POST" }), "Đã chạy một vòng thủ công.")} />}
        {selected && active === "Vật phẩm" && <Inventory accountId={selected.id} />}
        {selected && active === "Tự động" && <Automation account={selected} busy={busy} onSave={(config) => run(() => api(`/api/v1/accounts/${selected.id}/config`, { method: "PATCH", body: JSON.stringify({ config }) }), "Đã lưu cấu hình.")} />}
        {active === "Tài khoản" && <Accounts accounts={accounts} busy={busy} onAdd={(account) => { setAccounts((rows) => [...rows, account]); setSelectedId(account.id); }} onDelete={(id) => run(() => api(`/api/v1/accounts/${id}`, { method: "DELETE" }), "Đã gỡ tài khoản.", false)} />}
        {selected && active === "Nhật ký" && <Logs accountId={selected.id} />}
      </section>
    </main>
  );
}

function ServerStatusTag({ status }: { status: ServerStatus }) {
  const labels = { active: "Game server · Active", maintenance: "Game server · Maintenance", unknown: "Game server · Không xác định" };
  return <span className={`server-status-tag ${status.status}`} title={status.maintenance?.message || status.checkedAt || "Chưa kiểm tra được trạng thái máy chủ"}>
    <span className="server-status-dot" />{labels[status.status]}
  </span>;
}

function AuthScreen({ onLogin }: { onLogin: (user: { id: string; username: string }) => Promise<void> }) {
  const [setup, setSetup] = useState(false);
  const [username, setUsername] = useState(""); const [password, setPassword] = useState("");
  const [setupToken, setSetupToken] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const path = setup ? "/api/v1/auth/bootstrap" : "/api/v1/auth/login";
      const result = await api<{ user: { id: string; username: string } }>(path, { method: "POST", body: JSON.stringify(setup ? { username, password, setup_token: setupToken } : { username, password }) });
      await onLogin(result.user);
    } catch (e) { setError(e instanceof Error ? e.message : "Đăng nhập thất bại."); }
    finally { setBusy(false); }
  };
  return <main className="auth-wrap"><form className="card auth-card" onSubmit={submit}>
    <p className="eyebrow">VẤN ĐẠO · MINI CLIENT</p><h1>{setup ? "Khởi tạo dashboard" : "Đăng nhập"}</h1>
    <label>Tên đăng nhập<input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} /></label>
    <label>Mật khẩu<input type="password" autoComplete={setup ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10} /></label>
    {setup && <label>Setup token<input type="password" value={setupToken} onChange={(e) => setSetupToken(e.target.value)} required /></label>}
    {error && <p className="error-text">{error}</p>}<button className="button primary full" disabled={busy}>{busy ? "Đang xử lý…" : setup ? "Tạo tài khoản Admin" : "Đăng nhập Dashboard"}</button>
    <button className="link-button" type="button" onClick={() => { setSetup(!setup); setError(""); }}>{setup ? "Đã có user? Đăng nhập" : "Thiết lập lần đầu"}</button>
  </form></main>;
}

function AddAccount({ onAdded }: { onAdded: (account: Account) => void }) {
  const [username, setUsername] = useState(""); const [password, setPassword] = useState(""); const [label, setLabel] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { const result = await api<{ account: Account }>("/api/v1/accounts", { method: "POST", body: JSON.stringify({ username, password, label: label || username }) }); onAdded(result.account); }
    catch (e) { setError(e instanceof Error ? e.message : "Không liên kết được tài khoản."); }
    finally { setBusy(false); }
  };
  return <form className="card form-card" onSubmit={submit}><h2>Liên kết tài khoản game</h2><p className="muted">Backend đăng nhập qua API chính thức. Mật khẩu không được lưu; session được mã hóa trước khi lưu Supabase.</p>
    <label>Tên hiển thị<input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={48} /></label><label>Tên đăng nhập game<input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" /></label><label>Mật khẩu game<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></label>
    {error && <p className="error-text">{error}</p>}<button className="button primary" disabled={busy}>{busy ? "Đang liên kết…" : "Đăng nhập và liên kết"}</button>
  </form>;
}

function Overview({ account, meta, busy, onTick }: { account: Account; meta: GameMeta; busy: boolean; onTick: () => void }) {
  const state = account.state || {}; const character = state.character || {}; const activity = state.activity || {};
  const stats = character.stats || character.derived || {};
  const activityKey = typeof activity.type === "string" ? activity.type : "";
  const activityName = meta.activities[activityKey]?.name || (activity.type == null ? "Chưa có dữ liệu" : displayValue(activity.type));
  const targetName = typeof activity.targetId === "string"
    ? meta.spots[activity.targetId]?.name || activity.targetId
    : displayValue(activity.targetId);
  return <>
    <div className="notice">Tài khoản: <b>{account.label}</b> · Lượt tự động gần nhất: {account.lastTickAt ? new Date(account.lastTickAt).toLocaleString("vi-VN") : "chưa chạy"}</div>
    <div className="state-tags" aria-label="State hiện tại của game">
      <span className={`state-tag ${account.status === "active" ? "online" : "offline"}`}>
        Phiên game · {account.status === "active" ? "Đã liên kết" : account.status}
      </span>
      <span className="state-tag">Hoạt động · {activityName}{activity.targetId ? ` · ${targetName}` : ""}</span>
      {activity.win != null && <span className={`state-tag ${activity.win ? "online" : "offline"}`}>Kết quả · {activity.win ? "Thắng" : "Thua"}</span>}
      {state.stateVersion != null && <span className="state-tag">State v{state.stateVersion}</span>}
    </div>
    {account.lastError && <div className="error-banner">Lỗi gần nhất: {account.lastError}</div>}
    <div className="grid stats-grid">
      <Metric label="Cảnh giới" value={typeof character.realmName === "string" ? character.realmName : realmDisplay(character.realm, meta.realms)} detail={`Cấp ${character.level ?? "—"}`} />
      <Metric label="Tu vi" value={character.exp != null ? `${character.exp} / ${character.expNeed ?? "—"}` : "—"} detail={character.rateMilli ? `Tốc độ ${character.rateMilli}` : ""} />
      <Metric label="Hoạt động" value={activityName} detail={targetName === "—" ? "" : targetName} />
    </div>
    <div className="grid content-grid"><article className="card"><h2>Chỉ số nhân vật</h2><div className="stats-list">{Object.entries(stats).slice(0, 16).map(([key, value]) => <div key={key}><span>{key}</span><b>{String(value)}</b></div>)}{!Object.keys(stats).length && <p className="muted">State chưa có trường chỉ số đã chuẩn hóa.</p>}</div></article>
      <article className="card"><h2>Điều khiển</h2><p className="muted">Tự động: {account.enabled ? "đang bật" : "đang tắt"}</p><button className="button primary" disabled={busy} onClick={onTick}>Chạy một vòng ngay</button><p className="small muted">Một vòng có thể gửi lệnh game theo config đã bật.</p></article></div>
  </>;
}

function displayValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if (record.realmId != null) {
      return `${displayValue(record.realmId)}${record.stage != null ? ` · Tầng ${displayValue(record.stage)}` : ""}`;
    }
    return Object.entries(record).map(([key, item]) => `${key}: ${displayValue(item)}`).join(" · ");
  }
  if (Array.isArray(value)) return value.map(displayValue).join(", ");
  return String(value);
}

function realmDisplay(value: unknown, realms: GameMeta["realms"]): string {
  if (!value) return "—";
  const realmId = typeof value === "string"
    ? value
    : typeof value === "object" && !Array.isArray(value)
      ? String((value as Record<string, unknown>).realmId || "")
      : "";
  if (!realmId) return displayValue(value);
  const realm = realms[realmId];
  const name = realm?.name || realmId.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
  const stage = typeof value === "object" && value !== null && !Array.isArray(value)
    ? Number((value as Record<string, unknown>).stage || 0)
    : 0;
  if (!stage || !realm?.stageModel) return name;
  if (realm.stageModel === "layers") return `${name} · Tầng ${stage}`;
  if (realm.stageModel === "four_stage") return `${name} · ${["Sơ kỳ", "Trung kỳ", "Hậu kỳ", "Viên mãn"][stage - 1] || `Tầng ${stage}`}`;
  if (realm.stageModel === "gate") return `${name} · Cửa ${stage}`;
  return name;
}

function Metric({ label, value, detail }: { label: string; value: unknown; detail: string }) {
  return <article className="card"><p className="muted">{label}</p><strong>{displayValue(value)}</strong><small>{detail}</small></article>;
}

function Automation({ account, busy, onSave }: { account: Account; busy: boolean; onSave: (config: Record<string, any>) => void }) {
  const [config, setConfig] = useState(account.config);
  useEffect(() => setConfig(account.config), [account.id, account.config]);
  const flags = [
    ["enabled", "Bật trợ lý tự động"], ["autoMinor", "Tự lên tiểu tầng"], ["autoSalvage", "Tự dọn trang bị"],
    ["autoActivity", "Giữ hoạt động / điểm săn"], ["autoQuests", "Tự nhận nhiệm vụ"], ["autoDaily", "Tự nhận mốc ngày"],
    ["autoWeekly", "Tự nhận mốc tuần"], ["autoAchievements", "Tự nhận thành tựu"], ["autoMail", "Tự nhận thư có quà"],
    ["autoX2Daily", "Tự nhận thưởng mở rộng ngày"], ["autoCraft", "Tự luyện đan (tiêu nguyên liệu)"],
    ["autoUse", "Tự dùng đan (tiêu vật phẩm)"], ["autoUseExp", "Cho phép dùng đan tu vi trực tiếp"],
    ["autoBoss", "Tự đánh boss"], ["autoFarm", "Tự gieo / thu hoạch"],
  ] as const;
  const toggle = (key: string, value: boolean) => setConfig((current) => ({ ...current, [key]: value }));
  return <div className="card form-card"><h2>Cấu hình cho {account.label}</h2><label>Nhịp chạy<select value={config.intervalMs} onChange={(e) => setConfig({ ...config, intervalMs: Number(e.target.value) })}><option value={60000}>1 phút</option><option value={120000}>2 phút</option><option value={180000}>3 phút</option><option value={240000}>4 phút</option><option value={300000}>5 phút</option></select></label>
    <div className="toggle-grid">{flags.map(([key, label]) => <label className="toggle" key={key}><input type="checkbox" checked={!!config[key]} onChange={(e) => toggle(key, e.target.checked)} /><span>{label}</span></label>)}</div>
    <div className="grid two-col"><label>Ngưỡng phẩm cấp dọn<input type="number" min={0} max={7} value={config.autoSalvageTier} onChange={(e) => setConfig({ ...config, autoSalvageTier: Number(e.target.value) })} /></label><label>Chế độ dọn<select value={config.autoSalvageMode} onChange={(e) => setConfig({ ...config, autoSalvageMode: e.target.value })}><option value="salvage">Phân giải</option><option value="sell">Bán</option></select></label><label>Khoảng chờ buff (phút)<input type="number" min={0} max={240} value={config.useThresholdMin} onChange={(e) => setConfig({ ...config, useThresholdMin: Number(e.target.value) })} /></label><label>Số lượng đan muốn giữ<input type="number" min={0} value={config.craftKeepQty} onChange={(e) => setConfig({ ...config, craftKeepQty: Number(e.target.value) })} /></label></div>
    <p className="warning-text">Luyện/dùng đan, đánh boss và gieo trồng sẽ tác động tài nguyên trong game. Chỉ bật khi đã kiểm tra kỹ.</p><button className="button primary" disabled={busy} onClick={() => onSave(config)}>Lưu cấu hình</button>
  </div>;
}

function Inventory({ accountId }: { accountId: string }) {
  const [items, setItems] = useState<any[]>([]); const [query, setQuery] = useState(""); const [kind, setKind] = useState(""); const [error, setError] = useState("");
  useEffect(() => { api<{ items: any[] }>(`/api/v1/accounts/${accountId}/items?search=${encodeURIComponent(query)}&kind=${encodeURIComponent(kind)}`).then((r) => setItems(r.items)).catch((e) => setError(e.message)); }, [accountId, query, kind]);
  return <div className="card"><div className="filters"><input placeholder="Tìm vật phẩm" value={query} onChange={(e) => setQuery(e.target.value)} /><select value={kind} onChange={(e) => setKind(e.target.value)}><option value="">Mọi loại</option><option value="material">Nguyên liệu</option><option value="consumable">Tiêu hao</option><option value="equipment">Trang bị</option><option value="currency">Tiền tệ</option></select></div>{error && <p className="error-text">{error}</p>}<div className="table-wrap"><table><thead><tr><th>Vật phẩm</th><th>Loại</th><th>Số lượng</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.name || item.id}</td><td>{item.kind || "—"}</td><td>{item.qty}</td></tr>)}</tbody></table>{items.length === 0 && <p className="muted">Không tìm thấy vật phẩm.</p>}</div></div>;
}

function Logs({ accountId }: { accountId: string }) {
  const [logs, setLogs] = useState<LogEntry[]>([]); const [error, setError] = useState("");
  useEffect(() => { api<{ logs: LogEntry[] }>(`/api/v1/accounts/${accountId}/logs`).then((r) => setLogs(r.logs)).catch((e) => setError(e.message)); }, [accountId]);
  return <div className="card"><h2>Lịch sử thao tác</h2>{error && <p className="error-text">{error}</p>}<ul className="logs">{logs.map((log) => <li key={log.id}><span className={`badge ${log.level}`}>{log.level}</span><div><b>{log.action}</b><p>{log.message}</p><small>{new Date(log.created_at).toLocaleString("vi-VN")}</small></div></li>)}</ul>{!logs.length && <p className="muted">Chưa có nhật ký.</p>}</div>;
}

function Accounts({ accounts, busy, onAdd, onDelete }: { accounts: Account[]; busy: boolean; onAdd: (account: Account) => void; onDelete: (id: string) => void }) {
  const [adding, setAdding] = useState(false);
  return <>{accounts.length > 0 && <div className="card account-list"><div className="row-between"><h2>Tài khoản đã liên kết</h2><button className="button secondary" onClick={() => setAdding(!adding)}>Thêm tài khoản</button></div>{accounts.map((account) => <div className="account-row" key={account.id}><div><b>{account.label}</b><p className="muted">{account.gameUsername} · {account.status} · {account.enabled ? "automation bật" : "automation tắt"}</p></div><button className="button danger" disabled={busy} onClick={() => onDelete(account.id)}>Gỡ</button></div>)}</div>}{(adding || !accounts.length) && <AddAccount onAdded={(account) => { onAdd(account); setAdding(false); }} />}</>;
}
