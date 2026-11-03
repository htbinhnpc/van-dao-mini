import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const researchDir = process.env.VD_RESEARCH_DIR || path.join(os.tmpdir(), 'vd-research');
const m = await import(pathToFileURL(path.join(researchDir, 'i18n_tr.mjs')).href);
const tr = JSON.parse(fs.readFileSync(path.join(researchDir, 'translations_full.json'), 'utf8'));

const prettify = (id) => String(id || '')
  .replace(/^(item|equip|skill|passive|pet|region|spot|boss|mob|quest|recipe|set|title|task|achv)_/, '')
  .replace(/_/g, ' ')
  .replace(/\b\w/g, c => c.toUpperCase());

const nameOf = (key, fallbackId) => tr[key] || prettify(fallbackId || key);

const items = {};
for (const [id, it] of Object.entries(m.io)) {
  items[id] = {
    id,
    name: nameOf(it.nameKey, id),
    desc: tr[it.descKey] || '',
    kind: it.kind || 'material',
    icon: it.iconId || '',
    bound: !!it.bound,
    stackCap: it.stackCap || 9999,
    use: it.use || null,
  };
}

const sets = {};
for (const [key, value] of Object.entries(tr)) {
  const match = /^set\.([a-z0-9_]+)$/.exec(key);
  if (!match) continue;
  const bonuses = [];
  for (const pieces of [2, 4, 6]) {
    const desc = tr[`set.${match[1]}.${pieces}`];
    if (desc) bonuses.push({ pieces, desc });
  }
  sets[`set_${match[1]}`] = { id: `set_${match[1]}`, name: value, bonuses };
}

const equipmentName = (id, eq) => {
  if (eq.nameKey && tr[eq.nameKey]) return tr[eq.nameKey];
  if (/^equip_t\d+_mbracer(?:_q[a-z]+)?$/.test(id)) {
    const set = sets[eq.setId]?.name?.replace(/^Bộ\s+/, '') || '';
    return set ? `${set} Pháp Hộ Oản` : 'Pháp Hộ Oản';
  }
  return prettify(id);
};

const equipment = {};
for (const [id, eq] of Object.entries(m.eo)) {
  equipment[id] = {
    id,
    name: equipmentName(id, eq),
    slot: eq.slot,
    tier: eq.tier,
    rarity: eq.rarity,
    reqLevel: eq.reqLevel,
    main: eq.main,
    setId: eq.setId || null,
    maxEnhance: eq.maxEnhance || 0,
    sellPrice: eq.sellPrice || 0,
    icon: eq.iconId || '',
  };
}

const skills = {};
for (const [id, sk] of Object.entries({ ...m.bo, ...m._o })) {
  skills[id] = {
    id,
    name: nameOf(sk.nameKey, id),
    desc: tr[sk.descKey] || '',
    kind: sk.kind || (id.startsWith('passive') ? 'passive' : 'active'),
    mpCost: sk.mpCost ?? null,
    cooldownMs: sk.cooldownMs ?? null,
    icon: sk.iconId || '',
    tags: sk.tags || [],
  };
}

const spots = {};
for (const [id, sp] of Object.entries(m.Qa)) {
  spots[id] = {
    id,
    name: nameOf(sp.nameKey, id),
    desc: tr[sp.descKey] || '',
    regionId: sp.regionId,
    reqLevel: sp.reqLevel,
    recLevel: sp.recLevel || [],
    expPerCycle: sp.expPerCycle,
  };
}

const regions = {};
for (const [id, rg] of Object.entries(m.Za)) {
  regions[id] = {
    id,
    name: nameOf(rg.nameKey, id),
    desc: tr[rg.descKey] || '',
    order: rg.order,
    spotIds: rg.spotIds || [],
    unlock: rg.unlock || {},
    bossId: rg.bossId || null,
  };
}

const realms = {};
for (const [id, r] of Object.entries(m.Do)) {
  realms[id] = {
    id,
    name: tr[r.nameKey] || r.aliases?.[0] || prettify(id),
    type: r.type,
    order: r.order,
    stageCount: r.stageCount,
    stageModel: r.stageModel,
  };
}

const quests = {};
for (const [id, q] of Object.entries(m.Fa)) {
  quests[id] = {
    id,
    name: nameOf(q.nameKey, id),
    desc: tr[q.descKey] || '',
    order: q.order,
    objective: q.objective,
    rewards: q.rewards || {},
  };
}

const pets = {};
for (const [id, p] of Object.entries(m.Sa)) {
  pets[id] = {
    id,
    name: nameOf(p.nameKey, id),
    desc: tr[p.descKey] || '',
    role: p.role,
  };
}

const origins = {};
for (const id of ['thon_da', 'gia_toc', 'tap_dich', 'duoc_dong']) {
  origins[id] = {
    id,
    name: tr[`origin.${id}.name`] || prettify(id),
    desc: tr[`origin.${id}.desc`] || '',
  };
}

const attrs = {
  can_cot: { label: tr['attr.can_cot'] || 'Căn cốt', desc: tr['attrdesc.can_cot'] || '' },
  dao_tam: { label: tr['attr.dao_tam'] || 'Đạo tâm', desc: tr['attrdesc.dao_tam'] || '' },
  co_duyen: { label: tr['attr.co_duyen'] || 'Cơ duyên', desc: tr['attrdesc.co_duyen'] || '' },
  ngo_tinh: { label: tr['attr.ngo_tinh'] || 'Ngộ tính', desc: tr['attrdesc.ngo_tinh'] || '' },
};

const currencies = {
  spirit_stone: { name: tr['currency.spirit_stone'] || 'Linh thạch', icon: 'item_spirit_stone_low_01' },
  insight: { name: tr['currency.insight'] || 'Cảm ngộ', icon: 'item_insight_01' },
  sect_contribution: { name: tr['currency.sect_contribution'] || 'Cống hiến', icon: 'item_sect_contribution_01' },
  arena_token: { name: tr['currency.arena_token'] || 'Điểm đấu trường', icon: 'item_arena_token_01' },
  festival_token: { name: tr['currency.festival_token'] || 'Lễ phù', icon: 'item_festival_token_01' },
};

const stats = {
  hp: { label: 'Sinh lực', kind: 'int' },
  mp: { label: 'Linh lực', kind: 'int' },
  atk: { label: 'Công', kind: 'int' },
  matk: { label: 'Pháp công', kind: 'int' },
  def: { label: 'Phòng ngự', kind: 'int' },
  res: { label: 'Kháng', kind: 'pct' },
  speed: { label: 'Tốc độ', kind: 'int' },
  acc: { label: 'Chính xác', kind: 'pct' },
  eva: { label: 'Né tránh', kind: 'pct' },
  crit: { label: 'Bạo kích', kind: 'pct' },
  critDmg: { label: 'Bạo thương', kind: 'x' },
  pen: { label: 'Xuyên giáp', kind: 'pct' },
  regen: { label: 'Hồi phục', kind: 'int' },
  cdr: { label: 'Giảm hồi chiêu', kind: 'pct' },
  mpen: { label: 'Xuyên kháng', kind: 'pct' },
  mpRegen: { label: 'Hồi linh lực', kind: 'pct' },
  healRecv: { label: 'Hồi phục nhận', kind: 'pct' },
  shieldPct: { label: 'Giá trị khiên', kind: 'pct' },
  ctrlRes: { label: 'Kháng khống chế', kind: 'pct' },
  dotRes: { label: 'Kháng DOT', kind: 'pct' },
  mpCost: { label: 'Giảm tiêu linh lực', kind: 'pct' },
  buffDur: { label: 'Thời lượng buff', kind: 'pct' },
};

const activities = {};
for (const id of ['seclusion', 'farm', 'gather_herb', 'mine_ore', 'body_training']) {
  activities[id] = {
    id,
    name: tr[`activity.${id}`] || prettify(id),
    desc: tr[`activitydesc.${id}`] || '',
  };
}

const rarities = {
  pham: { label: 'Phàm', color: '#b8b8b8' },
  linh: { label: 'Linh', color: '#6fe3a0' },
  huyen: { label: 'Huyền', color: '#66b7ff' },
  dia: { label: 'Địa', color: '#c58cff' },
  thien: { label: 'Thiên', color: '#ffb35c' },
  tien: { label: 'Tiên', color: '#ff7b7b' },
  dao: { label: 'Đạo', color: '#ffd76a' },
};

const slots = {
  weapon: 'Vũ khí', robe: 'Pháp bào', head: 'Mũ', bracer: 'Hộ oản',
  belt: 'Đai', boots: 'Hài', ring: 'Nhẫn', pendant: 'Bội',
};

const meta = {
  generatedAt: new Date().toISOString(),
  source: 'Vấn Đạo: Nghịch Mệnh client bundle',
  stats,
  attrs,
  origins,
  currencies,
  activities,
  rarities,
  slots,
  items,
  equipment,
  sets,
  skills,
  spots,
  regions,
  realms,
  quests,
  pets,
  daily: m.Gi.map((t) => ({ ...t, name: tr[t.nameKey] || prettify(t.id) })),
  weekly: m.aa.map((t) => ({ ...t, name: tr[t.nameKey] || prettify(t.id) })),
  achievements: Object.fromEntries(Object.entries(m.zi).map(([id, a]) => [
    id,
    { ...a, name: tr[a.nameKey] || prettify(id) },
  ])),
  titles: m.Jo,
};

fs.writeFileSync(fileURLToPath(new URL('../data/meta.json', import.meta.url)), JSON.stringify(meta, null, 1));
console.log('meta written');
console.log('items', Object.keys(items).length, 'equipment', Object.keys(equipment).length, 'skills', Object.keys(skills).length);
console.log('spots', Object.keys(spots).length, 'regions', Object.keys(regions).length, 'quests', Object.keys(quests).length);
console.log('sample item', items.item_qi_pill);
console.log('sample equip', equipment.equip_t1_weapon);
