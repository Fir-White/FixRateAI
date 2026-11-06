import { afterEach, expect, it, vi } from "vitest";
import { ApiQueryCache } from "@/shared/lib/apiQueryCache";

afterEach(() => vi.useRealTimers());

it("shares concurrent reads and retains only successful results", async () => {
  const cache = new ApiQueryCache(), loader = vi.fn().mockResolvedValue([1]);
  const first = cache.load("tasks", loader), second = cache.load("tasks", loader);
  expect(second).toBe(first);
  expect(await first).toEqual([1]);
  expect(await cache.load("tasks", loader)).toEqual([1]);
  expect(loader).toHaveBeenCalledOnce();
  const failure = vi.fn().mockRejectedValue(new Error("Offline"));
  await expect(cache.load("other", failure)).rejects.toThrow("Offline");
  expect(cache.peek("other")).toBeUndefined();
});

it("revalidates an older snapshot and expires it after a minute", async () => {
  vi.useFakeTimers();
  const cache = new ApiQueryCache(), loader = vi.fn().mockResolvedValueOnce([1]).mockResolvedValue([2]);
  await cache.load("tasks", loader);
  vi.advanceTimersByTime(10_001);
  expect(cache.peek("tasks")?.data).toEqual([1]);
  expect(await cache.load("tasks", loader)).toEqual([2]);
  vi.advanceTimersByTime(60_001);
  expect(cache.peek("tasks")).toBeUndefined();
});

it("does not let a read that preceded a mutation repopulate the cache", async () => {
  const cache = new ApiQueryCache();
  let resolve!: (data: number[]) => void;
  const old = cache.load("tasks", () => new Promise<number[]>(done => { resolve = done; }));
  await Promise.resolve();
  cache.clear();
  await cache.load("tasks", async () => [2]);
  resolve([1]);await old;
  expect(cache.peek("tasks")?.data).toEqual([2]);
});

it("bounds memory instead of keeping every visited month indefinitely", async () => {
  const cache = new ApiQueryCache();
  for (let i = 0; i < 70; i++) await cache.load(`month:${i}`, async () => i);
  expect(cache.peek("month:0")).toBeUndefined();
  expect(cache.peek("month:69")?.data).toBe(69);
});
