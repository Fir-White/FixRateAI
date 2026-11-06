import type { ReactNode } from "react";

export type IconName =
  | "dashboard"
  | "equipment"
  | "calendar"
  | "service"
  | "tasks"
  | "forecast"
  | "report"
  | "quality"
  | "executor"
  | "logout"
  | "chevron"
  | "alert"
  | "clock"
  | "check"
  | "camera"
  | "search"
  | "user"
  | "back"
  | "plus"
  | "upload"
  | "menu"
  | "sidebar"
  | "close"
  | "bell"
  | "trash";

const PATHS: Record<IconName, ReactNode> = {
  sidebar: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></>,
  trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5"/></>,
  bell: <><path d="M5 17.5h14l-1.2-1.7a4 4 0 0 1-.8-2.4V10a5 5 0 0 0-10 0v3.4a4 4 0 0 1-.8 2.4L5 17.5Z"/><path d="M10 20a2.2 2.2 0 0 0 4 0M12 3v2"/></>,
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="4" rx="1.5" />
      <rect x="14" y="11" width="7" height="10" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  equipment: (
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.1-3.1a6 6 0 0 1-8.3 7.9l-7.2 7.2a2.1 2.1 0 0 1-3-3l7.2-7.2a6 6 0 0 1 7.9-8.3Z" />
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
    </>
  ),
  service: (
    <>
      <path d="M10 3.5h4l.5 2.1c.5.2 1 .4 1.4.7l1.9-1.1 2.8 2.8-1.1 1.9c.3.4.5.9.7 1.4l2.1.5v4l-2.1.5c-.2.5-.4 1-.7 1.4l1.1 1.9-2.8 2.8-1.9-1.1c-.4.3-.9.5-1.4.7L14 22h-4l-.5-2.1c-.5-.2-1-.4-1.4-.7l-1.9 1.1-2.8-2.8 1.1-1.9c-.3-.4-.5-.9-.7-1.4L1.7 14v-4l2.1-.5c.2-.5.4-1 .7-1.4L3.4 6.2l2.8-2.8 1.9 1.1c.4-.3.9-.5 1.4-.7Z" transform="translate(0 0.5) scale(.96)" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  tasks: (
    <>
      <path d="M9 6h11M9 12h11M9 18h11" />
      <path d="m3.5 6 1.5 1.5L7.5 5M3.5 12l1.5 1.5L7.5 11M3.5 18l1.5 1.5L7.5 17" />
    </>
  ),
  forecast: (
    <>
      <path d="M3 17l5-5 4 4 6-8" />
      <path d="M15 8h4v4" />
      <path d="M3 21h18" />
    </>
  ),
  report: (
    <>
      <path d="M4 20h16M6 17V9M12 17V4M18 17v-6" />
    </>
  ),
  quality: (
    <>
      <path d="M12 3 5 6v5c0 4.5 2.8 8.4 7 10 4.2-1.6 7-5.5 7-10V6l-7-3Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  executor: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 21c0-4 3.1-6.5 7-6.5s7 2.5 7 6.5" />
    </>
  ),
  logout: (
    <>
      <path d="M10 4H5v16h5" />
      <path d="M14 8l4 4-4 4M18 12H9" />
    </>
  ),
  chevron: <path d="m9 18 6-6-6-6" />,
  alert: (
    <>
      <path d="M12 3 2.5 20h19L12 3Z" />
      <path d="M12 9v5M12 17.5v.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  check: <path d="m4 12 5 5L20 6" />,
  camera: (
    <>
      <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
      <circle cx="12" cy="13" r="3.5" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 5 5" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 21c0-4 3.1-6.5 7-6.5s7 2.5 7 6.5" />
    </>
  ),
  back: (
    <>
      <path d="M19 12H5" />
      <path d="m11 18-6-6 6-6" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  upload: (
    <>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 16v4h16v-4" />
    </>
  ),
  menu: (
    <>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </>
  ),
  close: (
    <>
      <path d="m6 6 12 12M18 6 6 18" />
    </>
  ),
};

export function Icon({
  name,
  size = 20,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
