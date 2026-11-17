"""Typed read-only observations; parser/renderer tests are not live OCR evidence."""
import pytest
from pydantic import ValidationError
from app.assistant.photo_reading import VisiblePhotoReading,requested,render


@pytest.mark.parametrize('code,value,unit',[
    ('RT-FOTO-7','1.2','bar'),
    ('МН-01','12,5','кПа'),
    (None,None,None),
    ('VAC-1','-0.1','Pa'),
    ('V-1','0','V'),
])
def test_observation_preserves_visible_values_and_never_claims_recording(code,value,unit):
    observation=VisiblePhotoReading(asset_label=code,value=value,unit=unit)
    answer=render(observation)
    if code:assert code in answer
    if value is not None:assert '**'+value+'**' in answer
    else:assert 'не заменено нулём' in answer and '**0**' not in answer
    assert 'Данные в системе не сохранялись и не изменялись' in answer
    assert 'не подтверждение' in answer


@pytest.mark.parametrize('value',['NaN','8+A6:S33','1.2 bar','unknown','1e9'])
def test_observation_cannot_turn_non_numeric_text_into_a_reading(value):
    with pytest.raises(ValidationError):VisiblePhotoReading(asset_label=None,value=value,unit=None)


@pytest.mark.parametrize('question',[
    'Перепиши код и показание давления с фото. Ничего не изменяй.',
    'Прочитай маркировку и значение на изображении.',
    'Считай код и показание с фото.',
    'Распознай маркировку и давление на фото.',
    'Перепиши только код и показание давления с фото. Не выполняй никаких действий.',
])
def test_unambiguous_read_only_photo_request_is_recognized(question):assert requested(question)


@pytest.mark.parametrize('question',[
    'Перепиши код и показание с фото и сохрани результат.',
    'Прочитай код и показание на фото и запиши их в систему.',
    'Обнови показание по фото и прочитай код.',
    'Подтверди приёмку: перепиши код и показание фото.',
    'Сколько сотрудников доступно?',
    'Перепиши код и показание с фото и удали задание.',
    'Прочитай код и показание с фото и назначь техника.',
    'Прочитай код и показание с фото и переименуй оборудование.',
    'Прочитай код и показание с фото и опубликуй план.',
    'Прочитай код и показание с фото и замени деталь.',
    'Прочитай код и показание с фото, then save the reading.',
    'Перепиши код и показание с фото и рассчитай загрузку.',
    'Перепиши код и показание с фото и сравни с прошлым месяцем.',
    'Перепиши код и показание с фото. Почему давление выросло?',
    'Перепиши код и показание с фото и спланируй ТО.',
    'Перепиши код и показание с фото. Кто отвечает за оборудование?',
])
def test_reader_does_not_swallow_a_requested_domain_change(question):assert not requested(question)
