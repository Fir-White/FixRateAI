"""Conservative dispatch guards; recognizing a mutation never authorizes one."""
import re


_MUTATION=re.compile(r'\b(?:созда(?:й|йте|ть)|добав(?:ь|ьте|ить)|измен(?:и|ите|ить)|меня(?:й|йте|ть)|переимен(?:уй|уйте|овать|ование)|удал(?:и|ите|ить)|назнач(?:ь|ьте|ить)|распредел(?:и|ите|ить)|опублик(?:уй|уйте|овать)|утверд(?:и|ите|ить)|сохран(?:и|ите|ить)|запиш(?:и|ите)|записать|обнов(?:и|ите|ить)|прим(?:и|ите)|принять|подтверд(?:и|ите|ить)|замен(?:и|ите|ить)|сним(?:и|ите)|снять|отмен(?:и|ите|ить)|перенес(?:и|ите|ти)|установ(?:и|ите|ить)|очист(?:и|ите|ить)|create|add|edit|change|rename|delete|assign|publish|approve|save|record|update|accept|confirm|replace|remove|cancel|reschedule|install|clear)\b',re.I)


def mutation_requested(question):
    for match in _MUTATION.finditer(question):
        if not re.search(r"\b(?:не|not|don't)\s+$",question[max(0,match.start()-20):match.start()],re.I):return True
    return False


def literal_rename(question):
    """Copy one explicitly quoted target, never unescape a model-created name."""
    if not re.search(r'\b(?:переименуй|переименуйте|переименовать|переименование|rename)\b',question,re.I):return None
    matches=list(re.finditer(r'''\b(?:в|to)\s+(?:«([^«»\n]{1,256})»|"([^"\n]{1,256})"|'([^'\n]{1,256})')''',question,re.I))
    if len(matches)!=1:return None
    value=next(group for group in matches[0].groups() if group is not None).strip()
    return value or None


def explicit_revision(question):
    return bool(re.search(r'\b(?:expected_revision|revision|ревизи\w*|верси\w*)\b',question,re.I))


def read_then_change(question):
    parts=re.split(r'\b(?:затем|после этого|then)\b',question,maxsplit=1,flags=re.I)
    if len(parts)==2 and not mutation_requested(parts[0]) and mutation_requested(parts[1]):return parts[0].strip(' .\n')
    return None
