import {
  Children,
  Fragment,
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ComponentPropsWithoutRef,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { useFeedbackMotion } from "@/shared/motion/useFeedbackMotion";
import "./Form.css";
import { CalendarInput } from "./CalendarInput";
import { FileInput } from "./FileInput";
import { Icon } from "./Icon";

const CONTROL_CLASSES =
  "motion-input ui-control w-full min-w-0 rounded-lg border border-line-strong bg-canvas-soft text-sm text-ink placeholder:text-muted/60 transition-colors hover:border-muted/50 focus:border-accent focus:ring-2 focus:ring-accent/15 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50";

export function FieldCaption({ children }: { children: ReactNode }) {
  return <span className="field-caption">{children}</span>;
}

export function FormField({
  label,
  htmlFor,
  hint,
  error,
  required = false,
  children,
  className = "",
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  const generatedId = useId();
  const child = isValidElement(children) ? children as ReactElement<Record<string, unknown>> : null;
  const controlId = htmlFor ?? (typeof child?.props.id === "string" ? child.props.id : generatedId);
  const descriptionId = `${controlId}-description`;
  const describedBy = [
    typeof child?.props["aria-describedby"] === "string" ? child.props["aria-describedby"] : undefined,
    error || hint ? descriptionId : undefined,
  ].filter(Boolean).join(" ") || undefined;
  const feedback = useFeedbackMotion(error || hint);
  const control = child && (typeof child.type !== "string" || ["input", "select", "textarea", "button"].includes(child.type))
    ? cloneElement(child, {
        id: controlId,
        "aria-describedby": describedBy,
        ...(error ? { "aria-invalid": true } : {}),
      })
    : children;

  return (
    <div className={`min-w-0 ${className}`}>
      <label
        htmlFor={controlId}
        className="ui-field-label mb-1.5 block text-xs font-semibold text-ink-soft"
      >
        <FieldCaption>
        {label}
        {required ? (
          <span aria-hidden="true" className="ml-1 text-rose-300">
            *
          </span>
        ) : null}
        </FieldCaption>
      </label>
      {control}
      <div ref={feedback} className="form-feedback">
      {error ? (
        <p
          id={descriptionId}
          role="alert"
          className="mt-1.5 text-xs leading-5 text-rose-300"
        >
          <FieldCaption>{error}</FieldCaption>
        </p>
      ) : hint ? (
        <p
          id={descriptionId}
          className="mt-1.5 text-xs leading-5 text-muted"
        >
          <FieldCaption>{hint}</FieldCaption>
        </p>
      ) : null}
      </div>
    </div>
  );
}

export function Input({
  leadingIcon,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  leadingIcon?: ReactNode;
}) {
  if (["date", "datetime-local", "month", "time"].includes(props.type ?? "")) {
    return <CalendarInput {...props} className={className} />;
  }
  if (props.type === "file") return <FileInput {...props} className={className} />;
  const input = (
    <input
      className={`${CONTROL_CLASSES} h-10 px-3 ${leadingIcon ? "pl-10" : ""} ${className}`}
      {...props}
    />
  );

  if (!leadingIcon) {
    return input;
  }

  return (
    <span className="relative block">
      <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted">
        {leadingIcon}
      </span>
      {input}
    </span>
  );
}

type SelectOptionItem = {
  value: string;
  label: string;
  disabled: boolean;
  group?: string;
};

function nodeText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return nodeText(node.props.children);
  return "";
}

function extractSelectOptions(children: ReactNode, group?: string): SelectOptionItem[] {
  const items: SelectOptionItem[] = [];
  Children.forEach(children, (child) => {
    if (!isValidElement<Record<string, unknown>>(child)) return;
    if (child.type === Fragment) {
      items.push(...extractSelectOptions(child.props.children as ReactNode, group));
      return;
    }
    if (child.type === "optgroup") {
      const groupLabel = typeof child.props.label === "string" ? child.props.label : "";
      const groupDisabled = Boolean(child.props.disabled);
      for (const item of extractSelectOptions(child.props.children as ReactNode, groupLabel)) {
        items.push({ ...item, disabled: item.disabled || groupDisabled });
      }
      return;
    }
    if (child.type === "option") {
      const label = nodeText(child.props.children as ReactNode);
      const rawValue = child.props.value;
      const value = rawValue !== undefined ? String(rawValue) : label;
      items.push({
        value,
        label,
        disabled: Boolean(child.props.disabled),
        group,
      });
    }
  });
  return items;
}

export function Select({
  className = "",
  children,
  value,
  defaultValue,
  disabled,
  onChange,
  onMouseDown,
  onKeyDown,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const generatedId = useId();
  const listboxId = `${props.id ?? generatedId}-listbox`;
  const rootRef = useRef<HTMLSpanElement>(null);
  const selectRef = useRef<HTMLSelectElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const options = useMemo(() => extractSelectOptions(children), [children]);
  const [internalValue, setInternalValue] = useState<string>(() => {
    if (defaultValue !== undefined) return String(defaultValue);
    return options.find((item) => !item.disabled)?.value ?? options[0]?.value ?? "";
  });
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [position, setPosition] = useState<CSSProperties>({
    left: 8,
    top: 0,
    width: 240,
    maxHeight: 320,
  });

  const currentValue = value !== undefined ? String(value) : internalValue;

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (!open) return;
    const selectedIdx = options.findIndex((item) => item.value === currentValue && !item.disabled);
    const fallbackIdx = options.findIndex((item) => !item.disabled);
    setActiveIndex(selectedIdx >= 0 ? selectedIdx : fallbackIdx);
  }, [open, options, currentValue]);

  useLayoutEffect(() => {
    const field = selectRef.current;
    if (!open || !field) return;
    const viewport = window.visualViewport;
    const placeMenu = () => {
      const bounds = field.getBoundingClientRect();
      const vw = window.innerWidth || 1024;
      const vh = viewport ? viewport.offsetTop + viewport.height : (window.innerHeight || 768);
      const vTop = viewport?.offsetTop ?? 0;
      const below = vh - bounds.bottom - 12;
      const above = bounds.top - vTop - 12;
      const opensBelow = below >= 200 || below >= above;
      const width = bounds.width > 0 ? Math.min(Math.max(bounds.width, 180), vw - 16) : 240;
      const left = bounds.width > 0 ? Math.max(8, Math.min(bounds.left, vw - width - 8)) : 8;
      const maxHeight = Math.min(320, Math.max(120, opensBelow ? below : above));
      setPosition({
        left,
        width,
        maxHeight,
        ...(opensBelow
          ? { top: bounds.bottom + 6 }
          : { bottom: (window.innerHeight || 768) - bounds.top + 6 }),
      });
    };
    placeMenu();
    const handleScroll = (event: Event) => {
      if (menuRef.current && event.target instanceof Node && menuRef.current.contains(event.target)) {
        return;
      }
      placeMenu();
    };
    window.addEventListener("resize", placeMenu);
    window.addEventListener("scroll", handleScroll, { capture: true, passive: true });
    viewport?.addEventListener("resize", placeMenu);
    viewport?.addEventListener("scroll", placeMenu);
    return () => {
      window.removeEventListener("resize", placeMenu);
      window.removeEventListener("scroll", handleScroll, true);
      viewport?.removeEventListener("resize", placeMenu);
      viewport?.removeEventListener("scroll", placeMenu);
    };
  }, [open, options.length]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent | PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  const chooseOption = (nextValue: string) => {
    const field = selectRef.current;
    if (!field || field.matches(":disabled")) return;
    setOpen(false);
    if (value === undefined) setInternalValue(nextValue);
    if (field.value !== nextValue) {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(field, nextValue);
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }
    field.focus();
  };

  const stepActive = (delta: 1 | -1) => {
    if (!options.some((item) => !item.disabled)) return;
    let idx = activeIndex;
    for (let step = 0; step < options.length; step++) {
      idx = (idx + delta + options.length) % options.length;
      if (!options[idx].disabled) {
        setActiveIndex(idx);
        menuRef.current
          ?.querySelector<HTMLElement>(`[data-option-index="${idx}"]`)
          ?.scrollIntoView?.({ block: "nearest" });
        return;
      }
    }
  };

  const portalRoot =
    typeof document !== "undefined"
      ? (selectRef.current?.closest(".fr-content-v2") ??
        document.querySelector(".fr-content-v2") ??
        document.querySelector(".workspace-root") ??
        document.body)
      : null;

  return (
    <span ref={rootRef} className="fr-select" data-open={open || undefined}>
      <select
        ref={selectRef}
        className={`${CONTROL_CLASSES} ui-select h-10 px-3 pr-9 ${className}`}
        value={value}
        defaultValue={defaultValue}
        disabled={disabled}
        data-open={open || undefined}
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onMouseDown={(event) => {
          onMouseDown?.(event);
          if (event.defaultPrevented || event.button !== 0 || event.currentTarget.matches(":disabled")) {
            return;
          }
          event.preventDefault();
          event.currentTarget.focus();
          setOpen((prev) => !prev);
        }}
        onKeyDown={(event) => {
          onKeyDown?.(event);
          if (event.defaultPrevented || event.currentTarget.matches(":disabled")) return;
          if (!open) {
            if (
              event.key === "Enter" ||
              event.key === " " ||
              (event.altKey && (event.key === "ArrowDown" || event.key === "ArrowUp"))
            ) {
              event.preventDefault();
              setOpen(true);
            }
            return;
          }
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            setOpen(false);
          } else if (event.key === "Tab") {
            setOpen(false);
          } else if (event.key === "ArrowDown") {
            event.preventDefault();
            stepActive(1);
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            stepActive(-1);
          } else if (event.key === "Home") {
            event.preventDefault();
            const first = options.findIndex((item) => !item.disabled);
            if (first >= 0) setActiveIndex(first);
          } else if (event.key === "End") {
            event.preventDefault();
            for (let i = options.length - 1; i >= 0; i--) {
              if (!options[i].disabled) {
                setActiveIndex(i);
                break;
              }
            }
          } else if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            const item = options[activeIndex];
            if (item && !item.disabled) chooseOption(item.value);
          }
        }}
        onChange={(event) => {
          setOpen(false);
          if (value === undefined) setInternalValue(event.target.value);
          onChange?.(event);
        }}
        {...props}
      >
        {children}
      </select>
      {open &&
        portalRoot &&
        options.length > 0 &&
        createPortal(
          <div
            ref={menuRef}
            id={listboxId}
            role="listbox"
            className="fr-select-popover"
            style={position}
          >
            {options.map((option, index) => {
              const selected = option.value === currentValue;
              const active = index === activeIndex;
              const prevGroup = index > 0 ? options[index - 1].group : undefined;
              const showGroup = option.group && option.group !== prevGroup;
              return (
                <Fragment key={`${option.group ?? ""}:${option.value}:${index}`}>
                  {showGroup && (
                    <div className="fr-select-group" role="presentation">
                      {option.group}
                    </div>
                  )}
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    disabled={option.disabled}
                    data-option-index={index}
                    data-selected={selected || undefined}
                    data-active={active || undefined}
                    className="fr-select-option"
                    onMouseEnter={() => setActiveIndex(index)}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => chooseOption(option.value)}
                  >
                    <span>{option.label}</span>
                    {selected && <Icon name="check" size={16} />}
                  </button>
                </Fragment>
              );
            })}
          </div>,
          portalRoot,
        )}
    </span>
  );
}

export function Textarea({
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`${CONTROL_CLASSES} min-h-24 resize-y px-3 py-2.5 ${className}`}
      {...props}
    />
  );
}

export function Checkbox({
  label,
  className = "",
  ...props
}: Omit<ComponentPropsWithoutRef<"input">, "type"> & { label: string }) {
  return (
    <label
      className={`inline-flex items-center gap-2.5 text-sm text-ink-soft ${className}`}
    >
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-line-strong bg-white/[0.04] accent-accent"
        {...props}
      />
      {label}
    </label>
  );
}
