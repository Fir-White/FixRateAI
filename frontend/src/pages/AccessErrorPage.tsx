import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { AccessBrand } from "@/shared/ui/Brand";
import { buttonClassName } from "@/shared/ui/Button";
import "./access-theme.css";
import "./AccessErrorPage.css";

export function AccessErrorPage({ code, title, children, target, action }: {
  code: 403 | 404;
  title: string;
  children: ReactNode;
  target: string;
  action: string;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const { key } = useLocation();
  useEffect(() => {
    heading.current?.focus();
  }, [key]);

  return (
    <main className="access-error-page" data-code={code} aria-labelledby="access-error-title">
      <div className="access-error-content">
        <AccessBrand />
        <p id="access-error-code" className="access-error-code">{code}</p>
        <h1 ref={heading} id="access-error-title" aria-describedby="access-error-code" tabIndex={-1}>
          {title}
        </h1>
        <div className="access-error-description">{children}</div>
        <Link to={target} className={buttonClassName("primary", "md", "access-error-action")}>
          {action}
        </Link>
      </div>
    </main>
  );
}
