from __future__ import annotations

import os


def main() -> int:
    endpoint = os.getenv("D2B_GW_BASE_ENDPOINT", "").strip()
    if not endpoint:
        print("D2B GW API는 아직 연결되지 않았습니다. D2B_GW_BASE_ENDPOINT 확인 후 후속 단계에서 probe를 구현하세요.")
        return 0
    print(f"D2B GW endpoint configured: {endpoint}")
    print("공개 JSON 반영은 비활성 상태입니다. 실제 operation과 인증 방식을 검증한 뒤 연결하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
