"""Только GET-запросы: показывает id для .env и сохраняет справочники в tests/fixtures/ (папка не в git).

python scripts/recon.py            # справочники + список кампаний
python scripts/recon.py 12 34      # + потоки кампаний с id 12 и 34
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import keitaro  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
REDACT = {"token"}  # токен Click API кампании


def scrub(x):
    if isinstance(x, dict):
        return {k: "REDACTED" if k in REDACT else scrub(v) for k, v in x.items()}
    if isinstance(x, list):
        return [scrub(v) for v in x]
    return x


def dump(name: str, path: str, **params):
    data = scrub(keitaro.get(path, **params))
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


OUT.mkdir(parents=True, exist_ok=True)
for name in ("stream_types", "stream_schemas", "streams_actions", "stream_filters", "offers", "campaigns"):
    dump(name, f"/{name}")
for cid in sys.argv[1:]:
    dump(f"streams_{cid}", f"/campaigns/{cid}/streams")

for env, name, path, params in (
    ("DEFAULT_DOMAIN_ID", "domains", "/domains", {}),
    ("DEFAULT_GROUP_ID", "groups", "/groups", {"type": "campaigns"}),
    ("DEFAULT_SOURCE_ID", "traffic_sources", "/traffic_sources", {}),
):
    print(f"\n{env} — выберите id:")
    for item in dump(name, path, **params):
        print(f"  {item['id']:>8}  {item['name']}")
print(f"\nСправочники сохранены в {OUT}")
