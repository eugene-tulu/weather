import { describe, expect, it } from "vitest";

import { MAP_PRODUCTS } from "@/lib/map-products";
import { MODEL_VARIABLES, VARS } from "@/lib/models";

describe("map products", () => {
  it("has unique ids", () => {
    const ids = MAP_PRODUCTS.map((product) => product.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("only references surface variables that exist in the UI", () => {
    const variableIds = new Set(VARS.map((variable) => variable.id));
    for (const available of Object.values(MODEL_VARIABLES)) {
      for (const variable of available) {
        expect(variableIds.has(variable)).toBe(true);
      }
    }
  });

  it("keeps the global map catalog populated", () => {
    expect(MAP_PRODUCTS.length).toBeGreaterThanOrEqual(6);
    expect(MAP_PRODUCTS.some((product) => product.id.includes("gefs"))).toBe(true);
    expect(MAP_PRODUCTS.some((product) => product.id.includes("ecmwf"))).toBe(true);
  });
});
