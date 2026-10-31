import { BrowserRouter } from "react-router-dom";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";

export function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
    </SessionProvider>
  );
}
