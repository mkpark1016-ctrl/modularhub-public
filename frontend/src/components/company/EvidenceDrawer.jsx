import { useEffect, useRef } from "react";
import { ExternalLink, X } from "lucide-react";
import { formatSourceDate, sourceHasPublicUrl } from "../../companyEvidence";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export default function EvidenceDrawer({ evidence, onClose }) {
  const closeRef = useRef(null);
  const drawerRef = useRef(null);
  const open = Boolean(evidence);

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const focusable = () => Array.from(drawerRef.current?.querySelectorAll(FOCUSABLE_SELECTOR) || [])
      .filter((element) => !element.hasAttribute("disabled") && element.getAttribute("aria-hidden") !== "true");
    const focusFirstElement = () => {
      const [first] = focusable();
      (first || drawerRef.current || closeRef.current)?.focus?.();
    };
    focusFirstElement();
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
      if (event.shiftKey && document.activeElement === first) {
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
      if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
    };
  }, [onClose, open]);

  if (!open) return null;

  const sources = Array.isArray(evidence.sources) ? evidence.sources : [];
  return (
    <div className="evidence-drawer-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <aside ref={drawerRef} className="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-drawer-title" tabIndex={-1}>
        <div className="evidence-drawer-header">
          <div>
            <p className="eyebrow">EVIDENCE</p>
            <h2 id="evidence-drawer-title">{evidence.title || "근거 보기"}</h2>
            {evidence.value && <p>{evidence.value}</p>}
          </div>
          <button ref={closeRef} type="button" className="icon-button" onClick={onClose} aria-label="근거 Drawer 닫기">
            <X size={18} />
          </button>
        </div>
        {evidence.note && <p className="finance-note">{evidence.note}</p>}
        {sources.length ? (
          <div className="source-list evidence-source-list">
            {sources.map((source, index) => (
              <div key={`${source.id || source.title || "source"}-${index}`}>
                <strong>{source.title || "출처 제목 확인 중"}</strong>
                <span>
                  {[source.publisher, source.sourceType, formatSourceDate(source.publishedAt), source.sectionLabel, source.pageRange ? `${source.pageRange}쪽` : null, source.verificationStatus].filter(Boolean).join(" · ")}
                </span>
                {sourceHasPublicUrl(source) ? (
                  <a href={source.url} target="_blank" rel="noopener noreferrer">
                    원문 보기 <ExternalLink size={13} />
                  </a>
                ) : (
                  <span className="monitor-link-disabled">공개 원문 링크 없음</span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p>연결된 출처 위치를 추가 정리 중입니다.</p>
        )}
      </aside>
    </div>
  );
}
