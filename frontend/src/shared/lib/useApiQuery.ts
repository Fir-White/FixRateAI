import { useEffect, useState, type DependencyList } from "react";

export type ApiQuery<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: string };

export function useApiQuery<T>(
  loader: () => Promise<T>,
  dependencies: DependencyList,
  pollWhile?: (data: T) => boolean,
): ApiQuery<T> {
  const [state, setState] = useState<ApiQuery<T>>({
    status: "loading",
    data: null,
    error: null,
  });

  useEffect(() => {
    let active = true;
    setState({ status: "loading", data: null, error: null });

    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () => loader()
      .then((data) => {
        if (active) {
          setState({ status: "success", data, error: null });
          if (pollWhile?.(data)) timer = setTimeout(load, 3000);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setState({
            status: "error",
            data: null,
            error:
              error instanceof Error
                ? error.message
                : "Не удалось загрузить данные",
          });
        }
      });

    void load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, dependencies);

  return state;
}
