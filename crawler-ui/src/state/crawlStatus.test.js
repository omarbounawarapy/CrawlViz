import { describe, it, expect } from "vitest";
import { crawlStatusWords, humanizeStopReason } from "./crawlStatus";

describe("crawlStatusWords", () => {
  it("names the three lifecycle states", () => {
    expect(crawlStatusWords({ status: "IDLE" })).toEqual({ word: "Idle", reason: null });
    expect(crawlStatusWords({ status: "RUNNING" })).toEqual({ word: "Crawling", reason: null });
  });

  it("says a crawl that ended on its own is finished, and why", () => {
    expect(crawlStatusWords({ status: "STOPPED", stop_reason: "MAX_NODES" })).toEqual({
      word: "Finished",
      reason: "max nodes",
    });
    expect(crawlStatusWords({ status: "STOPPED" })).toEqual({ word: "Finished", reason: null });
  });

  it("says a crawl the user stopped was stopped by them, with no reason to add", () => {
    expect(crawlStatusWords({ status: "STOPPED", stop_reason: "USER_REQUEST", stopped_by_user: true })).toEqual({
      word: "Stopped by you",
      reason: null,
    });
  });

  it("does not report a stop reason while the crawl is running", () => {
    expect(crawlStatusWords({ status: "RUNNING", stop_reason: "MAX_NODES" }).reason).toBeNull();
  });

  it("lower-cases a reason and turns underscores into spaces", () => {
    expect(humanizeStopReason("TIME_LIMIT_REACHED")).toBe("time limit reached");
  });
});
