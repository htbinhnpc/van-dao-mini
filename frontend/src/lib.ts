import type { GameMeta } from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init, credentials: "same-origin",
    headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || data?.ok === false) {
    const detail = data?.detail || data?.message;
    const message = typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((item: any) => item.msg || "Dữ liệu không hợp lệ").join(" · ")
      : `Không thể hoàn tất yêu cầu (HTTP ${response.status}).`;
    throw new ApiError(message, response.status);
  }
  if (!data) throw new ApiError("Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại.", response.status);
  return data as T;
}

export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Không kết nối được máy chủ. Vui lòng thử lại.";
export const isAbort = (error: unknown) => error instanceof DOMException && error.name === "AbortError";
export function display(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) return value.map(display).join(", ");
  return Object.entries(value).map(([key, item]) => `${key}: ${display(item)}`).join(" · ");
}

const numbers = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });
export function number(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "string" && /^-?\d+$/.test(value)) {
    try { return numbers.format(BigInt(value)); } catch { return value; }
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? numbers.format(parsed) : "—";
}
export function percent(current: unknown, maximum: unknown): number {
  const value = Number(current), max = Number(maximum);
  return Number.isFinite(value) && Number.isFinite(max) && max > 0 ? Math.min(100, Math.max(0, value / max * 100)) : 0;
}
export function realmName(value: unknown, realms: GameMeta["realms"]): string {
  if (!value) return "Chưa có cảnh giới";
  const record = typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const id = typeof value === "string" ? value : String(record.realmId || "");
  if (!id) return display(value);
  const definition = realms[id];
  const name = definition?.name || id.replace(/_/g, " ");
  const stage = Number(record.stage || 0);
  if (!stage) return name;
  if (definition?.stageModel === "four_stage") return `${name} · ${["Sơ kỳ", "Trung kỳ", "Hậu kỳ", "Viên mãn"][stage - 1] || `Tầng ${stage}`}`;
  if (definition?.stageModel === "gate") return `${name} · Cửa ${stage}`;
  if (definition?.stageModel === "layers" || !definition) return `${name} · Tầng ${stage}`;
  return name;
}
export function dateTime(value?: string | null): string {
  if (!value) return "Chưa ghi nhận";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Chưa ghi nhận" : date.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}
const SECT_NAMES: Record<string, string> = {
  sect_thanh_van: "Thanh Vân Kiếm Các", sect_loi_dinh: "Lôi Đình Cốc", sect_thiet_son: "Thiết Sơn Môn",
  sect_hon_dang: "Hồn Đăng Các", sect_cam_van: "Cấm Văn Sơn Trang",
};
/** Sect name from the cached state; names come from the public game client. */
export function sectName(state?: Record<string, any> | null): string {
  const sect = state?.sect;
  if (!sect) return "Chưa gia nhập tông môn";
  const id = typeof sect === "string" ? sect : String(sect.id || "");
  if (!id) return "Chưa gia nhập tông môn";
  return SECT_NAMES[id] || (typeof sect.name === "string" && sect.name) || id.replace(/^sect_/, "").replace(/_/g, " ");
}
export function duration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const total = Math.round(seconds), days = Math.floor(total / 86400), hours = Math.floor(total % 86400 / 3600), minutes = Math.floor(total % 3600 / 60);
  if (days) return hours ? `${days} ngày ${hours} giờ` : `${days} ngày`;
  if (hours) return minutes ? `${hours} giờ ${minutes} phút` : `${hours} giờ`;
  return minutes ? `${minutes} phút` : `${total} giây`;
}
export type CultivationEta = { kind: "done" } | { kind: "stalled" } | { kind: "unknown" } | { kind: "eta"; rate: number; seconds: number; at: number };
/** Tu vi per second and when the next tu vi bar fills, from the last cached state (an estimate). */
export function cultivationEta(state: Record<string, any> | null | undefined, lastTickAt?: string | null): CultivationEta {
  const character = state?.character;
  if (!character) return { kind: "unknown" };
  let remaining: number;
  try { remaining = Number(BigInt(character.expNeed) - BigInt(character.exp)); }
  catch { remaining = Number(character.expNeed) - Number(character.exp); }
  if (!Number.isFinite(remaining)) return { kind: "unknown" };
  if (remaining <= 0) return { kind: "done" };
  const rate = Number(character.rateMilli) / 1000;
  if (!(rate > 0)) return { kind: "stalled" };
  const base = Number(state?.serverNow) || Date.parse(lastTickAt || "") || Date.now();
  const seconds = remaining / rate;
  return { kind: "eta", rate, seconds, at: base + seconds * 1000 };
}
export const formatRate = (rate: number) => `${rate >= 100 ? number(Math.round(rate)) : rate.toFixed(2).replace(".", ",")} tu vi/giây`;
export function normalize(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLocaleLowerCase("vi-VN");
}
export function readPreference(key: string, fallback = ""): string {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}
export function writePreference(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* Storage is optional. */ }
}
