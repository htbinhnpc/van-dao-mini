import { useState } from "react";
import { activeAutos } from "../automation-config";
import { EmptyState, Icon, Panel } from "../components";
import { dateTime, display, number, percent, realmName } from "../lib";
import type { Account, GameMeta, Section } from "../types";

const statLabels: Record<string, string> = { hp: "Sinh lực", mp: "Linh lực", atk: "Công", matk: "Pháp công", def: "Phòng ngự", res: "Kháng phép", speed: "Tốc độ", acc: "Chính xác", eva: "Né tránh", crit: "Bạo kích", critDmg: "Sát thương bạo kích", pen: "Xuyên giáp", cdr: "Giảm hồi chiêu", regen: "Hồi phục", mpen: "Xuyên kháng", mpRegen: "Hồi linh lực", healRecv: "Hiệu quả hồi phục", shieldPct: "Tạo khiên", ctrlRes: "Kháng khống chế", dotRes: "Kháng sát thương duy trì", mpCost: "Giảm tiêu hao", buffDur: "Thời lượng hiệu ứng" };
const pctStats = new Set(["res", "acc", "eva", "crit", "critDmg", "pen", "cdr", "mpen", "mpRegen", "healRecv", "shieldPct", "ctrlRes", "dotRes", "mpCost", "buffDur"]);
export function Overview({ account, meta, busy, maintenance, onTick, onNavigate }: { account: Account; meta: GameMeta; busy: boolean; maintenance: boolean; onTick: () => void; onNavigate: (section: Section) => void }) {
  const [allStats, setAllStats] = useState(false);
  const state = account.state || {}, character = state.character || {}, activity = state.activity || {};
  const stats = state.stats || character.stats || character.derived || {};
  const activityName = meta.activities[activity.type]?.name || (activity.type ? display(activity.type) : "Chưa chọn hoạt động");
  const spot = meta.spots[activity.targetId]?.name || activity.targetId;
  const enabled = activeAutos(account.config || {});
  const quests = (state.quests || []).filter((quest: any) => ["active", "open", "claimable"].includes(quest.status)).slice(0, 3);
  const fields = state.cave?.fields || [];
  const ready = fields.filter((item: any) => item.finishAt != null && Number(item.finishAt) <= Date.now()).length;
  const rooms = Array.isArray(state.cave?.rooms) ? state.cave.rooms : [];
  const roomDefs = meta.rooms || [];
  const activeRoom = rooms.find((room: any) => room.upgradeFinishAt != null);
  const progress = percent(character.exp, character.expNeed);
  return <>
    {account.lastError && <div className="alert alert-error" role="alert"><Icon name="warning" /><span><b>Lượt chạy gần nhất cần kiểm tra.</b> {account.lastError}</span><button className="text-button" onClick={() => onNavigate("logs")}>Xem nhật ký</button></div>}
    <div className="overview-top">
      <section className="cultivation-scene" aria-label="Thông tin tu luyện">
        <div className="scene-grain" aria-hidden="true" />
        <div className="scene-top"><span className="scene-location"><Icon name="compass" size={14} />{spot || "Hành trình tu đạo"}</span><span className={`pill ${account.status === "active" ? "jade" : "warning"}`}><i />{account.status === "active" ? "Đã liên kết" : "Cần liên kết lại"}</span></div>
        <div className="cultivator-info"><p className="scene-eyebrow">{character.name ? display(character.name) : account.label}</p><h2>{typeof character.realmName === "string" ? character.realmName : realmName(character.realm, meta.realms)}</h2><p className="cultivator-level">{character.level != null ? `Cấp ${number(character.level)}` : "Chưa có thông tin cấp"}<span>·</span>{state.power != null ? `Lực chiến ${number(state.power)}` : "Tiềm tâm tu luyện"}</p><div className="scene-flourish" aria-hidden="true">──── ◇ ────</div></div>
        <img className="cultivator-art" src={`/game-art/cultivator-${character.gender === "female" ? "female" : "male"}.png`} alt="" width="512" height="512" fetchPriority="high" />
        <div className="scene-bottom"><div className="activity-indicator"><span className="activity-emblem"><Icon name={activity.type === "farm" ? "sword" : "leaf"} size={22} /></span><div><small>HOẠT ĐỘNG HIỆN TẠI</small><b>{activityName}</b><span>{spot || "Theo hoạt động được lưu trong game"}</span></div>{activity.win != null && <span className={`battle-result ${activity.win ? "win" : "lose"}`}>{activity.win ? "Thắng" : "Thua"}</span>}</div><div className="cultivation-progress"><div className="progress-heading"><span>Tu vi tích lũy</span><span>{number(character.exp)} <em>/ {number(character.expNeed)}</em></span></div><div className="progress-track" role="progressbar" aria-label="Tiến độ tu vi" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div><div className="progress-caption"><span>{character.rateMilli != null ? `+${number(Number(character.rateMilli) / 1000)} tu vi / giây` : "Chưa có tốc độ tu vi"}</span><span>{character.expNeed != null ? `${number(progress)}%` : "Chưa có dữ liệu"}</span></div></div></div>
      </section>
      <div className="overview-side">
        <Panel title="Trợ lý tu hành" eyebrow="ĐỒNG HÀNH CÙNG BẠN" action={<span className={`pill ${account.enabled ? "jade" : "neutral"}`}><i />{account.enabled ? "Đang bật" : "Đang tắt"}</span>} className="assistant-panel"><p className="assistant-count"><strong>{enabled.length}</strong><span>tính năng đã chọn</span></p><p className="muted assistant-copy">{account.enabled ? "Trợ lý xử lý khi lịch định kỳ gọi đến. Tài nguyên chỉ dùng theo cấu hình bạn đã lưu." : "Bạn vẫn có thể chạy một vòng theo cấu hình đã lưu, hoặc bật trợ lý trong Tự động."}</p><button className="button primary full" disabled={busy || maintenance} onClick={onTick} title={maintenance ? "Game đang bảo trì" : undefined}><Icon name="spark" size={17} />Chạy một vòng ngay</button><button className="text-button assistant-settings" onClick={() => onNavigate("automation")}>Thiết lập trợ lý<Icon name="arrow" size={15} /></button><div className="assistant-last"><Icon name="clock" size={15} /><span>Lần chạy gần nhất<b>{dateTime(account.lastTickAt)}</b></span></div></Panel>
        <div className="safety-caption"><Icon name="shield" size={16} /><span>Chỉ dùng lệnh game. Không can thiệp dữ liệu máy chủ.</span></div>
      </div>
    </div>
    <div className="resource-grid"><div className="resource-card"><span className="resource-icon gold"><Icon name="coin" size={22} /></span><div><small>Linh thạch</small><strong>{number(state.wallet?.spirit_stone)}</strong></div><span className="resource-mark" aria-hidden="true">◇</span></div><div className="resource-card"><span className="resource-icon jade"><Icon name="spark" size={22} /></span><div><small>Cảm ngộ</small><strong>{number(state.wallet?.insight ?? state.materials?.insight)}</strong></div></div><div className="resource-card"><span className="resource-icon violet"><Icon name="leaf" size={22} /></span><div><small>Linh điền</small><strong>{state.cave?.unlocked ? `${ready} ô chín` : "Chưa mở"}</strong><span>{state.cave?.unlocked ? `${fields.length} / ${number(state.cave?.plots)} ô đang trồng` : "Tiếp tục hành trình để mở khóa"}</span></div></div></div>
    <div className="overview-bottom"><Panel title="Căn cơ & chỉ số" eyebrow="HIỂU RÕ BẢN THÂN" action={Object.keys(stats).length > 8 && <button className="text-button" onClick={() => setAllStats(!allStats)}>{allStats ? "Thu gọn" : "Tất cả chỉ số"}<Icon name="chevron" size={14} /></button>}>{Object.keys(stats).length ? <dl className="stat-grid">{Object.entries(stats).slice(0, allStats ? undefined : 8).map(([key, value]) => <div key={key}><dt>{meta.stats[key]?.label || statLabels[key] || key}</dt><dd>{pctStats.has(key) && Number.isFinite(Number(value)) ? `${number(Number(value) * 100)}%` : number(value)}</dd></div>)}</dl> : <EmptyState title="Chưa có chỉ số">Đồng bộ game để lấy trạng thái nhân vật mới nhất.</EmptyState>}<div className="panel-footnote"><Icon name="shield" size={14} />Dữ liệu đã lưu từ game{state.stateVersion != null ? ` · phiên bản ${number(state.stateVersion)}` : ""}</div></Panel>
      <Panel title="Bước chân tiếp theo" eyebrow="NHẬT TRÌNH TU ĐẠO" action={<Icon name="scroll" size={19} />}>{quests.length ? <ul className="quest-list">{quests.map((quest: any, index: number) => <li key={quest.id || index}><span className={`quest-seal ${quest.status === "claimable" ? "complete" : ""}`}>{quest.status === "claimable" ? <Icon name="check" size={17} /> : String(index + 1).padStart(2, "0")}</span><div><b>{meta.quests[quest.id]?.name || quest.name || "Nhiệm vụ đang thực hiện"}</b><span>{quest.status === "claimable" ? "Đã hoàn thành · có thể nhận thưởng" : quest.current != null && quest.target != null ? `${number(quest.current)} / ${number(quest.target)}` : "Đang trên hành trình"}</span></div></li>)}</ul> : <EmptyState icon="scroll" title="Đạo lộ rộng mở">Chưa có nhiệm vụ đang làm trong dữ liệu đã lưu.</EmptyState>}<button className="text-button panel-link" onClick={() => onNavigate("automation")}>Thiết lập tự nhận thưởng<Icon name="arrow" size={15} /></button></Panel></div>
    <Panel title="Động phủ" eyebrow="PHÒNG & TIẾN ĐỘ" className="cave-panel" action={<span className={`pill ${activeRoom ? "warning" : "neutral"}`}><i />{activeRoom ? "Đang nâng" : state.cave?.unlocked ? "Sẵn sàng" : "Chưa mở"}</span>}>
      {!state.cave?.unlocked ? <EmptyState icon="leaf" title="Chưa mở động phủ">Đạt cấp 16 rồi dùng lệnh mở động phủ trong game. Mini không tự mở.</EmptyState>
        : !roomDefs.length ? <p className="muted">Chưa tải được metadata phòng động phủ. Thử tải lại metadata.</p>
        : <div className="cave-room-grid">{roomDefs.map((definition) => {
          const room = rooms.find((item: any) => item.id === definition.id);
          const level = typeof room?.level === "number" ? room.level : null;
          const maxLevel = Number(definition.maxLevel) || 0;
          const busy = room?.upgradeFinishAt != null;
          const done = level != null && maxLevel > 0 && level >= maxLevel;
          const minutes = busy ? Math.max(0, Math.ceil((Number(room.upgradeFinishAt) - Date.now()) / 60000)) : 0;
          return <div className={`cave-room ${busy ? "upgrading" : ""}`} key={definition.id}>
            <div className="cave-room-head"><b>{definition.name}</b><span>{level == null ? "Chưa rõ cấp" : `Cấp ${level}/${maxLevel}`}</span></div>
            <p>{definition.effect}</p>
            {busy ? <span className="cave-room-state"><Icon name="clock" size={13} />Đang nâng{minutes ? ` · còn ~${minutes} phút` : " · chờ kết toán"}</span> : done ? <span className="cave-room-state cave-room-done">Đã đạt cấp tối đa</span> : null}
          </div>;
        })}</div>}
      <div className="panel-footnote"><Icon name="shield" size={14} />{activeRoom ? "Mỗi lúc chỉ nâng một phòng; Mini không dùng cave.rush." : "Chỉ nâng khi đủ tài nguyên dư; không suy đoán cấp phòng còn thiếu."}</div>
    </Panel>
  </>;
}
