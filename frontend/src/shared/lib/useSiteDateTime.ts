import { useSession } from "@/shared/session/SessionContext";
import { formatDateTime } from "./format";

export function useSiteDateTime() {
  const {profile}=useSession();
  return (value:string|null)=>formatDateTime(value,profile?.timezone??"UTC");
}
