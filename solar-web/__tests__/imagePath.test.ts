import { describe, it, expect } from "vitest";
import { indexToImagePath } from "../lib/imagePath";

describe("indexToImagePath", () => {
  it("appends .png to index", () => {
    expect(indexToImagePath("BOULDER_CO_1014")).toBe("BOULDER_CO_1014.png");
  });

  it("handles different county formats", () => {
    expect(indexToImagePath("SANDIEGO_CA_500")).toBe("SANDIEGO_CA_500.png");
  });
});
