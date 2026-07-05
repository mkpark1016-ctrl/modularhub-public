import { Star } from "lucide-react";

export default function FavoriteButton({ active, onClick, label = "관심목록" }) {
  return (
    <button
      type="button"
      className={`favorite-button ${active ? "active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
      aria-label={active ? `${label}에서 제거` : `${label}에 추가`}
      title={active ? `${label}에서 제거` : `${label}에 추가`}
    >
      <Star size={16} fill={active ? "currentColor" : "none"} />
      <span>{active ? "관심" : "관심"}</span>
    </button>
  );
}
