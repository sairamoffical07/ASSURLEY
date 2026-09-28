import re

with open('app/ocr.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if line.strip() == 'for doc_type, data in types.items():':
        skip = True
        new_lines.extend([
            '    for doc_type, data in types.items():\n',
            '        score = 0\n',
            '        matches = []\n',
            '        max_possible_score = sum(data["keywords"].values())\n',
            '        \n',
            '        for kw, weight in data["keywords"].items():\n',
            '            if kw in norm_text:\n',
            '                score += weight\n',
            '                matches.append(kw)\n',
            '        \n',
            '        confidence = min(1.0, score / max_possible_score) if max_possible_score > 0 else 0.0\n',
            '        \n',
            '        if score > best_score:\n',
            '            best_score = score\n',
            '            best_conf = confidence\n',
            '            best_type = doc_type\n',
            '            best_matches = matches\n',
            '\n',
            '    if best_conf >= 0.15:\n',
            '        return {\n',
            '            "type": best_type,\n',
            '            "heuristicScore": round(best_conf, 4),\n',
            '            "method": "KEYWORD_HEURISTIC",\n',
            '            "matchedPatterns": best_matches\n',
            '        }\n',
            '        \n',
            '    return {\n',
            '        "type": "UNKNOWN",\n',
            '        "heuristicScore": 0.0,\n',
            '        "method": "KEYWORD_HEURISTIC",\n',
            '        "matchedPatterns": []\n',
            '    }\n',
            '\n',
            'def extract_rc_fields(raw_text: str) -> dict:\n',
            '    from typing import Any, Optional\n',
            '    def field(value: Optional[str]) -> dict:\n',
            '        return {"value": value, "source": "regex", "page": None}\n',
            '\n',
            '    norm_text = normalize_text_for_extraction(raw_text)\n',
            '\n',
            '    def _find(patterns: list[str]) -> Optional[str]:\n',
            '        for pat in patterns:\n',
            '            m = re.search(pat, norm_text, re.IGNORECASE)\n',
            '            if m:\n',
            '                val = m.group(1).strip()\n',
            '                if val:\n',
            '                    return val\n',
            '        return None\n',
            '\n'
        ])
    elif skip and line.strip().startswith('owner_name = _find'):
        skip = False
        new_lines.append(line)
    elif not skip:
        new_lines.append(line)

with open('app/ocr.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Fixed classify_document and extract_rc_fields')
