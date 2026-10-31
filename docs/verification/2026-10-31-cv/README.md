# Дополнительный профиль настоящего CLIP

[Протокол inference](clip_inference_proof.json), [команды всех проверок](results.json), [pytest](pytest.log), [browser E2E](browser_e2e.log).

Запущено с `FIXRATE_REQUIRE_CLIP=1` в `.venv/cv` и отдельным HF_HOME. 167 Python tests, 22 UI tests и 1 browser E2E прошли. HTTP сценарий требует непустой modelRef настоящего закреплённого CLIP; unavailable не допускается в этой проверке. Данные — контролируемые тестовые изображения, оценка точности на customer фото не заявляется.

[Установка профиля](../../SYSTEM_OVERVIEW.md#отдельное-окружение-с-настоящим-clip). Runtime работает offline, загрузка была явной отдельной командой prepare_clip.py --download. Веса находятся в игнорируемом .venv/cv-cache и не включены в Git.
