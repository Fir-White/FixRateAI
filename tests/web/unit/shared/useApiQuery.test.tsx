import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useApiQuery } from "@/shared/lib/useApiQuery";

afterEach(()=>vi.useRealTimers());
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
