export type Config = Record<string, any>;
export type User = { id: string; username: string };
export type Account = {
  id: string; label: string; gameUsername?: string; status: string; enabled: boolean;
  state?: Record<string, any> | null; config: Config; lastTickAt?: string | null;
  lastError?: string | null; createdAt?: string;
};
export type Definition = { id: string; name: string; reqLevel?: number; [key: string]: any };
export type GameMeta = {
  realms: Record<string, Definition>;
  activities: Record<string, Definition>;
  spots: Record<string, Definition>;
  huntTargets: Record<string, Definition>;
  stats: Record<string, { label: string; kind: string }>;
  equipment: Record<string, Definition>;
  slots: Record<string, string>;
  rarities: Record<string, { label: string; color: string }>;
  recipes: Record<string, Definition>;
  seeds: Record<string, Definition>;
  regions: Record<string, Definition>;
  quests: Record<string, Definition>;
  rooms: Definition[];
};
export const EMPTY_META: GameMeta = {
  realms: {}, activities: {}, spots: {}, huntTargets: {}, stats: {}, equipment: {},
  slots: {}, rarities: {}, recipes: {}, seeds: {}, regions: {}, quests: {}, rooms: [],
};
export type ServerStatus = {
  status: "active" | "maintenance" | "unknown";
  checkedAt?: string; maintenance?: { message?: string } | null;
};
export type LogEntry = { id: number; level: string; action: string; message: string; created_at: string; details?: Record<string, unknown> | null };
export type Section = "overview" | "inventory" | "crafting" | "automation" | "accounts" | "logs";
export type IconName = "compass" | "bag" | "spark" | "users" | "scroll" | "arrow" | "refresh" | "plus" | "close" | "check" | "shield" | "logout" | "search" | "leaf" | "sword" | "coin" | "clock" | "warning" | "eye" | "eyeOff" | "chevron";
