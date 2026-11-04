import { useState, type FormEvent } from "react";
import { Brand, ErrorState, Icon, Spinner } from "../components";
import { api, errorMessage } from "../lib";
import type { Account, User } from "../types";

function Password({ value, onChange, label = "Mật khẩu", minLength, autoComplete = "current-password" }: { value: string; onChange: (value: string) => void; label?: string; minLength?: number; autoComplete?: string }) {
  const [visible, setVisible] = useState(false);
  return <label className="field">{label}<span className="password-input"><input type={visible ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} autoComplete={autoComplete} required minLength={minLength} /><button type="button" className="icon-button" aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"} onClick={() => setVisible(!visible)}><Icon name={visible ? "eyeOff" : "eye"} size={18} /></button></span></label>;
}
export function AuthScreen({ onLogin }: { onLogin: (user: User) => Promise<void> }) {
  const [setup, setSetup] = useState(false), [username, setUsername] = useState(""), [password, setPassword] = useState(""), [token, setToken] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await api<{ user: User }>(`/api/v1/auth/${setup ? "bootstrap" : "login"}`, { method: "POST", body: JSON.stringify({ username: username.trim(), password, ...(setup ? { setup_token: token } : {}) }) });
      setPassword(""); setToken(""); await onLogin(result.user);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  };
  return <main className="auth-layout"><div className="auth-landscape"><Brand /><div className="auth-story"><span className="auth-kicker">MỘT ĐỜI TU ĐẠO · MỘT NIỆM NGHỊCH THIÊN</span><h1>Đạo tại tâm.<br /><em>Mệnh tại ta.</em></h1><p>Một khoảng tĩnh lặng giữa vạn biến.<br />Theo dõi hành trình, giữ nhịp tu hành của riêng bạn.</p><div className="ornament" aria-hidden="true"><span />◆<span /></div></div><span className="auth-caption">Thanh Khê · Nơi hành trình bắt đầu</span></div><div className="auth-form-wrap"><form className="auth-form" onSubmit={submit}><p className="eyebrow">CHÀO MỪNG ĐẠO HỮU</p><h2>{setup ? "Khai mở động phủ" : "Trở về động phủ"}</h2><p className="muted">{setup ? "Tạo tài khoản quản trị đầu tiên cho dashboard." : "Đăng nhập dashboard để tiếp tục hành trình của bạn."}</p><fieldset disabled={busy}><label className="field">Tên đăng nhập<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required minLength={3} autoFocus /></label><Password value={password} onChange={setPassword} minLength={setup ? 10 : undefined} autoComplete={setup ? "new-password" : "current-password"} />{setup && <label className="field">Setup token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} required autoComplete="off" /><small>Token khởi tạo do người triển khai cung cấp.</small></label>}{error && <ErrorState message={error} />}<button className="button primary full" type="submit">{busy ? <Spinner /> : <Icon name="arrow" size={18} />}{busy ? "Đang mở động phủ…" : setup ? "Khởi tạo dashboard" : "Đăng nhập"}</button></fieldset><button type="button" disabled={busy} className="text-button auth-switch" onClick={() => { setSetup(!setup); setError(""); setPassword(""); setToken(""); }}>{setup ? "Đã có tài khoản? Đăng nhập" : "Lần đầu ghé thăm? Thiết lập dashboard"}</button><div className="auth-security"><Icon name="shield" size={18} /><p>Đây là tài khoản dashboard, không phải tài khoản game.<br />Phiên game của bạn được mã hóa khi lưu trữ.</p></div></form><p className="auth-disclaimer">Vấn Đạo Mini · Công cụ cá nhân, không phải game chính thức.</p></div></main>;
}
export function AddAccount({ onAdded, onCancel }: { onAdded: (account: Account) => void; onCancel?: () => void }) {
  const [username, setUsername] = useState(""), [password, setPassword] = useState(""), [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await api<{ account: Account }>("/api/v1/accounts", { method: "POST", body: JSON.stringify({ username: username.trim(), password, label: label.trim() || username.trim() }) });
      setPassword(""); onAdded(result.account);
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  };
  return <form className="panel link-account-form" onSubmit={submit}><div className="panel-head"><div><p className="eyebrow">THÊM MỘT HÀNH TRÌNH</p><h2>Liên kết tài khoản game</h2></div><Icon name="users" /></div><p className="muted">Đăng nhập một lần để liên kết. Mật khẩu game không được lưu.</p><fieldset disabled={busy}><label className="field">Tên hiển thị <span className="optional">· tùy chọn</span><input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={48} placeholder="Ví dụ: Thanh Vân" /></label><label className="field">Tên đăng nhập game<input value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} maxLength={24} autoComplete="username" /></label><Password value={password} onChange={setPassword} label="Mật khẩu game" minLength={8} />{error && <ErrorState message={error} />}<div className="row"><button className="button primary" type="submit">{busy ? <Spinner /> : <Icon name="plus" size={17} />}{busy ? "Đang liên kết…" : "Đăng nhập & liên kết"}</button>{onCancel && <button className="button ghost" type="button" onClick={onCancel}>Hủy</button>}</div></fieldset><p className="security-line"><Icon name="shield" size={15} />Session được mã hóa trước khi lưu Supabase.</p></form>;
}
