import { describe, it, expect } from "vitest";
import { DEFAULT_BLUEPRINT, validateBlueprint } from "./blueprintModel";

const topicErrors = (target_topic) =>
  validateBlueprint({ ...DEFAULT_BLUEPRINT, target_topic }).filter((e) => e.id === "bp-target_topic");

describe("validateBlueprint target topic", () => {
  it("asks for a topic when the field is empty or blank", () => {
    expect(topicErrors("")).toEqual([{ id: "bp-target_topic", message: "Target topic is required." }]);
    expect(topicErrors("   ")).toHaveLength(1);
  });

  it.each(["!!!", "...", "- / -", "   ?  "])("rejects %j, which has no letter, digit or underscore", (topic) => {
    const errors = topicErrors(topic);
    expect(errors).toHaveLength(1);
    expect(errors[0].message).toMatch(/letter or digit/);
  });

  it.each(["type 2 diabetes", "糖尿病", "Диабет", "2024", "_", "C++"])("accepts %j", (topic) => {
    expect(topicErrors(topic)).toEqual([]);
  });
});
