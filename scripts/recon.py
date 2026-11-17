"""Этап 1: только GET-запросы. Снимает справочники и эталонные кампании в tests/fixtures/.

python scripts/recon.py            # справочники + список кампаний
python scripts/recon.py 12 34      # + потоки кампаний с id 12 и 34
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import keitaro  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
REDACT = {"token"}  # токен Click API кампании, в git ему не место


def scrub(x):
    if isinstance(x, dict):
        return {k: "REDACTED" if k in REDACT else scrub(v) for k, v in x.items()}
    if isinstance(x, list):
        return [scrub(v) for v in x]
    return x


def dump(name: str, path: str, **params):
    data = scrub(keitaro.get(path, **params))
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{name}: {len(data) if isinstance(data, list) else 1}")


OUT.mkdir(parents=True, exist_ok=True)
dump("stream_types", "/stream_types")
dump("stream_schemas", "/stream_schemas")
dump("streams_actions", "/streams_actions")
dump("stream_filters", "/stream_filters")
dump("domains", "/domains")
dump("groups", "/groups", type="campaigns")
dump("traffic_sources", "/traffic_sources")
dump("offers", "/offers")
dump("campaigns", "/campaigns")
for cid in sys.argv[1:]:
    dump(f"streams_{cid}", f"/campaigns/{cid}/streams")
