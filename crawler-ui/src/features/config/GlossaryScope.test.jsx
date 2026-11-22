import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, act } from "@testing-library/react";
import { Explain, Term } from "../../shared/ui";
import GlossaryScope from "./GlossaryScope";
import { primeGlossary, resetGlossaryForTests } from "./glossary";

const { fetchConfigSchema } = vi.hoisted(() => ({ fetchConfigSchema: vi.fn() }));
vi.mock("../../api/client", () => ({ fetchConfigSchema }));

const GLOSSARY = { backoff: "The pause after too many requests.", "seed page": "A page a crawl starts from." };

beforeEach(() => {
  fetchConfigSchema.mockReset();
  fetchConfigSchema.mockResolvedValue({ ui_glossary: GLOSSARY });
});
afterEach(() => {
  cleanup();
  resetGlossaryForTests();
});

describe("GlossaryScope", () => {
  it("explains the words of a glossary that was primed", () => {
    act(() => primeGlossary(GLOSSARY));
    render(
      <GlossaryScope>
        <p>
          <Explain text="The backoff grows." /> <Term term="Seed page" />
        </p>
      </GlossaryScope>,
    );
    expect(screen.getByRole("button", { name: "backoff" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Seed page" })).toBeTruthy();
    expect(fetchConfigSchema).not.toHaveBeenCalled();
  });

  it("loads the glossary from the backend schema when nothing primed it, then explains", async () => {
    render(
      <GlossaryScope>
        <p>
          <Explain text="The backoff grows." />
        </p>
      </GlossaryScope>,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(await screen.findByRole("button", { name: "backoff" })).toBeTruthy();
    expect(fetchConfigSchema).toHaveBeenCalledTimes(1);
  });

  it("leaves the words as plain text when the backend cannot be reached", async () => {
    fetchConfigSchema.mockRejectedValue(new Error("offline"));
    render(
      <GlossaryScope>
        <p>
          <Explain text="The backoff grows." />
        </p>
      </GlossaryScope>,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("The backoff grows.")).toBeTruthy();
  });
});
