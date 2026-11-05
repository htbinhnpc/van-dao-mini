import { useEffect, useId, useRef, useState } from "react";
import { AddAccount } from "./Auth";
import { Automation } from "./Automation";
import { ConfirmDialog, Icon, trapDialogFocus } from "../components";
import { activeAutos } from "../automation-config";
import { cultivationEta, dateTime, display, duration, formatRate, realmName, sectName } from "../lib";
import type { Account, Config, GameMeta } from "../types";

function FeaturesDialog({ account, meta, busy, onSave, onClose }: { account: Account; meta: GameMeta; busy: boolean; onSave: (config: Config) => Promise<Config | null>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null), id = useId();
  const [dirty, setDirty] = useState(false), [asking, setAsking] = useState(false);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  const close = () => { if (busy) return; if (dirty) setAsking(true); else onClose(); };
  return <dialog className="confirm-dialog features-dialog" ref={ref} aria-labelledby={id} onKeyDown={trapDialogFocus} onCancel={(event) => { event.preventDefault(); close(); }}>
    <div className="features-head"><h2 id={id}>Tính năng · {account.label}</h2><button type="button" className="icon-button" aria-label="Đóng tính năng" onClick={close}><Icon name="close" size={18} /></button></div>
    <div className="features-body"><Automation account={account} meta={meta} busy={busy} onSave={onSave} onDirtyChange={setDirty} /></div>
    <ConfirmDialog open={asking} title="Cấu hình chưa được lưu" confirmLabel="Bỏ thay đổi" danger onCancel={() => setAsking(false)} onConfirm={onClose}><p>Những thay đổi vừa chọn chưa áp dụng vào game. Đóng cửa sổ sẽ bỏ các thay đổi này.</p></ConfirmDialog>
  </dialog>;
}

function etaText(account: Account): string {
  const eta = cultivationEta(account.state, account.lastTickAt);
  if (eta.kind === "done") return "Đã đủ tu vi · chờ đột phá";
  if (eta.kind === "stalled") return "Chưa tăng tu vi";
  if (eta.kind === "unknown") return "Chưa có dữ liệu";
  const left = eta.at - Date.now();
  if (left <= 0) return "Đã đủ (theo dữ liệu gần nhất)";
  const at = new Date(eta.at).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
  return `${at} · còn ${duration(left / 1000)}`;
}

export function Accounts({ accounts, selectedId, meta, busy, onAdd, onSelect, onDelete, onToggleAuto, onSaveConfig }: {
  accounts: Account[]; selectedId: string; meta: GameMeta; busy: boolean; onAdd: (account: Account) => void; onSelect: (id: string) => void;
  onDelete: (account: Account) => void; onToggleAuto: (account: Account) => void; onSaveConfig: (accountId: string, config: Config) => Promise<Config | null>;
}) {
  const [adding, setAdding] = useState(false);
  const [featuresId, setFeaturesId] = useState("");
  const featuresAccount = accounts.find((account) => account.id === featuresId);
  return <>
    <div className="account-intro"><span className="muted">{accounts.length} tài khoản đã liên kết · Cấu hình được lưu riêng</span><button className="button primary" disabled={adding || busy} onClick={() => setAdding(true)}><Icon name="plus" size={17} />Liên kết tài khoản</button></div>
    {(adding || !accounts.length) && <AddAccount onAdded={(account) => { onAdd(account); setAdding(false); }} onCancel={accounts.length ? () => setAdding(false) : undefined} />}
    <div className="account-grid">{accounts.map((account) => {
      const character = account.state?.character || {}, eta = cultivationEta(account.state, account.lastTickAt);
      return <section className={`panel account-card ${selectedId === account.id ? "selected" : ""}`} key={account.id}>
        <div className="account-card-head"><span className="account-avatar">{account.label.slice(0, 1).toUpperCase()}</span><div><h2>{account.label}</h2><span>{account.gameUsername}</span></div><span className={`pill ${account.status === "active" ? "jade" : "warning"}`}><i />{account.status === "active" ? "Đã liên kết" : "Phiên cần kiểm tra"}</span></div>
        <p className="account-realm">{realmName(character.realm, meta.realms)}</p>
        <dl className="account-details">
          <div><dt>Nhân vật</dt><dd>{character.name ? display(character.name) : "Chưa có dữ liệu"}</dd></div>
          <div><dt>Tông môn</dt><dd>{sectName(account.state)}</dd></div>
          <div><dt>Tốc độ tu vi</dt><dd>{eta.kind === "eta" ? formatRate(eta.rate) : eta.kind === "stalled" ? "0 tu vi/giây" : "—"}</dd></div>
          <div><dt>Dự kiến đủ tu vi</dt><dd>{etaText(account)}</dd></div>
          <div><dt>Trợ lý tự động</dt><dd><label className="switch-inline"><input type="checkbox" role="switch" checked={!!account.enabled} disabled={busy} aria-label={`Trợ lý tự động của ${account.label}`} onChange={() => onToggleAuto(account)} /><span>{account.enabled ? "Đang bật" : "Đang tắt"}</span></label></dd></div>
          <div><dt>Tính năng đã chọn</dt><dd>{activeAutos(account.config || {}).length}</dd></div>
          <div><dt>Lần chạy gần nhất</dt><dd>{dateTime(account.lastTickAt)}</dd></div>
        </dl>
        {account.lastError && <p className="account-error">{display(account.lastError)}</p>}
        <div className="account-card-actions">
          <button className="button secondary" disabled={busy || selectedId === account.id} onClick={() => onSelect(account.id)}>{selectedId === account.id ? <><Icon name="check" size={16} />Đang chọn</> : "Chọn tài khoản"}</button>
          <button className="button ghost" disabled={busy} onClick={() => setFeaturesId(account.id)}><Icon name="spark" size={16} />Tính năng</button>
          <button className="text-button danger-text" disabled={busy} onClick={() => onDelete(account)}>Gỡ liên kết</button>
        </div>
      </section>;
    })}</div>
    {featuresAccount && <FeaturesDialog key={featuresAccount.id} account={featuresAccount} meta={meta} busy={busy} onSave={(config) => onSaveConfig(featuresAccount.id, config)} onClose={() => setFeaturesId("")} />}
  </>;
}
