import type { DetailsHTMLAttributes, ReactNode } from "react";
import { Icon } from "./Icon";
import "./disclosure.css";

export function Disclosure({ title, children, className = "", ...props }: Omit<DetailsHTMLAttributes<HTMLDetailsElement>, "title"> & { title: string; children: ReactNode }) {
  return <details {...props} className={`fr-disclosure ${className}`}>
    <summary><span>{title}</span><Icon name="chevron" size={18}/></summary>
    <div className="fr-disclosure-body">{children}</div>
  </details>;
}
