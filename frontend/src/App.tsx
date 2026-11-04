import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage, isAbort, readPreference, writePreference } from "./lib";
import { Brand, ConfirmDialog, ErrorState, Icon, Skeleton, Spinner } from "./components";
import { AuthScreen, AddAccount } from "./views/Auth";
import { Overview } from "./views/Overview";
import { Automation } from "./views/Automation";
import { Accounts, Inventory, Logs } from "./views/Collection";
import { EMPTY_META, type Account, type Config, type GameMeta, type IconName, type Section, type ServerStatus, type User } from "./types";

const sections: { id: Section; label: string; icon: IconName; note: string }[] = [
  { id: "overview", label: "Tổng quan", icon: "compass", note: "Hành trình tu đạo" },
  { id: "inventory", label: "Túi đồ", icon: "bag", note: "Hành trang của bạn" },
  { id: "automation", label: "Tự động", icon: "spark", note: "Trợ lý tu hành" },
  { id: "accounts", label: "Tài khoản", icon: "users", note: "Các đạo hữu đồng hành" },
  { id: "logs", label: "Nhật ký", icon: "scroll", note: "Dấu chân tu hành" },
];
type Confirmation = { title: string; body: string; label: string; danger?: boolean; action: () => void | Promise<unknown> };
type Toast = { id: number; kind: "success" | "error" | "info"; text: string };

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const selectedRef = useRef(readPreference("vandao:account"));
  const [section, setSection] = useState<Section>("overview");
  const [loadingAccount, setLoadingAccount] = useState(false);
  const [pageError, setPageError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const mutationLock = useRef(false);
  const [dirty, setDirty] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [meta, setMeta] = useState<GameMeta>(EMPTY_META);
  const [metaError, setMetaError] = useState(false);
  const [server, setServer] = useState<ServerStatus>({ status: "unknown" });
  const accountRequest = useRef<AbortController | null>(null);
  const selected = accounts.find((account) => account.id === selectedId);
  const currentSection = sections.find((item) => item.id === section)!;

  const notify = useCallback((text: string, kind: Toast["kind"] = "success") => setToast({ id: Date.now(), text, kind }), []);
  useEffect(() => {
    if (!toast || toast.kind === "error") return;
    const timer = window.setTimeout(() => setToast(null), 6500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const loadAccounts = useCallback(async (requestedId?: string, refreshGame = false) => {
    accountRequest.current?.abort();
    const controller = new AbortController();
    accountRequest.current = controller;
    setLoadingAccount(true); setPageError("");
    try {
      const overview = await api<{ accounts: Account[] }>("/api/v1/dashboard/overview", { signal: controller.signal });
      let rows = overview.accounts || [];
      const wanted = requestedId ?? selectedRef.current;
      const id = rows.find((row) => row.id === wanted)?.id || rows[0]?.id || "";
      if (id) {
        const [state, config] = await Promise.all([
          api<{ state: Account["state"] }>(`/api/v1/accounts/${id}/state?refresh=${refreshGame}`, { signal: controller.signal }),
          api<{ config: Config }>(`/api/v1/accounts/${id}/config`, { signal: controller.signal }),
        ]);
        rows = rows.map((row) => row.id === id ? { ...row, state: state.state, config: config.config } : row);
      }
      if (controller.signal.aborted) return;
      selectedRef.current = id; writePreference("vandao:account", id);
      setSelectedId(id); setAccounts(rows);
    } catch (error) {
      if (!isAbort(error) && !controller.signal.aborted) setPageError(errorMessage(error));
    } finally { if (!controller.signal.aborted) setLoadingAccount(false); }
  }, []);

  const boot = useCallback(async (signal?: AbortSignal) => {
    setBooting(true); setBootError("");
    try {
      const result = await api<{ user: User }>("/api/v1/auth/me", { signal });
      if (signal?.aborted) return;
      setUser(result.user); await loadAccounts();
    } catch (error) {
      if (isAbort(error) || signal?.aborted) return;
      if (error instanceof ApiError && error.status === 401) setUser(null);
      else setBootError(errorMessage(error));
    } finally { if (!signal?.aborted) setBooting(false); }
  }, [loadAccounts]);

  useEffect(() => {
    const controller = new AbortController();
    void boot(controller.signal);
    return () => { controller.abort(); accountRequest.current?.abort(); };
  }, [boot]);

  const loadMeta = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await api<Partial<GameMeta>>("/api/v1/meta", { signal });
      if (!signal?.aborted) { setMeta({ ...EMPTY_META, ...result }); setMetaError(false); }
    } catch (error) { if (!isAbort(error) && !signal?.aborted) setMetaError(true); }
  }, []);
  useEffect(() => { const controller = new AbortController(); void loadMeta(controller.signal); return () => controller.abort(); }, [loadMeta]);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    let checking = false;
    const check = async () => {
      if (checking || document.hidden) return;
      checking = true;
      try {
        const result = await api<ServerStatus>("/api/v1/game/server-status", { signal: controller.signal });
        if (!controller.signal.aborted) setServer(result);
      } catch { if (!controller.signal.aborted) setServer({ status: "unknown" }); }
      finally { checking = false; }
    };
    void check();
    const timer = window.setInterval(check, 30_000);
    document.addEventListener("visibilitychange", check);
    return () => { controller.abort(); window.clearInterval(timer); document.removeEventListener("visibilitychange", check); };
  }, [user]);

  const run = async (label: string, action: () => Promise<void>, success: string) => {
    if (mutationLock.current) return false;
    mutationLock.current = true; setBusy(label); setToast(null);
    try { await action(); notify(success); return true; }
    catch (error) { notify(errorMessage(error), "error"); return false; }
    finally { mutationLock.current = false; setBusy(null); }
  };
  const leaveSafely = (action: () => void | Promise<unknown>) => {
    if (busy || loadingAccount) return;
    if (!dirty) { void action(); return; }
    setConfirmation({ title: "Cấu hình chưa được lưu", body: "Những thay đổi vừa chọn chưa áp dụng vào game. Rời trang sẽ bỏ các thay đổi này.", label: "Bỏ thay đổi & tiếp tục", action: () => { setDirty(false); return action(); } });
  };
  const saveConfig = async (config: Config): Promise<Config | null> => {
    if (!selected) return null;
    let saved: Config | null = null;
    await run("save", async () => {
      const result = await api<{ config: Config; enabled: boolean }>(`/api/v1/accounts/${selected.id}/config`, { method: "PATCH", body: JSON.stringify({ config }) });
      saved = result.config;
      setAccounts((rows) => rows.map((row) => row.id === selected.id ? { ...row, config: result.config, enabled: result.enabled } : row));
      setDirty(false);
    }, "Đã lưu cấu hình tu hành.");
    return saved;
  };
  const tick = () => {
    if (!selected) return;
    setConfirmation({ title: "Chạy một vòng tu hành?", body: `Tài khoản ${selected.label} sẽ kết toán và chạy các auto đã lưu, kể cả khi trợ lý định kỳ đang tắt. Các mục tiêu hao đã bật có thể dùng tài nguyên/lượt chơi.`, label: "Chạy một vòng", action: () => run("tick", async () => {
      const result = await api<{ state: Account["state"]; deferred?: boolean }>(`/api/v1/accounts/${selected.id}/tick`, { method: "POST" });
      setAccounts((rows) => rows.map((row) => row.id === selected.id ? { ...row, state: result.state, lastTickAt: new Date().toISOString(), lastError: null } : row));
    }, "Đã xử lý một vòng. Xem Nhật ký để biết từng thao tác.") });
  };
  const addAccount = (account: Account) => {
    setAccounts((rows) => [...rows.filter((row) => row.id !== account.id), account]);
    setSelectedId(account.id); selectedRef.current = account.id; writePreference("vandao:account", account.id);
    notify("Đã liên kết tài khoản game.");
  };

  if (booting) return <main className="boot-screen"><Brand /><Spinner label="Đang mở dashboard" /><p>Đang mở hành trình tu đạo…</p></main>;
  if (bootError) return <main className="boot-screen"><Brand /><ErrorState message={bootError} onRetry={() => void boot()} /></main>;
  if (!user) return <AuthScreen onLogin={async (nextUser) => { setUser(nextUser); await loadAccounts(); }} />;

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Đến nội dung chính</a>
    <aside className="sidebar">
      <Brand />
      <div className="sidebar-divider"><span>ĐỘNG PHỦ CỦA BẠN</span></div>
      <nav aria-label="Điều hướng chính">{sections.map((item) => <button type="button" className={`nav-item ${section === item.id ? "active" : ""}`} aria-current={section === item.id ? "page" : undefined} key={item.id} disabled={!!busy || loadingAccount} onClick={() => leaveSafely(() => setSection(item.id))}><Icon name={item.icon} /><span>{item.label}</span>{item.id === "automation" && <span className={`nav-dot ${selected?.enabled ? "on" : ""}`} />}</button>)}</nav>
      <div className="sidebar-bottom"><div className="safe-note"><Icon name="shield" /><div><b>Tu hành an tâm</b><p>Phiên game được mã hóa.<br />Bạn quyết định từng thao tác.</p></div></div><div className="user-row"><span className="avatar-small">{user.username.slice(0, 1).toUpperCase()}</span><div><b>{user.username}</b><small>Chủ động phủ</small></div><button className="icon-button" aria-label="Đăng xuất" disabled={!!busy} onClick={() => leaveSafely(() => run("logout", async () => { await api("/api/v1/auth/logout", { method: "POST" }); setAccounts([]); setUser(null); setDirty(false); }, "Đã đăng xuất."))}><Icon name="logout" size={18} /></button></div></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div className="breadcrumb">Động phủ <span>/</span> <b>{currentSection.label}</b></div><div className="topbar-actions"><span className={`server-status ${server.status}`} title={server.maintenance?.message || "Trạng thái kết nối game"}><i />{server.status === "active" ? "Máy chủ hoạt động" : server.status === "maintenance" ? "Đang bảo trì" : "Chưa rõ trạng thái"}</span>{accounts.length > 0 && <label className="account-picker"><Icon name="users" size={17} /><select aria-label="Tài khoản game" value={selectedId} disabled={!!busy || loadingAccount} onChange={(event) => { const id = event.target.value; leaveSafely(() => loadAccounts(id)); }}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.label}</option>)}</select></label>}<button className="icon-button mobile-logout" aria-label="Đăng xuất" disabled={!!busy} onClick={() => leaveSafely(() => run("logout", async () => { await api("/api/v1/auth/logout", { method: "POST" }); setAccounts([]); setUser(null); setDirty(false); }, "Đã đăng xuất."))}><Icon name="logout" size={18} /></button></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        <div className="page-heading"><div><p className="eyebrow">VẤN ĐẠO · MINI CLIENT</p><h1>{currentSection.note}</h1><p className="page-subtitle">{section === "overview" ? "Mỗi bước tiến, một lần nghịch mệnh." : section === "automation" ? "Tu hành theo cách của bạn. Mọi thay đổi đều trong tầm tay." : section === "inventory" ? "Mỗi món đồ, một phần cơ duyên." : section === "accounts" ? "Một động phủ, nhiều hành trình." : "Mọi bước tiến đều để lại dấu vết."}</p></div>{selected && section === "overview" && <button className="button secondary" disabled={!!busy || loadingAccount} onClick={() => void loadAccounts(selected.id, true)}>{loadingAccount ? <Spinner /> : <Icon name="refresh" size={16} />}Đồng bộ game</button>}</div>
        {server.status === "maintenance" && <div className="alert alert-warning"><Icon name="warning" /><span>{server.maintenance?.message || "Game đang bảo trì. Bạn vẫn có thể xem dữ liệu đã lưu; hãy chờ trước khi gửi thao tác game."}</span></div>}
        {metaError && <div className="alert"><Icon name="scroll" /><span>Chưa tải được tên vật phẩm/cảnh giới. Dữ liệu tài khoản vẫn được giữ nguyên.</span><button className="text-button" onClick={() => void loadMeta()}>Tải lại metadata</button></div>}
        {pageError && <ErrorState message={pageError} onRetry={() => void loadAccounts(selectedRef.current)} />}
        {loadingAccount ? <div className="panel loading-panel"><Skeleton lines={6} /></div> : <div className="page-content" key={`${section}:${selectedId}`}>
          {!selected && section !== "accounts" && !pageError && <div className="welcome-grid"><div><p className="eyebrow">KHỞI ĐẦU MỘT HÀNH TRÌNH</p><h2>Đạo lộ bắt đầu<br />từ một bước chân.</h2><p className="muted">Liên kết tài khoản game để xem tu vi, quản lý hành trang và thiết lập trợ lý tu hành riêng.</p></div><AddAccount onAdded={addAccount} /></div>}
          {selected && section === "overview" && <Overview account={selected} meta={meta} busy={!!busy} maintenance={server.status === "maintenance"} onTick={tick} onNavigate={(next) => setSection(next)} />}
          {selected && section === "automation" && <Automation account={selected} meta={meta} busy={busy === "save"} onSave={saveConfig} onDirtyChange={setDirty} />}
          {selected && section === "inventory" && <Inventory account={selected} meta={meta} />}
          {selected && section === "logs" && <Logs accountId={selected.id} />}
          {section === "accounts" && <Accounts accounts={accounts} selectedId={selectedId} meta={meta} busy={!!busy} onAdd={addAccount} onSelect={(id) => void loadAccounts(id)} onDelete={(account) => setConfirmation({ title: `Gỡ ${account.label}?`, body: "Chỉ gỡ liên kết và dữ liệu trợ lý trong dashboard. Nhân vật game không bị xóa. Bạn có thể liên kết lại sau.", label: "Gỡ liên kết", danger: true, action: () => run("delete", async () => {
            await api(`/api/v1/accounts/${account.id}`, { method: "DELETE" });
            setAccounts((rows) => rows.filter((row) => row.id !== account.id));
            if (selectedRef.current === account.id) { selectedRef.current = ""; setSelectedId(""); }
            await loadAccounts();
          }, "Đã gỡ liên kết tài khoản.") })} />}
        </div>}
        <footer className="page-footer"><span>Vấn Đạo Mini <span className="footer-diamond">◆</span> Trợ lý tu hành cá nhân</span><span>Không liên kết chính thức với nhà phát triển game.</span></footer>
      </main>
    </div>
    <ConfirmDialog open={!!confirmation} title={confirmation?.title || "Xác nhận"} confirmLabel={confirmation?.label} danger={confirmation?.danger} busy={!!busy} onCancel={() => setConfirmation(null)} onConfirm={() => { if (confirmation && !mutationLock.current) void Promise.resolve(confirmation.action()).then(() => setConfirmation(null)); }}><p>{confirmation?.body}</p></ConfirmDialog>
    {toast && <div className={`toast toast-${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}><span className="toast-symbol"><Icon name={toast.kind === "error" ? "warning" : toast.kind === "success" ? "check" : "scroll"} /></span><span>{toast.text}</span><button className="icon-button" aria-label="Đóng thông báo" onClick={() => setToast(null)}><Icon name="close" size={16} /></button></div>}
  </div>;
}
