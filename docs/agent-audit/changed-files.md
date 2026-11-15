# Changed files at the verified code checkpoint

Base: `f817875`. Code checkpoint: `75a1fa9ee873c7791c6f3ec1691ed345049e159f`. Files: **68**.

This manifest describes the cumulative audit diff, not production deployment. Final evidence-only documentation is recorded in the subsequent documentation commit.

## Backend

- [backend/app/assistant/analysis_scope.py](../../backend/app/assistant/analysis_scope.py)
- [backend/app/assistant/evidence.py](../../backend/app/assistant/evidence.py)
- [backend/app/assistant/grounding.py](../../backend/app/assistant/grounding.py)
- [backend/app/assistant/prompts/assistant.md](../../backend/app/assistant/prompts/assistant.md)
- [backend/app/assistant/read_transport.py](../../backend/app/assistant/read_transport.py)
- [backend/app/assistant/service.py](../../backend/app/assistant/service.py)
- [backend/app/assistant/task_report.py](../../backend/app/assistant/task_report.py)
- [backend/app/assistant/tools.py](../../backend/app/assistant/tools.py)
- [backend/app/assistant/workbook_readiness.py](../../backend/app/assistant/workbook_readiness.py)
- [backend/app/assistant/workbooks.py](../../backend/app/assistant/workbooks.py)
- [backend/app/integration/assistant_workspace.py](../../backend/app/integration/assistant_workspace.py)
- [backend/app/integration/planning.py](../../backend/app/integration/planning.py)
- [backend/app/integration/task_analytics.py](../../backend/app/integration/task_analytics.py)
- [backend/app/orchestrator/decision.py](../../backend/app/orchestrator/decision.py)
- [backend/app/orchestrator/forecast.py](../../backend/app/orchestrator/forecast.py)
- [backend/app/scheduling/generator.py](../../backend/app/scheduling/generator.py)
- [backend/app/scheduling/optimization.py](../../backend/app/scheduling/optimization.py)
- [backend/app/schemas/assistant.py](../../backend/app/schemas/assistant.py)
- [backend/app/security/sessions.py](../../backend/app/security/sessions.py)

## ML transport

- [ml_service/app/providers/ollama.py](../../ml_service/app/providers/ollama.py)

## Contracts

- [contracts/assistant.schema.json](../../contracts/assistant.schema.json)

## Runners

- [scripts/agent_redteam.py](../../scripts/agent_redteam.py)
- [scripts/generate_agent_redteam.py](../../scripts/generate_agent_redteam.py)
- [scripts/summarize_agent_audit.py](../../scripts/summarize_agent_audit.py)
- [scripts/verify.py](../../scripts/verify.py)

## Tests and fixtures

- [tests/backend/test_agent_redteam_command_feedback.py](../../tests/backend/test_agent_redteam_command_feedback.py)
- [tests/backend/test_agent_redteam_commit_loss.py](../../tests/backend/test_agent_redteam_commit_loss.py)
- [tests/backend/test_agent_redteam_controls.py](../../tests/backend/test_agent_redteam_controls.py)
- [tests/backend/test_agent_redteam_forecast_provenance.py](../../tests/backend/test_agent_redteam_forecast_provenance.py)
- [tests/backend/test_agent_redteam_grounding.py](../../tests/backend/test_agent_redteam_grounding.py)
- [tests/backend/test_agent_redteam_live.py](../../tests/backend/test_agent_redteam_live.py)
- [tests/backend/test_agent_redteam_live_mutations.py](../../tests/backend/test_agent_redteam_live_mutations.py)
- [tests/backend/test_agent_redteam_matrix.py](../../tests/backend/test_agent_redteam_matrix.py)
- [tests/backend/test_agent_redteam_properties.py](../../tests/backend/test_agent_redteam_properties.py)
- [tests/backend/test_agent_redteam_provenance.py](../../tests/backend/test_agent_redteam_provenance.py)
- [tests/backend/test_agent_redteam_repairs.py](../../tests/backend/test_agent_redteam_repairs.py)
- [tests/backend/test_agent_redteam_scope.py](../../tests/backend/test_agent_redteam_scope.py)
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
- [tests/ml/test_ollama_chat.py](../../tests/ml/test_ollama_chat.py)

## Documentation

- [README.md](../../README.md)
- [docs/PLAN.md](../../docs/PLAN.md)
- [docs/agent-audit/README.md](../../docs/agent-audit/README.md)
- [docs/agent-audit/agent-quality-metrics.md](../../docs/agent-audit/agent-quality-metrics.md)
- [docs/agent-audit/autonomous-progress.md](../../docs/agent-audit/autonomous-progress.md)
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
