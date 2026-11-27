"""Grade the eight-turn maintenance replay against an independent SQL snapshot."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata


def normal(text):
    text = unicodedata.normalize('NFKC', text).lower().replace('ё', 'е').replace('\\n', ' ')
    return ' '.join(re.sub(r'[\s*`]+', ' ', text).split())


def inspect_turn(index, turn, oracle):
    answer = normal(turn.get('answer', ''))
    tools = [entry['tool'] for entry in turn.get('trace', turn.get('evidence', [])) if not entry['tool'].startswith('__')]
    expected_ops = [row['title'] for row in oracle['operations'] if row['kind'] == 'ТО1']
    other_ops = [row['title'] for row in oracle['operations'] if row['kind'] != 'ТО1']
    coverage = {}
    if index == 0:
        groups = Counter(normal(row['kind']) for row in oracle['operations'])
        for kind, size in groups.items():
            window = rf'\b{kind[:2]}[- ]?{kind[2:]}\b.{{0,55}}\b{size}\b'
            coverage[kind] = bool(re.search(window, answer))
    elif index < 6:
        coverage = dict(included=sum(normal(title) in answer for title in expected_ops), expected=len(expected_ops),
                        unrelated=sum(normal(title) in answer for title in other_ops),
                        fabricated_type=bool(re.search(r'\b(?:то|to)[- ]?3\b', answer)),
                        searched_equipment='equipment_find' in tools)
    elif index == 6:
        count = len(oracle['ongoing'])
        coverage = dict(exact_count=bool(re.search(rf'(?<!\d){count}(?!\d)', answer)),
                        unfinished_scope=bool(re.search(r'\b(?:невыполн\w*|незаверш\w*|не\s+выполн\w*)', answer)),
                        source_named=bool(re.search(r'\b(?:источник|реестр\w*|наряд\w*)', answer)))
    else:
        days = ('2026-11-22', '2026-11-23', '2026-11-24')
        orders = [row for row in oracle['ongoing'] if row['day'] in days]
        covered = Counter(row['day'] for row in orders if re.search(rf'\b{row["code"]}\b', answer))
        counts = Counter(row['day'] for row in orders)
        coverage = dict(expected_by_day=dict(counts), included_by_day={day: covered[day] for day in days},
                        date_labels=all(re.search(rf'\b{day[-2:]}(?:\s+ноября|[./-]11\b)|\b{day}\b', answer) for day in days))
    if 1 <= index < 6:
        passed = coverage['included'] == coverage['expected'] and not any(coverage[key] for key in
            ('unrelated', 'fabricated_type', 'searched_equipment'))
    elif index == 7:
        passed = coverage['date_labels'] and coverage['included_by_day'] == coverage['expected_by_day']
    else:
        passed = all(coverage.values())
    return dict(turn=index+1, passed=passed, checks=coverage, tools=tools, status=turn.get('status'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle', required=True, type=Path)
    parser.add_argument('runs', nargs='+', type=Path)
    args = parser.parse_args()
    oracle = json.loads(args.oracle.read_text(encoding='utf-8'))
    for path in args.runs:
        raw = json.loads(path.read_text(encoding='utf-8'))
        turns = raw if isinstance(raw, list) else raw['turns']
        result = [inspect_turn(index, turn, oracle) for index, turn in enumerate(turns[:8])]
        score = dict(run=path.name, completed=len(result), passed=sum(turn['passed'] for turn in result), turns=result)
        print(json.dumps(score, ensure_ascii=False))


if __name__ == '__main__':
    main()
