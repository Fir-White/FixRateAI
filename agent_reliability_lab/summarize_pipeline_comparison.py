"""Summarize paired run artifacts. The reference quantity must be stated as a quantity."""
import argparse
from collections import Counter
import json
from math import ceil
from pathlib import Path
import re
from statistics import median


def reports_quantity(answer, count):
    normalized = answer.casefold().replace('**', '').replace('`', '').split('\nнезавершённые пункты', 1)[0]
    normalized = '\n'.join(line for line in normalized.splitlines() if not line.lstrip().startswith('#'))
    number = rf'(?<![\d-]){count}(?![\d-])'
    noun = r'(?:единиц\w*|задани\w*|наряд\w*|запис\w*|работ\w*|операци\w*|объект\w*)'
    if re.search(r'^\s*\d+\.\s+\S', normalized, re.M):
        return False
    if re.search(rf'\b(?:найдено|всего|итого|насчитано|количеств\w*|{noun})[\s:·—–-]+{number}', normalized):
        return True
    if re.search(rf'{number}\s+{noun}\b', normalized) or re.fullmatch(rf'\s*{number}\.?\s*', normalized):
        return True
    return count == 0 and bool(re.search(r'\b(?:нет(?!\s+доступа)|не\s+найден\w*)\b', normalized))


def summarize(directory):
    result = {}
    for variant in ('A', 'B', 'C'):
        path = directory/f'{variant}.jsonl'
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        if not rows:
            continue
        times = []
        counters = Counter()
        examples = {}
        for row in rows:
            turn_results = []
            for turn in row['turns']:
                errors = [reason for reason in turn['failures'] if reason not in ('quantity_mismatch', 'quantity_not_reported')]
                count = turn['expected']['count']
                if count is not None and not reports_quantity(turn['answer'] or '', count):
                    errors.append('quantity_not_reported')
                turn_results.append(errors)
                times.append(turn['seconds'])
                counters.update(turns=1, turns_passed=int(not errors), unexpected_actions=turn['actions'])
                counters.update(turn_failures=bool(errors))
            counters.update(cases=1, passed=int(not any(turn_results)))
            if row['case'] == 'reported':
                examples[row['case']] = dict(passed=int(sum(not errors for errors in turn_results)),
                                            turns=len(turn_results), failures=turn_results)
        times.sort()
        result[variant] = {**counters, 'turn_p50': round(median(times), 2),
                           'turn_p95': round(times[ceil(len(times)*.95)-1], 2),
                           'total_seconds': round(sum(times), 1), **examples}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.directory), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
