import { X } from "lucide-react";

export default function ActiveFilterChips({ chips, onReset }) {
  const active = chips.filter((chip) => chip.active);
  if (!active.length) return null;
  return (
    <div className="active-filter-chips" aria-label="활성 필터">
      {active.map((chip) => (
        <button key={chip.key} type="button" onClick={chip.onRemove}>
          <span>{chip.label}</span>
          <X size={14} />
        </button>
      ))}
      <button type="button" className="clear-all" onClick={onReset}>전체 해제</button>
    </div>
  );
}
