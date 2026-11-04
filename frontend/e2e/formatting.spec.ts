import { test, expect } from "@playwright/test";
import { display, normalize, number, percent, realmName } from "../src/lib";
import { activeAutos, configEqual } from "../src/automation-config";
import { defaultConfig, meta } from "./fixtures";

test("formatters safely handle unknown objects, big integers and invalid counters", () => {
  expect(number("900719925474099312345")).toBe("900.719.925.474.099.312.345");
  expect(number(undefined)).toBe("—"); expect(number("NaN")).toBe("—");
  expect(percent(120, 100)).toBe(100); expect(percent(20, 0)).toBe(0); expect(percent(-10, 100)).toBe(0);
  expect(display({ stage: 2, realmId: "ket_dan" })).toContain("ket_dan");
  expect(normalize("Đụn Cát ĐỎ")).toBe("dun cat do");
  expect(realmName({ realmId: "ket_dan", stage: 2 }, meta.realms)).toBe("Kết Đan · Trung kỳ");
  expect(realmName({ realmId: "unknown", stage: 3 }, {})).toBe("unknown · Tầng 3");
});
test("config equality is key-order independent and counts only principal actions", () => {
  expect(configEqual({ a: true, b: 3 }, { b: 3, a: true })).toBe(true);
  expect(configEqual({ a: true }, { a: false })).toBe(false);
  expect(activeAutos(defaultConfig).map((flag) => flag.key)).toEqual(["autoMinor", "autoQuests", "autoDaily", "autoMail"]);
});
