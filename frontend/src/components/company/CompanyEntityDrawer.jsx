import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export default function CompanyEntityDrawer({
  eyebrow = "DETAIL",
  title,
  subtitle = "",
  open,
  onClose,
  children,
  className = "",
}) {
  const closeRef = useRef(null);
  const drawerRef = useRef(null);
  const titleRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const appRoot = document.getElementById("root");
    const previousInert = appRoot?.inert;
    const previousAriaHidden = appRoot?.getAttribute("aria-hidden");
    document.body.style.overflow = "hidden";
    if (appRoot) {
      appRoot.inert = true;
      appRoot.setAttribute("aria-hidden", "true");
    }

    const focusable = () => Array.from(drawerRef.current?.querySelectorAll(FOCUSABLE_SELECTOR) || [])
      .filter((element) => !element.hasAttribute("disabled") && element.getAttribute("aria-hidden") !== "true");

    titleRef.current?.focus?.({ preventScroll: true });

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      if (!elements.length) {
        event.preventDefault();
        drawerRef.current?.focus?.();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (!elements.includes(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (appRoot) {
        appRoot.inert = Boolean(previousInert);
        if (previousAriaHidden === null) appRoot.removeAttribute("aria-hidden");
        else appRoot.setAttribute("aria-hidden", previousAriaHidden);
      }
      if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
    };
  }, [onClose, open]);

  if (!open) return null;

  return createPortal(
    <div
      className="company-entity-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        ref={drawerRef}
        className={`company-entity-drawer ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="company-entity-drawer-header">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h2 ref={titleRef} id={titleId} tabIndex={-1}>{title || "상세정보"}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button ref={closeRef} type="button" className="icon-button" onClick={onClose} aria-label="상세정보 닫기">
            <X size={18} />
          </button>
        </div>
        <div className="company-entity-drawer-content">
          {children}
        </div>
      </aside>
    </div>,
    document.body,
  );
}
