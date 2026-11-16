"""Conservative dispatch guards; recognizing a mutation never authorizes one."""
import re


_MUTATION=re.compile(r'\b(?:созда(?:й|йте|ть)|добав(?:ь|ьте|ить)|измен(?:и|ите|ить)|меня(?:й|йте|ть)|переимен(?:уй|уйте|овать|ование)|удал(?:и|ите|ить)|назнач(?:ь|ьте|ить)|распредел(?:и|ите|ить)|опублик(?:уй|уйте|овать)|утверд(?:и|ите|ить)|сохран(?:и|ите|ить)|запиш(?:и|ите)|записать|обнов(?:и|ите|ить)|прим(?:и|ите)|принять|подтверд(?:и|ите|ить)|замен(?:и|ите|ить)|сним(?:и|ите)|снять|отмен(?:и|ите|ить)|перенес(?:и|ите|ти)|установ(?:и|ите|ить)|очист(?:и|ите|ить)|create|add|edit|change|rename|delete|assign|publish|approve|save|record|update|accept|confirm|replace|remove|cancel|reschedule|install|clear)\b',re.I)


def mutation_requested(question):
    # Explicit start is a state change; reading its card is only a prerequisite.
    if re.search(r'^(?:please\s+)?start\b|\b(?:начни|начните)\b',question.strip(),re.I):return True
    for match in _MUTATION.finditer(question):
        prefix=re.split(r'[.:!?;\n]|\b(?:but|then|instead|затем|но)\b',question[:match.start()],flags=re.I)[-1]
        # A single negation scopes a coordinated prohibition: "Do not create,
        # approve or edit". Sentence/contrast boundaries restore positive intent.
        # This guard grants no authority; writes still require exact confirmation.
        negators=list(re.finditer(r"\b(?:не|not|don't|never)\s+",prefix,re.I))
        if not any(neg.end()==len(prefix) or _MUTATION.match(prefix,neg.end()) for neg in negators):return True
    return False


def mutation_command_requested(question):
    """Recognize a direct command without treating an analysed future change as one."""
    if not mutation_requested(question):return False
    if re.search(r'^(?:please\s+)?start\b|\b(?:начни|начните)\b',question.strip(),re.I):return True
    for match in _MUTATION.finditer(question):
        prefix=re.split(r'[.!?;\n]',question[:match.start()])[-1]
        if re.fullmatch(r'\s*(?:(?:please|пожалуйста|затем|then|теперь)\s*)?',prefix,re.I):return True
        if re.search(r'\b(?:then|затем)\s+$',prefix,re.I):return True
    return False


def literal_rename(question):
    """Copy one explicitly quoted target, never unescape a model-created name."""
    if not re.search(r'\b(?:переименуй|переименуйте|переименовать|переименование|rename)\b',question,re.I):return None
    matches=list(re.finditer(r'''\b(?:в|to)\s+(?:«([^«»\n]{1,256})»|"([^"\n]{1,256})"|'([^'\n]{1,256})')''',question,re.I))
    if len(matches)!=1:return None
    value=next(group for group in matches[0].groups() if group is not None).strip()
    return value or None


def primary_document_requested(question):
    """Conservative evidence safeguard, never a process/tool routing decision.

    Explicit verification of a manufacturer's recommendation/document cannot be
    satisfied by database history. This does not certify general NL coverage.
    """
    for clause in re.split(r'[.!?;\n]',question):
        if not re.search(r'производител\w*|manufacturer',clause,re.I):continue
        if not re.search(r'паспорт\w*|документ\w*|рекомендац\w*|manual|document|recommendation',clause,re.I):continue
        for action in re.finditer(r'проверь|провер\w*|подтверд\w*|свер\w*|check|verify|confirm|validate|substantiate',clause,re.I):
            if not re.search(r"\b(?:не|not|don't)\s+$",clause[:action.start()],re.I):return True
    return False


def explicit_revision(question):
    return bool(re.search(r'\b(?:expected_revision|revision|ревизи\w*|верси\w*)\b',question,re.I))


def read_then_change(question):
    parts=re.split(r'\b(?:затем|после этого|then)\b',question,maxsplit=1,flags=re.I)
    if len(parts)==2 and not mutation_requested(parts[0]) and mutation_requested(parts[1]):return parts[0].strip(' .\n')
    return None
