import { Component, useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import type { IconName } from "./types";

const paths: Record<IconName, ReactNode> = {
  compass: <><circle cx="12" cy="12" r="9" /><path d="m16 8-3 5-5 3 3-5 5-3Z" /></>,
  bag: <><path d="M5 7h14l1 14H4L5 7Z" /><path d="M8 8V6a4 4 0 0 1 8 0v2" /></>,
  spark: <><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z" /><path d="m20 2 .7 2.3L23 5l-2.3.7L20 8l-.7-2.3L17 5l2.3-.7L20 2Z" /></>,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v3" /></>,
  scroll: <><path d="M6 3h13v14a4 4 0 0 1-4 4H6M6 3a3 3 0 0 0-3 3v2h6V6a3 3 0 0 0-3-3Zm0 18a3 3 0 0 1-3-3v-2h12v2a3 3 0 0 0 3 3M12 8h4m-4 4h4" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  check: <path d="m5 12 4 4L19 6" />,
  shield: <><path d="M12 2 3 6v6c0 6 9 10 9 10s9-4 9-10V6l-9-4Z" /><path d="m8 12 3 3 5-6" /></>,
  logout: <><path d="M9 4H4v16h5M10 12h11m-4-4 4 4-4 4" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  leaf: <><path d="M20 3C7 2 1 8 5 15c5 8 17 2 15-12Z" /><path d="M3 21 16 8" /></>,
  sword: <><path d="m5 19 2-2m-3-3 6 6m-4-4L16 4l4-1-1 4L8 18M3 21l3-3" /></>,
  coin: <><circle cx="12" cy="12" r="9" /><path d="M9 9h6v6H9z" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  warning: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3v1" /></>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="m3 3 18 18M9 5a11 11 0 0 1 3 0c6 0 10 7 10 7a19 19 0 0 1-4 4M6 6a21 21 0 0 0-4 6s4 7 10 7a12 12 0 0 0 4-1" /></>,
  chevron: <path d="m8 4 8 8-8 8" />,
};
export function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  return <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
export function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? "brand-small" : ""}`}><span className="brand-seal" aria-hidden="true">道</span><span><b>Vấn Đạo<span className="brand-mini">MINI</span></b><small>NGHỊCH MỆNH</small></span></div>;
}
export function Spinner({ label = "Đang xử lý" }: { label?: string }) {
  return <span className="spinner" role="status" aria-label={label} />;
}
export function EmptyState({ icon = "compass", title, children, action }: { icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-symbol"><Icon name={icon} size={28} /></span><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>;
}
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="alert alert-error" role="alert"><Icon name="warning" /><span>{message}</span>{onRetry && <button type="button" className="text-button" onClick={onRetry}>Thử lại</button>}</div>;
}
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return <div className="skeleton-stack" aria-label="Đang tải dữ liệu" role="status">{Array.from({ length: lines }, (_, i) => <div className="skeleton" key={i} style={{ width: i === lines - 1 ? "65%" : "100%" }} />)}</div>;
}
export function Panel({ title, eyebrow, action, children, className = "" }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><header className="panel-head"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>{action}</header>{children}</section>;
}
export function trapDialogFocus(event: KeyboardEvent<HTMLDialogElement>) {
  if (event.key !== "Tab") return;
  const elements = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href], [tabindex]"))
    .filter((element) => !element.matches(":disabled") && element.tabIndex >= 0 && element.getClientRects().length > 0);
  if (!elements.length) { event.preventDefault(); return; }
  const first = elements[0], last = elements[elements.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === event.currentTarget)) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === event.currentTarget)) {
    event.preventDefault(); first.focus();
  }
}
export function ConfirmDialog({ open, title, children, confirmLabel = "Xác nhận", danger = false, busy = false, confirmDisabled = false, onConfirm, onCancel }: {
  open: boolean; title: string; children: ReactNode; confirmLabel?: string; danger?: boolean; busy?: boolean; confirmDisabled?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (open && dialog && !dialog.open) dialog.showModal();
    else if (!open && dialog?.open) dialog.close();
    return () => { if (dialog?.open) dialog.close(); };
  }, [open]);
  return <dialog ref={ref} className="confirm-dialog" aria-labelledby={titleId} onKeyDown={trapDialogFocus} onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}>
    <div className="dialog-icon"><Icon name={danger ? "warning" : "shield"} size={28} /></div>
    <h2 id={titleId}>{title}</h2><div className="dialog-body">{children}</div>
    <div className="dialog-actions"><button type="button" className="button ghost" onClick={onCancel} disabled={busy} autoFocus>Quay lại</button><button type="button" aria-label={confirmLabel} aria-busy={busy} className={`button ${danger ? "danger" : "primary"}`} onClick={onConfirm} disabled={busy || confirmDisabled}>{busy && <Spinner />}{confirmLabel}</button></div>
  </dialog>;
}

export class DashboardBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <main className="boot-screen"><Brand /><div className="panel"><EmptyState icon="warning" title="Giao diện cần được tải lại" action={<button className="button primary" onClick={() => window.location.reload()}>Tải lại dashboard</button>}>Có dữ liệu chưa hiển thị được. Cấu hình đã lưu và tài khoản game của bạn không bị thay đổi.</EmptyState></div></main>;
  }
}
