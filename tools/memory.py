"""Long-term memory tools: remember, recall, forget, list_facts."""

from __future__ import annotations

from memory.repo import MemoryRepo
from tools.registry import Tool, ToolRegistry


def register_memory_tools(registry: ToolRegistry, memory: MemoryRepo) -> None:
    def remember(key: str, value: str, category: str = "general") -> str:
        k = str(key).strip()
        v = str(value).strip()
        if not k or not v:
            return "Key aur value dono zaroori hain."
        memory.remember(k, v, category=category)
        return f"Yaad rakh liya: '{k}' = '{v}' [{category}]"

    def recall(query: str, limit: int = 5) -> str:
        q = str(query).strip()
        if not q:
            return "Search query do."
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 5
        matches = memory.recall(q, limit=limit)
        if not matches:
            return f"'{q}' ke baare me koi saved fact nahi mila."
        lines = [f"- {m['key']} ({m.get('category', 'general')}): {m['value']}" for m in matches]
        return "Found facts:\n" + "\n".join(lines)

    def forget(key: str) -> str:
        k = str(key).strip()
        if not k:
            return "Kise bhoolna hai? Key do."
        ok = memory.forget(k)
        if ok:
            return f"Fact '{k}' bhool gaya (deleted)."
        return f"'{k}' naam ka koi active fact nahi mila."

    def list_facts(category: str = "") -> str:
        facts = memory.list_facts(category=category)
        if not facts:
            return "Abhi koi facts saved nahi hain."
        lines = [f"- [{f.get('category','general')}] {f['key']}: {f['value']}" for f in facts]
        return f"Saved facts ({len(facts)}):\n" + "\n".join(lines)

    def search_memory(query: str, limit: int = 5) -> str:
        q = str(query).strip()
        if not q:
            return "Search query required."
        try:
            lim = int(limit)
        except (ValueError, TypeError):
            lim = 5
        res = memory.search_memory(q, limit=lim)
        facts = res.get("facts") or []
        convos = res.get("conversations") or []

        if not facts and not convos:
            return f"'{q}' ke baare me koi saved fact ya purani conversation nahi mili."

        out = [f"### 🧠 Memory Search Results for '{q}':"]
        if facts:
            out.append("\n**Saved Facts & Preferences:**")
            for f in facts:
                out.append(f"- [{f.get('category', 'general')}] {f['key']}: {f['value']}")
        if convos:
            out.append("\n**Past Conversations:**")
            for c in convos:
                role_tag = "User" if c.get("role") == "user" else "LUMI"
                ts = c.get("ts", "")
                content = c.get("content", "").replace("\n", " ")[:140]
                out.append(f"- [{ts}] {role_tag}: {content}")
        return "\n".join(out)


    registry.register(Tool(
        "remember",
        "User ke baare me koi important fact, preference, rule, ya detail permanently save karta hai.",
        {"type": "object", "properties": {
            "key": {"type": "string", "description": "Short identifier, e.g. 'user_name', 'favorite_editor'"},
            "value": {"type": "string", "description": "Fact detail to remember"},
            "category": {"type": "string", "description": "identity | preference | work | budget | general"}},
         "required": ["key", "value"]},
        remember,
        risk="auto"
    ))

    registry.register(Tool(
        "recall",
        "Permanently saved facts me keyword search karta hai.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search term"},
            "limit": {"type": "integer", "description": "Max results"}},
         "required": ["query"]},
        recall,
        risk="auto"
    ))

    registry.register(Tool(
        "forget",
        "Saved fact ko delete/remove karta hai.",
        {"type": "object", "properties": {
            "key": {"type": "string", "description": "Key of fact to forget"}},
         "required": ["key"]},
        forget,
        risk="ask"
    ))

    registry.register(Tool(
        "list_facts",
        "Saare currently active saved facts ki list dikhata hai.",
        {"type": "object", "properties": {
            "category": {"type": "string", "description": "Optional category filter"}},
         "required": []},
        list_facts,
        risk="auto"
    ))

    registry.register(Tool(
        "search_memory",
        "Lifelong memory search: searches both permanent facts AND past conversations / dialog history.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search keyword or topic"},
            "limit": {"type": "integer", "description": "Max results to return (default 5)"}},
         "required": ["query"]},
        search_memory,
        risk="auto"
    ))

