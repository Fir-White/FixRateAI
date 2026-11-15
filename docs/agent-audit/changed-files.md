# Changed files at the verified code checkpoint

Base: `f8178754433d57cf5cfeb2690eb64b2fe0207ec2`. Code checkpoint: `fe39fb766e40d0def6793dd5de388990ce0b6acc`. Files: **81**.

This manifest describes the cumulative audit diff, not production deployment. Final evidence-only documentation is recorded in the subsequent documentation commit.

## README.md

- [README.md](../../README.md)

## backend

- [backend/app/assistant/analysis_scope.py](../../backend/app/assistant/analysis_scope.py)
- [backend/app/assistant/evidence.py](../../backend/app/assistant/evidence.py)
- [backend/app/assistant/explicit_draft.py](../../backend/app/assistant/explicit_draft.py)
- [backend/app/assistant/grounding.py](../../backend/app/assistant/grounding.py)
- [backend/app/assistant/intents.py](../../backend/app/assistant/intents.py)
- [backend/app/assistant/inventory_report.py](../../backend/app/assistant/inventory_report.py)
- [backend/app/assistant/photo_reading.py](../../backend/app/assistant/photo_reading.py)
- [backend/app/assistant/prompts/assistant.md](../../backend/app/assistant/prompts/assistant.md)
- [backend/app/assistant/read_transport.py](../../backend/app/assistant/read_transport.py)
- [backend/app/assistant/service.py](../../backend/app/assistant/service.py)
- [backend/app/assistant/task_report.py](../../backend/app/assistant/task_report.py)
- [backend/app/assistant/tools.py](../../backend/app/assistant/tools.py)
- [backend/app/assistant/workbook_readiness.py](../../backend/app/assistant/workbook_readiness.py)
- [backend/app/assistant/workbooks.py](../../backend/app/assistant/workbooks.py)
- [backend/app/integration/assistant_workspace.py](../../backend/app/integration/assistant_workspace.py)
- [backend/app/integration/management.py](../../backend/app/integration/management.py)
- [backend/app/integration/planning.py](../../backend/app/integration/planning.py)
- [backend/app/integration/task_analytics.py](../../backend/app/integration/task_analytics.py)
- [backend/app/orchestrator/decision.py](../../backend/app/orchestrator/decision.py)
- [backend/app/orchestrator/forecast.py](../../backend/app/orchestrator/forecast.py)
- [backend/app/scheduling/generator.py](../../backend/app/scheduling/generator.py)
- [backend/app/scheduling/optimization.py](../../backend/app/scheduling/optimization.py)
- [backend/app/schemas/assistant.py](../../backend/app/schemas/assistant.py)
- [backend/app/security/sessions.py](../../backend/app/security/sessions.py)

## contracts

- [contracts/assistant.schema.json](../../contracts/assistant.schema.json)

## docs

- [docs/PLAN.md](../../docs/PLAN.md)
- [docs/agent-audit/README.md](../../docs/agent-audit/README.md)
- [docs/agent-audit/agent-quality-metrics.md](../../docs/agent-audit/agent-quality-metrics.md)
- [docs/agent-audit/autonomous-progress.md](../../docs/agent-audit/autonomous-progress.md)
- [docs/agent-audit/changed-files.md](../../docs/agent-audit/changed-files.md)
- [docs/agent-audit/final-report.md](../../docs/agent-audit/final-report.md)
- [docs/agent-audit/known-defects.md](../../docs/agent-audit/known-defects.md)
- [docs/agent-audit/planning-evaluation.md](../../docs/agent-audit/planning-evaluation.md)
- [docs/agent-audit/requirements-matrix.md](../../docs/agent-audit/requirements-matrix.md)
- [docs/agent-audit/security-findings.md](../../docs/agent-audit/security-findings.md)
- [docs/agent-audit/test-inventory.md](../../docs/agent-audit/test-inventory.md)
- [docs/agent-audit/tool-contract-audit.md](../../docs/agent-audit/tool-contract-audit.md)
- [docs/releases/2026-11-15-agent-redteam.md](../../docs/releases/2026-11-15-agent-redteam.md)
- [docs/service/INDEX.md](../../docs/service/INDEX.md)
- [docs/service/assistant.md](../../docs/service/assistant.md)
- [docs/service/verification.md](../../docs/service/verification.md)

## ml_service

- [ml_service/app/providers/ollama.py](../../ml_service/app/providers/ollama.py)

## scripts

- [scripts/agent_redteam.py](../../scripts/agent_redteam.py)
- [scripts/generate_agent_redteam.py](../../scripts/generate_agent_redteam.py)
- [scripts/summarize_agent_audit.py](../../scripts/summarize_agent_audit.py)
- [scripts/verify.py](../../scripts/verify.py)

## tests

- [tests/backend/test_agent_redteam_command_feedback.py](../../tests/backend/test_agent_redteam_command_feedback.py)
- [tests/backend/test_agent_redteam_commit_loss.py](../../tests/backend/test_agent_redteam_commit_loss.py)
- [tests/backend/test_agent_redteam_controls.py](../../tests/backend/test_agent_redteam_controls.py)
- [tests/backend/test_agent_redteam_explicit_draft.py](../../tests/backend/test_agent_redteam_explicit_draft.py)
- [tests/backend/test_agent_redteam_failed_reads.py](../../tests/backend/test_agent_redteam_failed_reads.py)
- [tests/backend/test_agent_redteam_forecast_provenance.py](../../tests/backend/test_agent_redteam_forecast_provenance.py)
- [tests/backend/test_agent_redteam_grounding.py](../../tests/backend/test_agent_redteam_grounding.py)
- [tests/backend/test_agent_redteam_intent_dispatch.py](../../tests/backend/test_agent_redteam_intent_dispatch.py)
- [tests/backend/test_agent_redteam_live.py](../../tests/backend/test_agent_redteam_live.py)
- [tests/backend/test_agent_redteam_live_mutations.py](../../tests/backend/test_agent_redteam_live_mutations.py)
- [tests/backend/test_agent_redteam_matrix.py](../../tests/backend/test_agent_redteam_matrix.py)
- [tests/backend/test_agent_redteam_photo_reading.py](../../tests/backend/test_agent_redteam_photo_reading.py)
- [tests/backend/test_agent_redteam_properties.py](../../tests/backend/test_agent_redteam_properties.py)
- [tests/backend/test_agent_redteam_proposal_sources.py](../../tests/backend/test_agent_redteam_proposal_sources.py)
- [tests/backend/test_agent_redteam_provenance.py](../../tests/backend/test_agent_redteam_provenance.py)
- [tests/backend/test_agent_redteam_repairs.py](../../tests/backend/test_agent_redteam_repairs.py)
- [tests/backend/test_agent_redteam_scope.py](../../tests/backend/test_agent_redteam_scope.py)
- [tests/backend/test_agent_redteam_staff_preservation.py](../../tests/backend/test_agent_redteam_staff_preservation.py)
- [tests/backend/test_agent_redteam_state.py](../../tests/backend/test_agent_redteam_state.py)
- [tests/backend/test_agent_redteam_trace_privacy.py](../../tests/backend/test_agent_redteam_trace_privacy.py)
- [tests/backend/test_agent_redteam_workbook_readiness.py](../../tests/backend/test_agent_redteam_workbook_readiness.py)
- [tests/backend/test_assistant_assignment_endtoend.py](../../tests/backend/test_assistant_assignment_endtoend.py)
- [tests/backend/test_assistant_production_scenarios.py](../../tests/backend/test_assistant_production_scenarios.py)
- [tests/backend/test_assistant_task_analytics.py](../../tests/backend/test_assistant_task_analytics.py)
- [tests/backend/test_domain_scenarios.py](../../tests/backend/test_domain_scenarios.py)
- [tests/backend/test_forecast_audit.py](../../tests/backend/test_forecast_audit.py)
- [tests/backend/test_orchestration.py](../../tests/backend/test_orchestration.py)
- [tests/backend/test_planning.py](../../tests/backend/test_planning.py)
- [tests/backend/test_schedule_audit.py](../../tests/backend/test_schedule_audit.py)
- [tests/fixtures/assistant/live_mutation_cases.json](../../tests/fixtures/assistant/live_mutation_cases.json)
- [tests/fixtures/assistant/live_red_team_cases.json](../../tests/fixtures/assistant/live_red_team_cases.json)
- [tests/fixtures/assistant/red_team_cases.json](../../tests/fixtures/assistant/red_team_cases.json)
- [tests/ml/test_ollama_agent_grammar.py](../../tests/ml/test_ollama_agent_grammar.py)
- [tests/ml/test_ollama_chat.py](../../tests/ml/test_ollama_chat.py)

## Comparison with the last known published ref

Original origin/kran_dev locally tracks `81df9221527794fd6b1ec476999b0cf0d897e7d7`; it was read without fetching or pushing. `f817875` is the local pre-audit snapshot, not the published ref.

| Range | Files | Scope |
|---|---:|---|
| 81df922 to f817875 | 67 | Pre-existing local iteration, preserved unchanged by this audit |
| f817875 to audited code/documentation | 81 | This isolated audit |
| 81df922 to audit HEAD | 126 | Combined diff, overlapping paths counted once |

The preceding iteration is documented in [its release](../releases/2026-11-15-assistant-iteration.md). It includes migration021, chat UI, message attachments, production workflows and earlier P0/analytics corrections; these are not presented as newly implemented by this audit. Its files:

- [.env.example](../../.env.example)
- [AGENTS.md](../../AGENTS.md)
- [README.md](../../README.md)
- [backend/app/assistant/attachments.py](../../backend/app/assistant/attachments.py)
- [backend/app/assistant/capabilities.py](../../backend/app/assistant/capabilities.py)
- [backend/app/assistant/inventory_report.py](../../backend/app/assistant/inventory_report.py)
- [backend/app/assistant/production_workflow.py](../../backend/app/assistant/production_workflow.py)
- [backend/app/assistant/prompts/assistant.md](../../backend/app/assistant/prompts/assistant.md)
- [backend/app/assistant/prompts/conversation.md](../../backend/app/assistant/prompts/conversation.md)
- [backend/app/assistant/prompts/final.md](../../backend/app/assistant/prompts/final.md)
- [backend/app/assistant/prompts/router.md](../../backend/app/assistant/prompts/router.md)
- [backend/app/assistant/read_transport.py](../../backend/app/assistant/read_transport.py)
- [backend/app/assistant/service.py](../../backend/app/assistant/service.py)
- [backend/app/assistant/task_report.py](../../backend/app/assistant/task_report.py)
- [backend/app/assistant/tools.py](../../backend/app/assistant/tools.py)
- [backend/app/assistant/workbooks.py](../../backend/app/assistant/workbooks.py)
- [backend/app/catalog_excel.py](../../backend/app/catalog_excel.py)
- [backend/app/integration/assistant.py](../../backend/app/integration/assistant.py)
- [backend/app/integration/assistant_workspace.py](../../backend/app/integration/assistant_workspace.py)
- [backend/app/integration/management.py](../../backend/app/integration/management.py)
- [backend/app/integration/task_analytics.py](../../backend/app/integration/task_analytics.py)
- [backend/app/schemas/assistant.py](../../backend/app/schemas/assistant.py)
- [compose.cloud.yaml](../../compose.cloud.yaml)
- [compose.ollama.yaml](../../compose.ollama.yaml)
- [contracts/assistant-tools.json](../../contracts/assistant-tools.json)
- [contracts/assistant.schema.json](../../contracts/assistant.schema.json)
- [database/migrations/021_assistant_message_attachments.sql](../../database/migrations/021_assistant_message_attachments.sql)
- [docs/ASSISTANT_ANALYTICS_AUDIT.md](../../docs/ASSISTANT_ANALYTICS_AUDIT.md)
- [docs/ASSISTANT_P0_AUDIT.md](../../docs/ASSISTANT_P0_AUDIT.md)
- [docs/ASSISTANT_PRODUCTION_SCENARIOS.md](../../docs/ASSISTANT_PRODUCTION_SCENARIOS.md)
- [docs/PLAN.md](../../docs/PLAN.md)
- [docs/releases/2026-11-15-assistant-iteration.md](../../docs/releases/2026-11-15-assistant-iteration.md)
- [docs/service/INDEX.md](../../docs/service/INDEX.md)
- [docs/service/assistant.md](../../docs/service/assistant.md)
- [docs/service/database.md](../../docs/service/database.md)
- [docs/service/development.md](../../docs/service/development.md)
- [docs/service/runtime.md](../../docs/service/runtime.md)
- [docs/service/user-experience.md](../../docs/service/user-experience.md)
- [docs/service/verification.md](../../docs/service/verification.md)
- [frontend/package-lock.json](../../frontend/package-lock.json)
- [frontend/package.json](../../frontend/package.json)
- [frontend/src/features/assistant/AssistantAnswer.tsx](../../frontend/src/features/assistant/AssistantAnswer.tsx)
- [frontend/src/features/assistant/assistant.css](../../frontend/src/features/assistant/assistant.css)
- [frontend/src/index.css](../../frontend/src/index.css)
- [frontend/src/pages/AssistantPage.tsx](../../frontend/src/pages/AssistantPage.tsx)
- [frontend/src/shared/api/assistant.ts](../../frontend/src/shared/api/assistant.ts)
- [ml_service/app/cv/local_vision.py](../../ml_service/app/cv/local_vision.py)
- [ml_service/app/providers/aitunnel.py](../../ml_service/app/providers/aitunnel.py)
- [ml_service/app/providers/ollama.py](../../ml_service/app/providers/ollama.py)
- [scripts/start_local.py](../../scripts/start_local.py)
- [scripts/start_ollama_chat.ps1](../../scripts/start_ollama_chat.ps1)
- [tests/backend/test_assistant.py](../../tests/backend/test_assistant.py)
- [tests/backend/test_assistant_assignment_endtoend.py](../../tests/backend/test_assistant_assignment_endtoend.py)
- [tests/backend/test_assistant_capabilities.py](../../tests/backend/test_assistant_capabilities.py)
- [tests/backend/test_assistant_message_files.py](../../tests/backend/test_assistant_message_files.py)
- [tests/backend/test_assistant_p0.py](../../tests/backend/test_assistant_p0.py)
- [tests/backend/test_assistant_production_scenarios.py](../../tests/backend/test_assistant_production_scenarios.py)
- [tests/backend/test_assistant_production_workflows.py](../../tests/backend/test_assistant_production_workflows.py)
- [tests/backend/test_assistant_task_analytics.py](../../tests/backend/test_assistant_task_analytics.py)
- [tests/backend/test_assistant_workbooks.py](../../tests/backend/test_assistant_workbooks.py)
- [tests/backend/test_cloud_configuration.py](../../tests/backend/test_cloud_configuration.py)
- [tests/fixtures/assistant/production_scenarios.json](../../tests/fixtures/assistant/production_scenarios.json)
- [tests/ml/test_aitunnel.py](../../tests/ml/test_aitunnel.py)
- [tests/ml/test_ollama_chat.py](../../tests/ml/test_ollama_chat.py)
- [tests/web/e2e/assistant-composer.spec.ts](../../tests/web/e2e/assistant-composer.spec.ts)
- [tests/web/unit/features/assistant/AssistantAnswer.test.tsx](../../tests/web/unit/features/assistant/AssistantAnswer.test.tsx)
- [tests/web/unit/pages/AssistantPage.test.tsx](../../tests/web/unit/pages/AssistantPage.test.tsx)
