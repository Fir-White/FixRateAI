# FixRate AI — handoff аналитика для интеграции в репозиторий

Сборка материалов из переписки: 2026-11-04. Это **передаваемые исходные материалы**, а не подтверждение согласованности с текущим `dev`/`kran_dev`.

## Состав

- `docs/domain/` — оригинальные материалы предметной области и аналитика, включая AN06
- `docs/acceptance/demo_acceptance.md` — AN07: сценарий пользовательской приёмки
- `tests/fixtures/evidence_manifest.json` — 9 кейсов, ожидаемые вердикты
- `tests/fixtures/photos/` — 14 фактически доступных снимков для сценариев
- `docs/acceptance/INTEGRATION_REVIEW.md` — замечания ассистента (не авторский документ Насти)

## Важно

Файлы нужно **сверить с актуальным репозиторием** до интеграции, особенно названия таблиц AN07, права на фото, CASE-06 и тестовые результаты CV. Не трактовать ожидаемые AI-ответы как измеренные результаты, а фотографии — как проверенные факты выполнения работ.

Текущие относительные пути в `evidence_manifest.json` проверены на наличие файлов в пакете. Архив не выполняет SQL-мграции, не запускает ML и не синхронизирует Git.

## Контроль целостности

- `docs/acceptance/INTEGRATION_REVIEW.md` — SHA256 `e8d131021d71fdefb9708e122e1368571db401263c6d3390d9f63c9007373132`
- `docs/acceptance/demo_acceptance.md` — SHA256 `f25468f6b47335a572fa3be180209cdfd6bb00d50a6a7e0c81ad48d8091107f6`
- `docs/domain/data_dictionary.md` — SHA256 `2974e0a8f5b6b0307bc236594cb99f2fab33fb548a3803c816a5a1ee30b39427`
- `docs/domain/examples/maintenance_cases.json` — SHA256 `29f0a92cd8790f28d1e88268b1ee73dfff6c0d2f2981959874debc7ef8c45c38`
- `docs/domain/examples/maintenance_operations.json` — SHA256 `7488369453be0f498a348d8dac93da0c1fe38c91c75b17784bbe1fc986c30c68`
- `docs/domain/examples/maintenance_task.json` — SHA256 `048ad68677f10c0fee3b4a24fd16236572db2b465770987d7b56087bdbadef44`
- `docs/domain/examples/operation_template.json` — SHA256 `a5aedd762291833764001c14173f1e91da8489f2ddabfa2ab53c3dbc8fc3c21e`
- `docs/domain/examples/operation_to_equipment_links.json` — SHA256 `a45420449d557b3be7965a652c5ec7ef1dbe83bdeea8145623f8e7c73f8c635f`
- `docs/domain/examples/regulation.json` — SHA256 `c5e6a734234cd2641404a519c3eef15add7b35e93337d8bab110d1c6d3816dd1`
- `docs/domain/expected_schedule.md` — SHA256 `964a9e86988e5f9861aa6107f27ce35bd32c11562ccbeb260ab96dbe1718450f`
- `docs/domain/inspection_criteria.md` — SHA256 `c704204e6e91dca55c1057ef2abf2ef767f5bcfccc0770d60fec093c613fb565`
- `docs/domain/pilot_regulations.md` — SHA256 `ecea5639a5c05173ba9b9870ff4b7d477fc6d579976f4070757b39b7c0ec1cfa`
- `docs/domain/roles.md` — SHA256 `1384f792f64c2c3b89c386ea43e1654e2b8e79a3256779d83d6c9e2c93a7a696`
- `docs/domain/scope.md` — SHA256 `8c19d82bedb768418c28887ad17b318fea5c0621cb25f55e2dcc5c10a389becc`
- `docs/domain/user_flows.md` — SHA256 `47b1acbb69b563798fca9239ef2f0ab90f1c2a7390563d4b8cc046f4cb4cce72`
- `tests/fixtures/evidence_manifest.json` — SHA256 `164afea48aa4858f40d2c6edf80c4bf5474e76809ca3be0359dd6a1699b2d28d`
- `tests/fixtures/photos/case_01_after.jpg` — SHA256 `7216cfe02a920faaad1927a943d851796add81be9e4b9c9f36093855bee3d777`
- `tests/fixtures/photos/case_01_before.jpg` — SHA256 `2ff768ac8e09084e559230977b250e4cbaa4e6735dba8dcccec2feaf9d09395c`
- `tests/fixtures/photos/case_02_after.jpg` — SHA256 `4d0a014924ef19a37b0204b8e40100c7ed9a921e66de23a348d57e675334f092`
- `tests/fixtures/photos/case_02_before.jpg` — SHA256 `bde6216ddb26d0674f6a79d9bc5ce0ee8940f8f2a67a47604f5774fe04b2a023`
- `tests/fixtures/photos/case_03_after.jpg` — SHA256 `310777ce75c22f0bd444275c11526934b95fcbced39a1bd64671efd2d419508d`
- `tests/fixtures/photos/case_03_before.jpg` — SHA256 `76919089df9ec5514b0b21a742a43a70129af4805b9f6b580a8c5ee896201e61`
- `tests/fixtures/photos/case_04_after.jpg` — SHA256 `0b18feb404cfed7c3c8994654c83c28a29600ca44e4acd9a10a24931a5f69bd4`
- `tests/fixtures/photos/case_04_before.jpg` — SHA256 `b93d0523f26f57d6a341012339da70bcca16796c13900c91d2b1bd59263bdf7a`
- `tests/fixtures/photos/case_05_after.jpg` — SHA256 `81716d8a4fc2d9583871625422532fdad8c25730d7eaa2d3133225a37f5313d3`
- `tests/fixtures/photos/case_05_before.jpg` — SHA256 `4f2f531f0e82ec3cf606af144092a98dbbd08cb145db09caefc5f7ee8e8d8492`
- `tests/fixtures/photos/case_06_after.jpg` — SHA256 `531b0fdd5f453f1da33b1de813af55fffdc19916f49d0e4632447e819a60796e`
- `tests/fixtures/photos/case_06_before.jpg` — SHA256 `bdb43c028723e6998f8d413e5567f30cd1c3b6ba4b0b31311fce28e76715bbba`
- `tests/fixtures/photos/neg_01_after_blurry_glare.jpg` — SHA256 `e4bb580d5d89e824f14588824c6afd150779bfe20bf4f02fb98aef326ab94ea4`
- `tests/fixtures/photos/neg_02_after_blurry_glare.jpg` — SHA256 `dea9105b192a57d43070d796651ed754111ad702dfff55c4914d928f5b849dc9`
