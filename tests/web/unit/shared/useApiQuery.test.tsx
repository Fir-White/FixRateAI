import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, StrictMode, type ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { useApiQuery } from "@/shared/lib/useApiQuery";
import { ApiQueryProvider } from "@/shared/lib/ApiQueryProvider";
import { invalidateApiQueries } from "@/shared/lib/apiQueryCache";

afterEach(()=>vi.useRealTimers());
const wrapper = ({ children }: { children: ReactNode }) => createElement(StrictMode, null, createElement(ApiQueryProvider, { scope: "user:one", children }));

it("reopens a cached tab synchronously, without a loading frame or another request", async () => {
 const loader=vi.fn().mockResolvedValue(["current"]);
 const {result,rerender}=renderHook(({visible})=>({first:useApiQuery(loader,[],undefined,"tasks"),second:useApiQuery(loader,[],undefined,visible?"tasks":undefined)}),{wrapper,initialProps:{visible:false}});
 await waitFor(()=>expect(result.current.first.status).toBe("success"));
 const calls=loader.mock.calls.length;
 rerender({visible:true});
 expect(result.current.second).toMatchObject({status:"success",data:["current"]});
 await act(async()=>{await Promise.resolve();});
 expect(loader).toHaveBeenCalledTimes(calls);
});

it("invalidates future tabs after a mutation while preserving the mounted snapshot", async () => {
 const loader=vi.fn().mockResolvedValueOnce(["old"]).mockResolvedValue(["new"]);
 const {result,rerender}=renderHook(({refresh})=>useApiQuery(loader,[refresh],undefined,"tasks"),{wrapper,initialProps:{refresh:0}});
 await waitFor(()=>expect(result.current.data).toEqual(["old"]));
 act(()=>invalidateApiQueries());
 expect(result.current.data).toEqual(["old"]);
 rerender({refresh:1});
 await waitFor(()=>expect(result.current.data).toEqual(["new"]));
});

it("does not reuse another user or object's cached records", async () => {
 const loader=vi.fn().mockResolvedValueOnce(["one"]).mockResolvedValue(["two"]);
 const Scoped=({scope}:{scope:string})=>useApiQuery(loader,[],undefined,scope);
 const {result,rerender}=renderHook(Scoped,{wrapper,initialProps:{scope:"object:one"}});
 await waitFor(()=>expect(result.current.data).toEqual(["one"]));
 rerender({scope:"object:two"});
 expect(result.current.data).not.toEqual(["one"]);
 await waitFor(()=>expect(result.current.data).toEqual(["two"]));
});

it("discards the cache when the authenticated user or site changes", async () => {
 let scope="user:one/site:one";
 const scopedWrapper=({children}:{children:ReactNode})=>createElement(ApiQueryProvider,{scope,children});
 const loader=vi.fn().mockResolvedValueOnce(["private-one"]).mockResolvedValue(["private-two"]);
 const {result,rerender}=renderHook(()=>useApiQuery(loader,[],undefined,"tasks"),{wrapper:scopedWrapper});
 await waitFor(()=>expect(result.current.data).toEqual(["private-one"]));
 scope="user:two/site:two";rerender();
 expect(result.current.data).not.toEqual(["private-one"]);
 await waitFor(()=>expect(result.current.data).toEqual(["private-two"]));
 expect(loader).toHaveBeenCalledTimes(2);
});

it("keeps a cached list visible while revalidating it and exposes a refresh failure", async () => {
 vi.useFakeTimers();const loader=vi.fn().mockResolvedValueOnce(["old"]).mockRejectedValue(new Error("Connection lost"));
 const {result}=renderHook(()=>useApiQuery(loader,[],undefined,"tasks"),{wrapper});
 await act(async()=>{await Promise.resolve();});
 expect(result.current.data).toEqual(["old"]);
 await act(async()=>{vi.advanceTimersByTime(10_001);window.dispatchEvent(new Event("focus"));});
 expect(result.current).toMatchObject({status:"error",error:"Connection lost"});
});
it("polls pending analysis without clearing the report and stops when a result arrives",async()=>{
 vi.useFakeTimers();const load=vi.fn().mockResolvedValueOnce({status:"pending"}).mockResolvedValue({status:"ready"});
 const {result,unmount}=renderHook(()=>useApiQuery<{status:string}>(load,[],data=>data.status==="pending"));
 await act(async()=>{await Promise.resolve();});expect(result.current.status).toBe("success");
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});expect(result.current).toMatchObject({status:"success",data:{status:"ready"}});
 await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});expect(load).toHaveBeenCalledTimes(2);unmount();
});
it("cancels pending refresh on unmount",async()=>{
 vi.useFakeTimers();const load=vi.fn().mockResolvedValue({status:"pending"});
 const {unmount}=renderHook(()=>useApiQuery<{status:string}>(load,[],()=>true));await act(async()=>{await Promise.resolve();});unmount();
 await vi.advanceTimersByTimeAsync(10000);expect(load).toHaveBeenCalledTimes(1);
});
it("shows a refresh failure instead of silently presenting a completed analysis",async()=>{
 vi.useFakeTimers();const load=vi.fn().mockResolvedValueOnce({status:"pending"}).mockRejectedValue(new Error("Connection lost"));
 const {result}=renderHook(()=>useApiQuery<{status:string}>(load,[],()=>true));await act(async()=>{await Promise.resolve();});
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});expect(result.current).toMatchObject({status:"error",error:"Connection lost"});
});
