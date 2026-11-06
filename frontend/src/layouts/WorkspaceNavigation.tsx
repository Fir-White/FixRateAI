import { createContext, useContext, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate, useNavigationType } from "react-router-dom";

const NavigationContext = createContext<(() => void) | null>(null);

/** Track only entries visited during this authenticated workspace session. */
export function WorkspaceNavigation({ home, children }: { home: string; children: ReactNode }) {
  const location = useLocation();
  const action = useNavigationType();
  const navigate = useNavigate();
  const keys = useRef<string[]>([]);
  const [canGoBack, setCanGoBack] = useState(false);

  useLayoutEffect(() => {
    const stack = keys.current;
    if (stack.at(-1) === location.key) return;
    if (action === "PUSH") stack.push(location.key);
    else if (action === "REPLACE" && stack.length) stack[stack.length - 1] = location.key;
    else {
      const index = stack.indexOf(location.key);
      if (index >= 0) stack.splice(index + 1);
      else keys.current = [location.key];
    }
    setCanGoBack(keys.current.length > 1);
  }, [location.key, action]);

  const back = () => canGoBack ? navigate(-1) : navigate(home, {replace: true});
  return <NavigationContext.Provider value={back}>{children}</NavigationContext.Provider>;
}

export function useWorkspaceBack() {
  const back = useContext(NavigationContext);
  if (!back) throw new Error("WorkspaceNavigation is missing");
  return back;
}
