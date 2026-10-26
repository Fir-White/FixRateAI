"""SQL-only scenario definitions for the FixRate DB matrix (TC-001..TC-095)."""


def uid(n: int) -> str:
    return f"a{n:07d}-0000-4000-8000-000000000001"


V = {
    "U1": uid(1),
    "U2": uid(2),
    "U3": uid(3),
    "B1": uid(4),
    "R1": uid(5),
    "R2": uid(6),
    "R3": uid(7),
    "P1": uid(8),
    "P2": uid(9),
    "P3": uid(10),
    "P4": uid(11),
    "D1": uid(12),
    "D2": uid(13),
    "D3": uid(14),
    "S1": uid(15),
    "S2": uid(16),
    "RATE1": uid(17),
    "RATE2": uid(18),
    "RUN1": uid(19),
    "RUN2": uid(20),
    "AR1": uid(21),
    "E1": uid(22),
    "E2": uid(23),
    "E4": uid(24),
    "ITEM1": uid(25),
    "ITEM2": uid(26),
    "ITEM3": uid(27),
    "ITEM4": uid(28),
    "M1": uid(29),
    "M2": uid(30),
    "M3": uid(31),
    "CLAR1": uid(32),
    "CLAR2": uid(33),
    "EV1": uid(34),
    "CHUNK1": uid(35),
    "CHUNK2": uid(36),
    "S3": uid(37),
    "RATE3": uid(38),
    "RUN3": uid(39),
    "AR3": uid(40),
    "AR2": uid(41),
    "HASH": "a" * 64,
}

COMMON = """
INSERT INTO users(user_id, full_name, email, role) VALUES
    ('@U1@', 'TC Operator', 'tc.user1@example.test', 'operator'),
    ('@U2@', 'TC Estimator', 'tc.user2@example.test', 'estimator'),
    ('@U3@', 'TC Admin', 'tc.user3@example.test', 'admin');
INSERT INTO buildings(building_id, address) VALUES ('@B1@', 'TC building');
INSERT INTO repair_requests(request_id, building_id, created_by, title) VALUES
    ('@R1@', '@B1@', '@U1@', 'TC request 1'),
    ('@R2@', '@B1@', '@U1@', 'TC request 2'),
    ('@R3@', '@B1@', '@U2@', 'TC request 3');
INSERT INTO request_photos(photo_id, request_id, storage_key, original_filename,
    mime_type, file_size, checksum_sha256) VALUES
    ('@P1@', '@R1@', 'tc-key-1', '1.jpg', 'image/jpeg', 10, v_hash),
    ('@P2@', '@R2@', 'tc-key-2', '2.jpg', 'image/jpeg', 10, v_hash),
    ('@P3@', '@R1@', 'tc-key-3', '3.jpg', 'image/jpeg', 10, v_hash),
    ('@P4@', '@R1@', 'tc-key-4', '4.jpg', 'image/jpeg', 10, v_hash);
INSERT INTO defects(defect_id, request_id, description) VALUES
    ('@D1@', '@R1@', 'TC defect 1'),
    ('@D2@', '@R2@', 'TC defect 2'),
    ('@D3@', '@R1@', 'TC defect 3');
INSERT INTO norm_sources(source_id, source_type, title, edition, document_reference, is_verified) VALUES
    ('@S1@', 'DEMO', 'TC source 1', 'tc-v1', 'TC document 1', false),
    ('@S2@', 'DEMO', 'TC source 2', 'tc-v1', 'TC document 2', false);
INSERT INTO rates(rate_id, source_id, rate_code, work_name, unit_code,
    rate_unit_multiplier, base_price, currency, price_basis, cost_scope) VALUES
    ('@RATE1@', '@S1@', 'TC-RATE-1', 'TC work 1', 'pcs', 1, 100, 'RUB', 'demo', 'work_only'),
    ('@RATE2@', '@S2@', 'TC-RATE-2', 'TC work 2', 'pcs', 1, 200, 'RUB', 'demo', 'work_only');
INSERT INTO ai_runs(run_id, request_id, pipeline_version) VALUES
    ('@RUN1@', '@R1@', 'tc-v1'),
    ('@RUN2@', '@R2@', 'tc-v1');
INSERT INTO ai_results(ai_result_id, run_id, request_id, module_type) VALUES
    ('@AR1@', '@RUN1@', '@R1@', 'cv'),
    ('@AR2@', '@RUN2@', '@R2@', 'cv');
INSERT INTO estimates(estimate_id, request_id, version) VALUES ('@E1@', '@R1@', 1);
"""

TESTS = []


def add(tc: str, body: str) -> None:
    TESTS.append((tc, body))


add("TC-001", """
SELECT count(*) INTO v_count FROM repair_requests WHERE created_by = '@U1@';
IF v_count <> 2 THEN
    RAISE EXCEPTION 'TC-001 expected 2 requests for one user, got %', v_count;
END IF;
""")

add("TC-002", """
BEGIN
    DELETE FROM users WHERE user_id = '@U1@';
    RAISE EXCEPTION 'TC-002 expected FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-004", """
BEGIN
    INSERT INTO users(full_name, email, role)
    VALUES ('Dup', 'TC.USER1@EXAMPLE.TEST', 'operator');
    RAISE EXCEPTION 'TC-004 expected unique rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-005", """
BEGIN
    INSERT INTO users(full_name, email, role)
    VALUES ('Bad role', 'bad.role.tc@example.test', 'guest');
    RAISE EXCEPTION 'TC-005 expected check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-007", """
BEGIN
    DELETE FROM buildings WHERE building_id = '@B1@';
    RAISE EXCEPTION 'TC-007 expected FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-009", """
INSERT INTO buildings(address, additional_properties)
VALUES ('TC roof building', '{"roof":"metal"}'::jsonb);
SELECT additional_properties->>'roof' INTO v_text
FROM buildings WHERE address = 'TC roof building';
IF v_text IS DISTINCT FROM 'metal' THEN
    RAISE EXCEPTION 'TC-009 JSONB value not stored: %', v_text;
END IF;
""")

add("TC-010", """
BEGIN
    INSERT INTO buildings(address, additional_properties)
    VALUES ('TC bad json', '[]'::jsonb);
    RAISE EXCEPTION 'TC-010 expected check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-011", """
BEGIN
    INSERT INTO buildings(address, total_area) VALUES ('TC zero area', 0);
    RAISE EXCEPTION 'TC-011 expected check rejection for zero area';
EXCEPTION WHEN check_violation THEN NULL;
END;
BEGIN
    INSERT INTO buildings(address, total_area) VALUES ('TC negative area', -1);
    RAISE EXCEPTION 'TC-011 expected check rejection for negative area';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-012", """
SELECT count(*) INTO v_count FROM request_photos WHERE request_id = '@R1@';
IF v_count <> 3 THEN
    RAISE EXCEPTION 'TC-012 expected 3 photos, got %', v_count;
END IF;
SELECT count(DISTINCT storage_key) INTO v_count
FROM request_photos WHERE request_id = '@R1@';
IF v_count <> 3 THEN
    RAISE EXCEPTION 'TC-012 expected 3 distinct storage keys, got %', v_count;
END IF;
""")

add("TC-013", """
BEGIN
    INSERT INTO request_photos(request_id, storage_key, original_filename,
        mime_type, file_size, checksum_sha256)
    VALUES ('ffffffff-ffff-4fff-8fff-ffffffffffff', 'tc-missing-request',
        'x.jpg', 'image/jpeg', 10, v_hash);
    RAISE EXCEPTION 'TC-013 expected FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-014", """
BEGIN
    INSERT INTO request_photos(request_id, storage_key, original_filename,
        mime_type, file_size, checksum_sha256)
    VALUES ('@R2@', 'tc-key-1', 'dup.jpg', 'image/jpeg', 10, v_hash);
    RAISE EXCEPTION 'TC-014 expected unique rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-016", """
BEGIN
    UPDATE repair_requests SET status = 'archived' WHERE request_id = '@R1@';
    RAISE EXCEPTION 'TC-016 expected check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-021", """
INSERT INTO defect_photos(defect_id, photo_id, request_id) VALUES
    ('@D1@', '@P1@', '@R1@'),
    ('@D1@', '@P3@', '@R1@'),
    ('@D1@', '@P4@', '@R1@');
SELECT count(*) INTO v_count FROM defect_photos WHERE defect_id = '@D1@';
IF v_count <> 3 THEN
    RAISE EXCEPTION 'TC-021 expected 3 photos for one defect, got %', v_count;
END IF;
""")

add("TC-022", """
INSERT INTO defect_photos(defect_id, photo_id, request_id) VALUES
    ('@D1@', '@P1@', '@R1@'),
    ('@D3@', '@P1@', '@R1@');
SELECT count(*) INTO v_count FROM defect_photos WHERE photo_id = '@P1@';
IF v_count <> 2 THEN
    RAISE EXCEPTION 'TC-022 expected 2 defects for one photo, got %', v_count;
END IF;
""")

add("TC-023", """
INSERT INTO defect_photos(defect_id, photo_id, request_id)
VALUES ('@D1@', '@P1@', '@R1@');
BEGIN
    INSERT INTO defect_photos(defect_id, photo_id, request_id)
    VALUES ('@D1@', '@P1@', '@R1@');
    RAISE EXCEPTION 'TC-023 expected duplicate rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-024", """
INSERT INTO defect_photos(defect_id, photo_id, request_id, is_primary)
VALUES ('@D1@', '@P1@', '@R1@', true);
BEGIN
    INSERT INTO defect_photos(defect_id, photo_id, request_id, is_primary)
    VALUES ('@D1@', '@P3@', '@R1@', true);
    RAISE EXCEPTION 'TC-024 expected partial unique rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-025", """
BEGIN
    INSERT INTO defect_photos(defect_id, photo_id, request_id)
    VALUES ('@D1@', '@P2@', '@R1@');
    RAISE EXCEPTION 'TC-025 expected photo/request FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-026", """
INSERT INTO defect_measurements(measurement_id, defect_id, request_id,
    parameter_code, value, unit_code, source_type) VALUES
    ('@M1@', '@D1@', '@R1@', 'length', 2, 'm', 'manual'),
    ('@M2@', '@D1@', '@R1@', 'width', 1, 'm', 'manual'),
    ('@M3@', '@D1@', '@R1@', 'area', 2, 'm2', 'manual');
SELECT count(*) INTO v_count
FROM defect_measurements WHERE defect_id = '@D1@';
IF v_count <> 3 THEN
    RAISE EXCEPTION 'TC-026 expected 3 measurements, got %', v_count;
END IF;
""")

add("TC-027", """
BEGIN
    INSERT INTO defect_measurements(defect_id, request_id, parameter_code,
        value, unit_code, source_type)
    VALUES ('@D1@', '@R1@', 'bad', -2, 'm', 'manual');
    RAISE EXCEPTION 'TC-027 expected negative-value check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-031", """
INSERT INTO defect_measurements(measurement_id, defect_id, request_id,
    parameter_code, value, unit_code, source_type, is_current)
VALUES ('@M1@', '@D1@', '@R1@', 'area', 1, 'm2', 'manual', true);
BEGIN
    INSERT INTO defect_measurements(measurement_id, defect_id, request_id,
        parameter_code, value, unit_code, source_type, is_current)
    VALUES ('@M2@', '@D1@', '@R1@', 'area', 2, 'm2', 'manual', true);
    RAISE EXCEPTION 'TC-031 expected current-version unique rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-032", """
BEGIN
    INSERT INTO defect_measurements(defect_id, request_id, parameter_code,
        value, unit_code, source_type, source_ai_result_id)
    VALUES ('@D1@', '@R1@', 'area', 1, 'm2', 'photo', '@AR2@');
    RAISE EXCEPTION 'TC-032 expected cross-request AI result FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-033", """
BEGIN
    INSERT INTO defect_measurements(defect_id, request_id, parameter_code,
        value, unit_code, source_type)
    VALUES ('@D1@', '@R2@', 'area', 1, 'm2', 'manual');
    RAISE EXCEPTION 'TC-033 expected cross-request defect FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-034", """
INSERT INTO defect_measurements(measurement_id, defect_id, request_id,
    parameter_code, value, unit_code, source_type)
VALUES ('@M1@', '@D1@', '@R1@', 'area', 1, 'm2', 'manual');
BEGIN
    UPDATE defect_measurements
    SET supersedes_measurement_id = '@M1@'
    WHERE measurement_id = '@M1@';
    RAISE EXCEPTION 'TC-034 expected self-reference check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-038", """
INSERT INTO ai_runs(run_id, request_id, pipeline_version)
VALUES ('@RUN3@', '@R1@', 'tc-v2');
INSERT INTO ai_results(ai_result_id, run_id, request_id, module_type,
    model_name, model_version)
VALUES ('@AR3@', '@RUN3@', '@R1@', 'cv', 'model-v2', '2.0');
SELECT count(*) INTO v_count
FROM ai_results
WHERE ai_result_id = '@AR3@'
  AND model_name = 'model-v2'
  AND model_version = '2.0';
IF v_count <> 1 THEN
    RAISE EXCEPTION 'TC-038 new model version was not saved';
END IF;
SELECT count(*) INTO v_count FROM ai_results WHERE ai_result_id = '@AR1@';
IF v_count <> 1 THEN
    RAISE EXCEPTION 'TC-038 previous AI result was deleted';
END IF;
""")

add("TC-040", """
BEGIN
    INSERT INTO ai_results(run_id, request_id, module_type)
    VALUES ('@RUN1@', '@R2@', 'cv');
    RAISE EXCEPTION 'TC-040 expected cross-request AI result FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-041", """
BEGIN
    INSERT INTO ai_results(run_id, request_id, module_type)
    VALUES ('@RUN1@', '@R1@', 'ocr');
    RAISE EXCEPTION 'TC-041 expected module_type check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-046", """
INSERT INTO norm_sources(source_id, source_type, title, edition, source_url, is_verified)
VALUES ('@S3@', 'FER', 'TC FER source', 'tc-v1', 'https://example.test/fer', true);
INSERT INTO rates(rate_id, source_id, rate_code, work_name, unit_code,
    base_price, currency, price_basis, cost_scope)
VALUES ('@RATE3@', '@S3@', 'TC-FER-1', 'TC FER work', 'pcs',
    300, 'RUB', 'normative_base', 'work_only');
SELECT source_type INTO v_text FROM norm_sources WHERE source_id = '@S3@';
IF v_text <> 'FER' THEN
    RAISE EXCEPTION 'TC-046 expected FER source, got %', v_text;
END IF;
SELECT count(*) INTO v_count
FROM rates WHERE rate_id = '@RATE3@' AND source_id = '@S3@';
IF v_count <> 1 THEN
    RAISE EXCEPTION 'TC-046 rate is not linked to its source';
END IF;
BEGIN
    INSERT INTO norm_sources(source_type, title)
    VALUES ('OTHER', 'TC invalid source type');
    RAISE EXCEPTION 'TC-046 expected source_type check rejection';
EXCEPTION WHEN check_violation OR raise_exception THEN NULL;
END;
""")

add("TC-047", """
BEGIN
    INSERT INTO norm_sources(source_id, source_type, title, is_verified)
    VALUES (gen_random_uuid(), 'FER', 'Bad verified source', true);
    RAISE EXCEPTION 'TC-047 expected verified-source check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-049", """
BEGIN
    INSERT INTO rates(source_id, rate_code, work_name, unit_code,
        base_price, currency, price_basis, cost_scope)
    VALUES ('@S1@', 'TC-RATE-1', 'Duplicate rate', 'pcs',
        100, 'RUB', 'demo', 'work_only');
    RAISE EXCEPTION 'TC-049 expected duplicate rate_code rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-056", """
BEGIN
    INSERT INTO normative_chunks(chunk_id, source_id, rate_id, chunk_index,
        content, content_hash)
    VALUES ('@CHUNK1@', '@S1@', '@RATE2@', 1, 'TC cross-source chunk', '@HASH@');
    RAISE EXCEPTION 'TC-056 expected rate/source FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-057", """
BEGIN
    INSERT INTO normative_chunks(source_id, chunk_index, content, content_hash)
    VALUES ('@S1@', 2, '   ', '@HASH@');
    RAISE EXCEPTION 'TC-057 expected empty-content check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-058", """
INSERT INTO normative_chunks(chunk_id, source_id, chunk_index, content, content_hash)
VALUES ('@CHUNK1@', '@S1@', 3, 'TC chunk 1', '@HASH@');
BEGIN
    INSERT INTO normative_chunks(chunk_id, source_id, chunk_index, content, content_hash)
    VALUES ('@CHUNK2@', '@S1@', 3, 'TC chunk 2', '@HASH@');
    RAISE EXCEPTION 'TC-058 expected duplicate chunk_index rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-059", """
BEGIN
    INSERT INTO normative_chunks(source_id, chunk_index, content, embedding, content_hash)
    VALUES ('@S1@', 4, 'TC embedding without model', '[1,2,3]'::vector, '@HASH@');
    RAISE EXCEPTION 'TC-059 expected embedding/model check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-060", """
BEGIN
    INSERT INTO normative_chunks(source_id, chunk_index, content, embedding_model, content_hash)
    VALUES ('@S1@', 5, 'TC model without embedding', 'test-model', '@HASH@');
    RAISE EXCEPTION 'TC-060 expected embedding/model check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-065", """
INSERT INTO estimates(estimate_id, request_id, version)
VALUES ('@E2@', '@R1@', 2);
BEGIN
    INSERT INTO estimates(estimate_id, request_id, version)
    VALUES ('@E4@', '@R1@', 2);
    RAISE EXCEPTION 'TC-065 expected duplicate estimate version rejection';
EXCEPTION WHEN unique_violation THEN NULL;
END;
""")

add("TC-066", """
BEGIN
    INSERT INTO estimates(estimate_id, request_id, version, based_on_run_id)
    VALUES ('@E4@', '@R1@', 2, '@RUN2@');
    RAISE EXCEPTION 'TC-066 expected cross-request based_on_run FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-067", """
INSERT INTO estimates(estimate_id, request_id, version)
VALUES ('@E2@', '@R2@', 1);
BEGIN
    INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name)
    VALUES ('@ITEM1@', '@E2@', '@R1@', 'TC cross-estimate item');
    RAISE EXCEPTION 'TC-067 expected estimate/request FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-068", """
BEGIN
    INSERT INTO estimate_items(item_id, estimate_id, request_id, defect_id, work_name)
    VALUES ('@ITEM1@', '@E1@', '@R1@', '@D2@', 'TC cross-defect item');
    RAISE EXCEPTION 'TC-068 expected defect/request FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-069", """
INSERT INTO estimate_items(item_id, estimate_id, request_id, defect_id, work_name) VALUES
    ('@ITEM1@', '@E1@', '@R1@', '@D1@', 'TC work 1'),
    ('@ITEM2@', '@E1@', '@R1@', '@D1@', 'TC work 2'),
    ('@ITEM3@', '@E1@', '@R1@', '@D1@', 'TC work 3'),
    ('@ITEM4@', '@E1@', '@R1@', '@D1@', 'TC work 4');
SELECT count(*) INTO v_count FROM estimate_items WHERE estimate_id = '@E1@';
IF v_count <> 4 THEN
    RAISE EXCEPTION 'TC-069 expected 4 items for one defect, got %', v_count;
END IF;
""")

add("TC-071", """
BEGIN
    INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name,
        quantity, unit_code, unit_price, base_cost, total_cost,
        validation_status, source_snapshot)
    VALUES ('@ITEM1@', '@E1@', '@R1@', 'TC valid without price/source',
        1, 'pcs', NULL, 100, 100, 'valid', NULL);
    RAISE EXCEPTION 'TC-071 expected valid-item price/source check rejection';
EXCEPTION WHEN check_violation OR raise_exception THEN NULL;
END;
""")

add("TC-072", """
BEGIN
    INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name,
        quantity, unit_code, unit_price, base_cost, total_cost)
    VALUES ('@ITEM1@', '@E1@', '@R1@', 'TC negative quantity',
        -1, 'pcs', 100, 100, 100);
    RAISE EXCEPTION 'TC-072 expected negative-quantity check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
BEGIN
    INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name,
        quantity, unit_code, unit_price, base_cost, total_cost)
    VALUES ('@ITEM2@', '@E1@', '@R1@', 'TC negative price',
        1, 'pcs', -1, 100, 100);
    RAISE EXCEPTION 'TC-072 expected negative-price check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-073", """
BEGIN
    INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name,
        coefficient)
    VALUES ('@ITEM1@', '@E1@', '@R1@', 'TC zero coefficient', 0);
    RAISE EXCEPTION 'TC-073 expected coefficient check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-076", """
INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name)
VALUES ('@ITEM1@', '@E1@', '@R1@', 'TC material item');
BEGIN
    INSERT INTO estimate_materials(item_id, material_name, quantity,
        unit_code, cost_treatment)
    VALUES ('@ITEM1@', 'TC additional material', 1, 'pcs', 'additional');
    RAISE EXCEPTION 'TC-076 expected additional-material price check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-080", """
INSERT INTO estimate_items(item_id, estimate_id, request_id, work_name,
    quantity, unit_code, unit_price, base_cost, total_cost,
    validation_status, source_snapshot)
VALUES ('@ITEM1@', '@E1@', '@R1@', 'TC approval item',
    1, 'pcs', 100, 100, 100, 'valid',
    '{"origin":"manual","source_description":"TC manual quote","entered_by":"@U2@","basis":"TC approval","unit_code":"pcs","unit_price":100,"currency":"RUB"}'::jsonb);
UPDATE estimates SET total_cost = 100 WHERE estimate_id = '@E1@';
BEGIN
    UPDATE estimates SET status = 'approved' WHERE estimate_id = '@E1@';
    RAISE EXCEPTION 'TC-080 expected approved-without-reviewer check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-087", """
INSERT INTO request_clarifications(clarification_id, request_id, run_id,
    field_name, question, status)
VALUES ('@CLAR1@', '@R1@', '@RUN1@', 'area', 'TC question?', 'open');
SELECT count(*) INTO v_count
FROM request_clarifications
WHERE clarification_id = '@CLAR1@'
  AND request_id = '@R1@'
  AND run_id = '@RUN1@';
IF v_count <> 1 THEN
    RAISE EXCEPTION 'TC-087 clarification not linked to request/run';
END IF;
""")

add("TC-088", """
BEGIN
    INSERT INTO request_clarifications(clarification_id, request_id,
        field_name, question, status)
    VALUES ('@CLAR1@', '@R1@', 'area', 'TC answered?', 'answered');
    RAISE EXCEPTION 'TC-088 expected answered-without-answer check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
INSERT INTO request_clarifications(clarification_id, request_id,
    field_name, question, answer, status, answered_at)
VALUES ('@CLAR2@', '@R1@', 'area', 'TC answered?', '2 m2', 'answered', now());
SELECT count(*) INTO v_count
FROM request_clarifications
WHERE clarification_id = '@CLAR2@'
  AND answer = '2 m2'
  AND answered_at IS NOT NULL;
IF v_count <> 1 THEN
    RAISE EXCEPTION 'TC-088 answered clarification not stored';
END IF;
""")

add("TC-090", """
BEGIN
    INSERT INTO request_clarifications(request_id, run_id, field_name, question)
    VALUES ('@R1@', '@RUN2@', 'area', 'TC cross-run clarification');
    RAISE EXCEPTION 'TC-090 expected clarification run/request FK rejection';
EXCEPTION WHEN foreign_key_violation THEN NULL;
END;
""")

add("TC-091", """
INSERT INTO request_clarifications(clarification_id, request_id,
    field_name, question)
VALUES ('@CLAR1@', '@R1@', 'area', 'TC self clarification');
BEGIN
    UPDATE request_clarifications
    SET supersedes_clarification_id = '@CLAR1@'
    WHERE clarification_id = '@CLAR1@';
    RAISE EXCEPTION 'TC-091 expected self-reference check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

add("TC-094", """
INSERT INTO audit_events(event_id, actor_type, user_id, request_id,
    entity_type, entity_id, action)
VALUES ('@EV1@', 'ai', NULL, '@R1@', 'estimates', '@E1@', 'tc_ai_action');
SELECT count(*) INTO v_count
FROM audit_events
WHERE event_id = '@EV1@'
  AND actor_type = 'ai'
  AND user_id IS NULL;
IF v_count <> 1 THEN
    RAISE EXCEPTION 'TC-094 AI audit event was not stored';
END IF;
""")

add("TC-095", """
BEGIN
    INSERT INTO audit_events(actor_type, user_id, request_id,
        entity_type, entity_id, action)
    VALUES ('user', NULL, '@R1@', 'estimates', '@E1@', 'tc_user_action');
    RAISE EXCEPTION 'TC-095 expected user-actor user_id check rejection';
EXCEPTION WHEN check_violation THEN NULL;
END;
""")

# === END TESTS ===
