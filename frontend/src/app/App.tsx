import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";

const router = createBrowserRouter([{path:"*",element:<AppRouter />}]);

export function App() {
  return (
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>
  );
}
