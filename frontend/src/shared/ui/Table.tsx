import type {
  HTMLAttributes,
  ReactNode,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";

export function Table({
  label,
  minWidth = 760,
  children,
  className = "",
}: {
  label: string;
  minWidth?: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className={`overflow-x-auto rounded-b-2xl focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent ${className}`}
    >
      <table
        className="w-full border-collapse text-left"
        style={{ minWidth }}
      >
        {children}
      </table>
    </div>
  );
}

export function Tr({
  highlighted = false,
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLTableRowElement> & {
  highlighted?: boolean;
  children: ReactNode;
}) {
  return (
    <tr
      className={`group border-b border-line last:border-0 transition-colors hover:bg-white/[0.03] ${
        highlighted ? "bg-rose-400/[0.055]" : ""
      } ${className}`}
      {...props}
    >
      {children}
    </tr>
  );
}

export function Th({
  className = "",
  children,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <th
      scope="col"
      className={`border-b border-line px-4 py-3 text-[10px] font-semibold tracking-[0.16em] text-muted uppercase first:pl-5 last:pr-5 sm:first:pl-6 sm:last:pr-6 ${className}`}
      {...props}
    >
      {children}
    </th>
  );
}

export function Td({
  className = "",
  children,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <td
      className={`px-4 py-4 align-middle text-sm text-ink-soft first:pl-5 last:pr-5 sm:first:pl-6 sm:last:pr-6 ${className}`}
      {...props}
    >
      {children}
    </td>
  );
}
