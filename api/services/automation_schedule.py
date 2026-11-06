"""Pure fair scheduling: fixed safety setup, then rotate enabled feature groups."""

FEATURE_FLAGS = {
    "claims": ("autoQuests", "autoDaily", "autoWeekly", "autoAchievements", "autoMail", "autoX2Daily"),
    "extra_rewards": ("autoSectTasks", "autoSeasonTasks", "autoTitles"),
    "guild_checkin": ("autoGuildCheckin",),
    "world_boss": ("autoWorldBoss",),
    "guild_boss": ("autoGuildBoss",),
    "titles": ("autoEquipTitle",),
    "encounters": ("autoEncounter",),
    "equipment": ("autoEquipBest", "autoCleanup"),
    "major": ("autoMajorBreakthrough",),
    "minor": ("autoMinorTrial",),
    "pets": ("autoPetAdopt", "autoHunt"),
    "npc": ("autoNpcTalk", "autoNpcRewards"),
    "pill": ("autoUse",),
    "cave": ("autoCaveUpgrade",),
    "craft": ("autoCraft", "autoMajorBreakthrough"),
    "donate": ("autoSectDonate",),
    "boss": ("autoBoss",),
    "farm": ("autoFarm",),
    "arena": ("autoArena",),
}


def feature_order(config: dict, cursor: str | None = None) -> list[str]:
    keys = list(FEATURE_FLAGS)
    # When a feature was disabled, continue to the next enabled neighbour.
    start = keys.index(cursor) if isinstance(cursor, str) and cursor in keys else 0
    keys = keys[start:] + keys[:start]
    return [key for key in keys if any(config.get(flag) for flag in FEATURE_FLAGS[key])
            and (key != "donate" or config.get("autoSectTasks"))]
