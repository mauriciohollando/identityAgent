import json
from pathlib import Path

from a2a.types import AgentCard


def test_agent_card_on_disk_is_valid():
    path = Path(__file__).resolve().parent.parent / ".well-known" / "agent-card.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    AgentCard.model_validate(data)
