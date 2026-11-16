"""Outcome-based assistant acceptance inventory; registration never implies acceptance.

This offline exporter does not construct an app, open a database, read .env or call
any provider. Each available role/operation gets its own positive acceptance cell.
Only explicit execution records can change a cell from not_run to passed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ROLES = ('director', 'chief_engineer', 'engineer', 'dispatcher', 'admin', 'executor')
CATEGORIES = ('reachability', 'positive_e2e', 'negative', 'mocked', 'api_domain')

# Requirements are product-level traceability from MVP_SCOPE §7; they do not
# assert that a tool implements the whole referenced requirement or passed it.
DOMAINS = {
    'access': ('MVP-01', ['AT-03', 'AT-10', 'AT-17'], ['D-01', 'D-05'],
               'Two isolated sites, six distinct role accounts and separate ownership; no production sessions.'),
    'registry': ('MVP-02', ['PLN-01', 'PLN-03', 'PLN-24', 'PLN-26'], ['D-01', 'D-02', 'D-03'],
                 'TEST equipment, system/type and versioned regulations; include equipment without tasks and a second inaccessible site.'),
    'excel': ('MVP-03', ['PLN-04', 'PLN-23', 'PLN-24', 'PLN-25', 'PLN-26', 'PLN-27', 'PLN-28', 'PLN-29', 'AT-01', 'AT-18', 'AT-30'], ['D-02', 'D-03'],
              'Versioned synthetic XLSX with source hashes, confirmed and unconfirmed rows, formula/text traps and a repeated import.'),
    'workforce': ('MVP-04', ['PLN-01', 'PLN-05', 'PLN-08', 'AT-02', 'AT-03', 'AT-05'], ['D-02', 'D-04'],
                  'Synthetic workers, qualified crew, shifts and absences; include an expired qualification and another site membership.'),
    'planning': ('MVP-05', ['PLN-02', 'PLN-03', 'PLN-06', 'PLN-08', 'PLN-09', 'PLN-10', 'PLN-11', 'PLN-16', 'PLN-27', 'AT-02', 'AT-04', 'AT-07'], ['D-01', 'D-02', 'D-03', 'D-04'],
                 'Confirmed synthetic norms/calendar, adequate qualified shifts, versioned draft, fixed placement and separately fingerprinted live schedule.'),
    'publication': ('MVP-06', ['PLN-07', 'PLN-10', 'PLN-13', 'PLN-17', 'PLN-21', 'AT-06', 'AT-08', 'AT-09', 'AT-11', 'AT-28'], ['D-04', 'D-05'],
                    'Validated TEST draft/proposal at the required lifecycle state; fingerprint live tasks, accepted facts and locks before each action.'),
    'execution': ('MVP-07', ['AN06', 'AN07', 'AT-16'], ['D-01', 'D-05'],
                  'Own assigned TEST task with confirmed checklist, permissions and synthetic photo/act attachments; independent engineer account.'),
    'review': ('MVP-08', ['AN06', 'AN07', 'AT-10', 'AT-11', 'AT-16'], ['D-05'],
               'Submitted TEST report with a complete attempt and evidence; engineer is distinct from executor; retain previous accepted facts.'),
    'components': ('MVP-09', ['PLN-08', 'PLN-18', 'PLN-19', 'PLN-20', 'AT-13', 'AT-14'], ['D-06'],
                   'TEST installed component with known unit/resource and readings, replacement part and independent historical snapshot.'),
    'reporting': ('MVP-10', ['PLN-06', 'PLN-11', 'PLN-14', 'AT-01', 'AT-11', 'AT-27'], ['D-01', 'D-07'],
                  'Synthetic task populations exceeding one page, all lifecycle states and a fixed site/timezone/period; independent SQL aggregate.'),
    'assistant': ('MVP-11', ['PLN-12', 'PLN-20', 'AT-08', 'AT-09', 'AT-10', 'AT-11', 'AT-12', 'AT-17', 'AT-30'], ['D-08', 'D-09'],
                  'Fresh private TEST conversation, installed pinned local Ollama model only; no downloads, external providers or live preference changes.'),
    'ml': ('MVP-12', ['AN06', 'AN07'], ['D-08', 'D-09'],
           'Synthetic consented photos or forecast inputs and a supported installed local model; external LLM routes disabled, ML limitations declared.'),
}

# name | domain | user goal | independent successful postcondition
# Explicit specifications make omissions fail export instead of silently falling
# back to the tool title or a generic HTTP-200 oracle.
SPECIFICATIONS = '''
chat_models|assistant|Show installed local chat models without generating an answer|Catalog matches local tags and excludes cloud-only entries in the local-only evaluation; no model download or preference mutation.
chat_model_preference|assistant|Show my saved model in this role and site|Selection and revision equal this actor/site/role preference; another role/site preference is absent.
chat_model_select|assistant|Use the named installed local model for my next messages|After confirmation only this TEST user's scoped preference changes; a new turn pins that model/digest and old turns retain their snapshot.
tasks_analyze|reporting|Count all tasks and explain unfinished work and overdue deadlines|Status counts equal independent SQL over the whole authorized scope, including records beyond page one; planned start is distinct from mandatory due date.
draft_changes|publication|Compare the two named versions of my draft|Reported added/removed/changed placements equal a direct version diff; unrelated and locked placements are identified correctly.
drafts_find|planning|Find my saved plan by its name and period|Expected TEST draft is found even beyond the first page; returned identifiers resolve to that draft and version within scope.
planning_context|planning|Show the data and decisions needed to plan this period|Selected period, source decisions, norms, capacity and missing inputs equal backend records; unknown values remain unknown.
inventory_read|registry|List all accessible sites, equipment and regulation gaps|Inventory equals authorized registry including equipment without tasks; published/draft regulations and missing planning data match independent queries.
attachment_read|assistant|Read the selected private file from this conversation|Returned text/page metadata derives from the selected attachment hash and range; no other chat/owner attachment is exposed and truncation is explicit.
workbook_readiness|excel|Check whether the selected sent workbooks contain confirmed inputs for a real staffing calculation|The authorized raw-workbook diagnostics match actual cells, hashes and selected current/prior sent attachments; unknown/invalid/formula-only norms, quantities and units remain distinct. Raw positive numbers do not certify norms/assets/capacity, can_calculate_real_staffing stays false until independently confirmed inputs exist, and any staffing goal remains explicitly unfinished without invented headcount or business writes.
equipment_list|registry|List equipment on the selected site|Set of returned equipment equals the authorized registry after complete pagination, including equipment without tasks.
equipment_read|registry|Open the equipment card by its inventory code|Code, name, commissioned date, revision and identifiers match the one resolved equipment row, with no modification.
catalog_read|registry|Show equipment systems, types and configuration choices|Choices correspond to actual scoped system/type records and resolve to usable identifiers without inventing values.
equipment_create|registry|Create a TEST pump with the specified code, name and system|Exactly one equipment row has the supplied fields/site after confirmation; none exists before confirmation and replay creates no second row.
equipment_edit|registry|Rename the named TEST equipment and keep all other fields|After confirmation the exact target name changes at a new revision; all unrequested fields and other equipment retain their prior values.
equipment_retire|registry|Retire the named unused TEST equipment with the stated reason|Target follows the backend retirement contract; its history remains readable and unrelated equipment/tasks are unchanged.
regulations_read|registry|Show the current equipment regulations and recurrence fields|All bound regulation versions and publication states equal stored records; yearly_count repeats are not converted into year intervals.
calendar_evidence|registry|Explain this equipment's saved recurrence and calculate dates for the specified period|Each configuration is read under the actual equipment authorization; semantics and source/effective dates equal the production generator with validity/basis, completeness and timezone explicit. Accepted history, saved tasks and manufacturer recommendations are not inferred from calculated obligations.
equipment_service_history|registry|Check actual accepted maintenance of this equipment during the specified local-date interval|Complete authorized report/acceptance records match this equipment, starts_on/ends_on, site timezone and only_accepted selection. Performance time derives from the report's recorded fact, not a mutable task start; submission fallback and unknown dates remain explicitly partial. Executor scope includes only assigned equipment and tasks, and empty accepted history is not absence of all planned work.
regulation_create|registry|Add the specified confirmed service configuration to this equipment|Exactly one binding/version contains supplied operation, pattern and norms after confirmation; no calendar/task publication occurs implicitly.
regulation_edit|registry|Change only the specified recurrence field in this equipment regulation|A new valid configuration revision contains the requested change; prior revision and unrelated norms/checklist fields are preserved.
tasks_list|reporting|List every task visible to me in the selected period|Task set and role filtering equal independent authorized API/SQL results after pagination; empty states and partial pages are explicit.
tasks_find|reporting|Find the task by equipment, title and period|All selectors apply together; target beyond page one is reachable and no result is silently broadened to another equipment or period.
equipment_find|registry|Find equipment by its exact inventory code|Resolved equipment identity and code match the unique scoped registry record; ambiguous matches remain unresolved.
staff_find|workforce|Find the named available worker for this site|Resolved user identity and active membership match the requested worker; qualifications/availability are not inferred from the person's name.
staff_read|workforce|Show this worker's role, memberships, shifts and qualifications|Returned membership/account flags and dates equal stored values; visibility follows caller role and contains no credentials.
task_read|execution|Open my selected task and its current instructions|State, revision, assignments, regulatory snapshot and report equal the authorized target resource; own-task restrictions apply for executor.
calendar_read|reporting|Show my authorized calendar for the chosen interval|Every event belongs to visible work and falls in the requested site timezone/interval; counts match an independent range query.
assignment_context|workforce|Show eligible people and constraints for this task|Candidates and crew requirements match deterministic qualifications/shift checks; inaccessible personnel and invented eligibility are absent.
assignment_prepare|workforce|Prepare a feasible assignment to the named people without applying it|Suggested command passes the actual server preview with exact task/workers/time; no assignment or task state changes.
assignment_preview|workforce|Check this crew and time interval before assigning|Feasible/conflict classification equals the shared validator; all qualification, capacity and overlap constraints are retained and no write occurs.
task_assign|workforce|Assign the specified feasible crew and time to this task|Confirmed assignment rows, time range and task revision match the validated proposal; no reservation exists before approval and replay is single application.
task_cancel|execution|Cancel the selected eligible task with this reason|Task reaches its documented cancelled state with reason and audit history; accepted facts remain intact and other tasks are unchanged.
task_start|execution|Start my currently assigned TEST task|Only the executor's allowed assignment reaches in-progress once; actual start is server recorded and no report is implicitly accepted.
report_save|execution|Save my checklist values and factual report as a draft|Persisted report contains exactly supplied values/units and attachment links; task is not submitted/accepted and previous attempt is retained.
report_submit|execution|Submit my completed report to the engineer|Task/report reach submitted once with the same complete evidence; no engineering acceptance is created and replay adds no duplicate attempt.
report_review|review|Accept the submitted report or return it with the stated reason|Chosen decision is persisted by an authorized independent engineer, attempts/history remain intact and only acceptance advances accepted maintenance fact.
photo_review|ml|Analyze the saved report photos as advisory evidence|A new local-model assessment references exact photo hashes and is persisted; unsupported/uncertain results remain explicit and task acceptance is unchanged.
forecast_run|ml|Calculate and save the supported forecast for this task|Stored forecast has actual deterministic/model provenance and input hash; no fabricated what-if or automatic schedule confirmation occurs.
workforce_read|workforce|Show the site team, shifts and qualifications|Staff/membership/shift/qualification sets equal scoped records including dates and expired flags; query volume is bounded independently of staff count.
catalogs_list|excel|List my saved source workbooks|Every authorized import is reachable across pages with correct original name/hash/version; another site's workbook is absent.
portfolio_list|planning|Find saved portfolio plans for the chosen period|Results equal scoped saved portfolio records and selected links reopen the same plan/version after reload.
portfolio_preview|planning|Preview one combined plan from the specified sources|Union of obligations is deduplicated by source identity; conflicts/missing data are explicit and no plan or real work is created.
portfolio_save|planning|Save this reviewed combined plan as a draft|One saved draft references the exact preview/source revisions and obligation set; live task/assignment fingerprints are unchanged.
draft_list|planning|Show my saved drafts|All scoped drafts are reachable with stable identifiers and version/period metadata; no live schedule is modified.
draft_read|planning|Open the saved draft and selected revision|Resource identity, source snapshots, revision and totals equal the saved version; stable link reload restores that selection.
draft_occurrences|planning|Show every obligation in the chosen draft revision|Complete paginated occurrence set equals that revision's stored obligations, including unscheduled and deficient items.
draft_policy|planning|Show the chosen draft's calendar and capacity policy|Returned policy is the exact selected revision, including unknown decisions and units rather than inferred defaults.
draft_load|planning|Compute load for this draft version and supplied capacity|Hours, concurrent crew demand, available useful capacity and deficits equal deterministic calculation with stated units; no live reservations appear.
draft_policy_edit|planning|Change only the specified draft policy with this reason|New draft revision contains the requested policy; previous versions, accepted facts, placements and live work remain unchanged unless explicitly recalculated.
draft_place|planning|Move and lock the selected draft segment at the specified time|New revision contains only the requested placement/lock with validated worker/time constraints; earlier version and live schedule are unchanged.
draft_undo_preview|publication|Show whether my last draft change can be undone|Preview references the actual last eligible actor/revision and exact inverse diff; it does not change the draft.
draft_undo|publication|Undo my last eligible draft change with this reason|A new version restores the documented prior values with audit history; no previous version is deleted and no live work is changed.
catalog_read_saved|excel|Open the selected saved source workbook metadata|Source name/hash, importer, row count and version match the preserved import; no reimport occurs.
catalog_operations|excel|Show all original operations from this workbook|Complete paginated rows and original cell coordinates equal preserved source data; unconfirmed and included operations are not converted to tasks.
draft_preview|planning|Preview a plan from the selected confirmed workbook rows|Computed obligations reflect supported frequency semantics and selected rows without duplicate inclusion; unresolved rows have explicit blockers and no writes.
draft_save|planning|Save the reviewed workbook plan as a draft|Saved sources/digests, period and occurrence totals equal preview; source workbook and live tasks/assignments remain unchanged.
draft_segments|planning|Show every segment of this draft obligation|Returned segments preserve total hours, units, locks, workers and dependency identity for the selected revision.
draft_versions|publication|Show the history of this draft|All saved revisions appear in chronological order with actor/reason; reloading a revision returns its immutable content.
draft_split|planning|Split this divisible obligation into the specified segments|New revision preserves total labor and required crew/dependencies; unrequested locks and live tasks are unchanged.
draft_validate|planning|Validate the selected draft before release|Independent shared validator reproduces all reported feasibility/deficit results; timeout is not reported as mathematical infeasibility and no write occurs.
optimization_start|planning|Start CP-SAT for this draft without publishing anything|One real solver run references exact source revision/limits after confirmation; recorded state and baseline are real and live task fingerprints remain unchanged.
optimization_list|planning|List saved solver runs for this draft|Runs match the draft's authorized run records and revisions; stale/current status is visible and no run is restarted by reading.
optimization_read|planning|Show this solver run's status and comparison metrics|State, feasibility, objective/bounds, baseline and optimized metrics match persisted solver result; feasible is not claimed proven optimal without proof.
optimization_placements|planning|Show all placements from the calculated variant|Complete placement set equals selected solver result including unscheduled obligations and fixed assignments.
optimization_apply|planning|Apply the chosen feasible variant to my draft|New draft revision equals validated run placements and preserves locks; solver/run provenance remains and live work is not published.
optimization_cancel|planning|Cancel the selected queued or running calculation|Run reaches cancelled/cancellation-requested then terminal according to worker contract; no calculated placements are silently applied or published.
publication_regulations|publication|Show approved instructions available for release|Only applicable approved versions are selectable; missing/unapproved instruction blockers match backend publication validation.
publication_profiles|publication|Show instruction templates available for workbook release|Profiles, applicability and versions equal authorized records; selecting a template does not fabricate approved regulatory data.
publication_prepare|publication|Prepare release of this validated draft without approving it|One proposal contains exact task/change diff and source digest; no live work changes and proposal is not already approved/published.
publication_list|publication|List release proposals for the selected draft|All authorized proposal records and their real approval/publication states are reachable with stable links.
publication_read|publication|Open the exact release proposal and its state|Target digest/revision, source version, approver and change summary equal persisted proposal; no transition occurs.
publication_changes|publication|Show every proposed live schedule change|Full paginated diff equals independently derived before/after work set, preserving started/accepted work and explicit conflict blockers.
publication_approve|publication|Approve this exact current release proposal|Authorized chief approval binds exact current digest once; live work is unchanged until separately confirmed publication.
publication_reject|publication|Reject the selected release proposal with this reason|Proposal becomes rejected with reason/actor/history; real tasks and previous approvals remain unchanged and replay does not duplicate transitions.
publication_publish|publication|Publish this specifically approved current proposal|Exactly the reviewed tasks/assignments are created/changed once; accepted facts and locks persist and stale digest/conflicts block before any write.
sites_list|access|List the sites I may work with|Site set equals active memberships for this account and contains no foreign site; active site is identified correctly.
site_switch|access|Switch to my other authorized TEST site|After explicit confirmation session scope/cookies reflect that site, old conversation is inaccessible in new scope and no membership is created implicitly.
session_logout|access|Sign me out of this TEST session|After confirmation session cookies are cleared and old session receives unauthorized responses; other user sessions are unchanged.
profile_read|access|Show my current profile and role|Identity, site, role and email match authenticated session and account; no password/hash/token appears.
profile_email|access|Change my email to the supplied TEST address|After confirmation and password entered only in protected field, email changes once; secret is absent from model/history/audit and other profile fields remain unchanged.
roles_list|access|Show roles supported by the application|Returned role identifiers/labels equal actual policy and do not grant any role to the caller.
user_roles|access|Show the authorized role information for the selected user|Visible memberships/roles match policy-filtered records; no escalation or foreign-user personal data leak occurs.
users_list|access|List registered users as an administrator|Full paginated administrative set equals scoped permitted accounts, with no hashes/credentials and no account mutation.
enrollment_read|access|Show applications awaiting administrative enrollment|Pending/decided application groups and permitted role/site choices match database state and scope.
enrollment_create|access|Enroll this synthetic person with the specified role and site|Exactly one expected TEST account/membership is created after confirmation; secret setup input stays protected and no unrequested role/membership is added.
application_decide|access|Approve or reject the selected membership application|Exactly the requested decision, role/site and reason are persisted; approval grants only reviewed membership and rejection grants none.
staff_edit|workforce|Change the named worker's specified administrative field|Only requested field changes; active membership, account state, qualification dates and other memberships retain previous values.
shift_create|workforce|Add the specified TEST worker shift and useful capacity|One shift with exact timezone-aware interval/capacity is persisted; overnight length and person-hours are not conflated.
shift_edit|workforce|Change only the specified existing shift interval|Shift revision has requested interval/capacity after validation; other shifts and memberships remain unchanged.
availability_create|workforce|Record this worker's absence for the specified interval|One absence with exact interval/type/reason is persisted and eligibility/load subsequently reflects it; assignments are not silently rescheduled.
availability_cancel|workforce|Cancel the selected absence with this reason|Target absence is cancelled with audit/history; other absences and existing accepted work are preserved.
staff_calendar|workforce|Show the selected permitted worker's calendar|Events reflect shifts, absences and assignments for requested interval; executor sees only permitted own data and all timezone boundaries are correct.
skill_create|workforce|Create the specified TEST qualification category|Exactly one category with supplied code/name is created; no worker is automatically qualified.
qualification_set|workforce|Grant this worker the specified qualification and validity dates|Worker-skill record contains exact validity/source and revision after approval; expiry checks use dates and unrelated qualifications remain unchanged.
qualification_revoke|workforce|Revoke the selected worker qualification with this reason|Qualification is revoked with retained history; subsequent candidate validation rejects the expired/revoked authorization and unrelated skills remain active.
crew_create|workforce|Create this named crew from the specified workers|Exactly one crew has exact reviewed membership and site; no work assignment or shift is implicitly created.
crew_edit|workforce|Change only this crew's specified membership|Crew revision contains reviewed people; old version/history and unrelated crews/assignments remain intact.
pattern_preview|planning|Preview dates for the supplied recurrence and holiday policy|Dates equal CalendarPattern/occurrence_pairs with normative and shifted dates separated; five yearly repeats are not a five-year interval and no tasks are generated.
system_create|registry|Create the specified TEST engineering system|One system with reviewed name/code/site exists after confirmation; no equipment or regulation is added implicitly.
equipment_type_create|registry|Create the specified equipment type|One type with reviewed fields is stored and available in catalog; no existing equipment type assignment changes.
registry_read|registry|Show the complete equipment hierarchy and classification|Buildings/systems/equipment/components equal authorized registry across pagination; equipment without tasks and unclassified systems remain visible.
system_classify|registry|Set the named system's specified classification|Only selected system classification/revision changes; hierarchy, equipment and historical records remain intact.
building_create|registry|Create this TEST building with the stated timezone|One reviewed building/site and documented memberships are created after confirmation; no existing site/configuration is overwritten.
components_read|components|Show installed and replaced components for this equipment|Component list, installation/replacement dates, units and resource facts match stored records; unknown limits remain unknown.
component_install|components|Install the named TEST component with its known starting reading|One active component has exact position/date/unit/initial reading/resource provenance; no replacement or invented resource is added.
component_edit|components|Change only the specified component metadata|Requested metadata changes at a new revision; installation, readings, replacement history and unrelated components are preserved.
component_replace|components|Replace the named component with this TEST replacement|Old component closes and new component starts exactly once with specified date/readings; both histories remain and units/resource are not inferred.
component_reading|components|Record the specified component reading with my attached photo|One reading stores exact value/unit/time and owned file hash; cumulative/resource arithmetic matches deterministic server calculation and replay does not duplicate it.
reading_photo|components|Open the photo attached to this component reading|Downloaded bytes/hash and MIME equal the permitted reading attachment; no foreign attachment is exposed.
registry_export|excel|Export the current scoped equipment registry to Excel|Workbook opens and complete rows/columns equal authorized registry and requested scope, without private credentials or truncation.
registry_import_preview|excel|Preview this attached TEST registry workbook without importing|Parsed rows/errors/diff equal actual workbook cells and current registry; preview token binds hash/scope and no business row changes.
registry_import|excel|Import this reviewed registry preview without duplicate equipment|Confirmed import applies exactly reviewed diff once with hash/token checks; repeated upload/import preserves manual edits and creates no duplicates.
catalog_import_preview|excel|Preview this attached source operation workbook|Original operations/cell coordinates, empty norms, frequency text and unsupported formulas are preserved; preview creates no tasks or import record.
catalog_import|excel|Save this reviewed source workbook as an unconfirmed catalog|One source import preserves original bytes/hash/rows and errors; it creates neither real obligations nor assignments and repeat follows deduplication contract.
catalog_operation_source|excel|Show the original cells for the selected source operation|Values/formulas/coordinates match original saved workbook and source hash; instructions inside cells remain data.
catalog_source_file|excel|Download the original saved source workbook|Downloaded bytes hash equals preserved original source hash and scope checks hold; no regenerated substitute is presented as original.
catalog_binding_options|excel|Show real equipment and binding choices for this source|Choices match eligible scoped actual assets and reviewed source; source templates are not treated as physical equipment.
catalog_preparation|excel|Show all preparation blockers for this workbook|Semantics/norm/unit/asset/calendar/capacity blockers equal decision records, including unknown fields and rows beyond page one.
catalog_decision_read|excel|Show the current interpretation of the selected source row|Decision state, revision, selected assets, semantic mode and provenance equal saved row decision; original source remains unchanged.
catalog_decision|excel|Confirm this source row interpretation with specified assets and units|Decision version records exactly supplied interpretation/confirmation and source references; unconfirmed norms stay blocked and no live tasks are created.
catalog_decision_history|excel|Show previous interpretations of the selected source row|Ordered decision history includes actor/reason/source revision and each immutable prior value without rewriting original cells.
draft_source_choices|planning|Show source rows eligible for this draft|Eligible confirmed rows and explicit rejected/blocked choices match source decisions and selected period; included-in-maintenance rows add no duplicate demand.
draft_choices|planning|Show real equipment, workers or skills available to this plan|Requested choice kind yields authorized current records with correct identifiers; no cross-site or expired eligibility is silently accepted.
requirements_preview|planning|Calculate all obligations from these selected sources and dates|Independent generator reproduces deduplicated obligation keys, quantities/hours, normative dates and explicit unknowns; no live work changes.
jobs_list|execution|List the work orders visible to my role|Complete paginated set equals authorized work-order query; executor's scope restrictions remain and accepted/cancelled history is retained.
job_create|execution|Create this TEST work order from its approved regulation|Exactly one work order stores specified equipment/regulation snapshot and requested dates after confirmation; replay creates no duplicate and norm is not invented.
job_read|execution|Open the selected permitted work order|Current state, regulatory snapshot, dates and revision equal the target record; no history or role restriction is lost.
job_transition|execution|Move this eligible TEST work order to the specified state|Only backend-permitted transition occurs with reason/actor/history and expected revision; no later state such as accepted is implied.
job_history|execution|Show all transitions of this work order|Ordered history matches persisted events and actors, including prior attempts/reasons; no mutation occurs.
equipment_ui_list|registry|Show equipment with its maintenance status|Complete equipment set includes assets without jobs; maintenance indicators equal actual accepted history and open obligations.
equipment_history|registry|Show this equipment card and maintenance history|Card/history match selected equipment and accepted records; unfinished reports are not treated as completed maintenance.
calendar_preview|planning|Preview normative dates before generating tasks|Normative/shifted dates equal configured calendar policy within requested interval and no schedule plan, task or assignment is created.
workload_read|reporting|Calculate workload and staffing for this interval|Totals equal deterministic duration times simultaneous crew and confirmed useful capacity; missing norms/capacity prohibit an unsupported exact deficit.
calendar_generate|planning|Generate the reviewed normative TEST calendar for this period|Exactly expected obligation keys/tasks are persisted once; dates match generator/holiday policy, existing history remains and no automatic assignment occurs.
comparisons_list|ml|List saved forecast comparisons|Returned records match authorized comparison runs and actual model/input metadata; no new forecast is generated by reading.
comparison_read|ml|Show the selected forecast comparison and provenance|Numbers, inputs, actual model and uncertainty match saved comparison result; unsupported what-if and causal explanations are not fabricated.
quality_list|review|Show reports awaiting my engineering review|Queue equals submitted reports visible to the engineer, excluding already accepted facts and unauthorized/self-acceptance paths.
photo_upload|execution|Attach this private photo to my TEST report|One owned photo record links exact bytes/hash/stage to the permitted task after approval; repeated upload follows deduplication and no unrelated file is attached.
photo_read|execution|Open this permitted report photo|Downloaded bytes/hash and metadata equal saved photo; authorization follows task ownership/site/role.
act_upload|execution|Attach this private synthetic act to my TEST report|Owned act bytes/hash and metadata link to the correct task/attempt once; prior evidence is retained and act is not preverified.
act_verify|review|Verify the selected submitted act with this decision|Authorized engineer decision/actor/time and reason are stored for the exact act; task acceptance remains a separate operation.
task_attempts|review|Show the full attempt and evidence history of this task|All attempts, submitted/returned/accepted states and evidence links equal retained immutable history.
task_reopen|review|Reopen the accepted TEST task with this documented reason|Chief-only reopen creates the documented next attempt/state with history; original accepted fact is preserved rather than overwritten.
late_authorize|review|Authorize engineering review of this late TEST report|Explicit chief authorization window/reason is stored for the exact report; no acceptance occurs until separately reviewed.
late_execution|review|Authorize this task's specified late execution window|Stored chief authorization has exact valid interval/reason; earlier accepted facts and other task permissions remain unchanged.
plans_list|planning|List normative monthly plans for my scope|Plan identities, states and periods match authorized database records; selected plan link remains stable after reload.
plan_approve|publication|Approve this exact eligible monthly normative plan|Chief approval binds the selected current plan once with actor/history; unrelated plans/accepted work remain unchanged and replay adds no duplicate approval.
overview_read|reporting|Show indicators for all sites I may view|Counts and denominators equal independently computed authorized aggregates with clear period/timezone; inaccessible sites and unconfirmed numeric assumptions are absent.
report_export|reporting|Export the selected plan or work-order report to Excel|Workbook row set, chosen revision, columns and numeric totals equal authorized API/SQL oracle for the requested interval.
schedule_matrix|reporting|Show the normative obligation matrix for this period|Equipment-operation-date cells equal actual obligation generator and preserved facts; source templates and repeated pages are not double counted.
comparison_confirm|ml|Confirm this reviewed supported forecast variant|One confirmation stores selected comparison/input digest and permitted resulting state; no unrequested publication or unsupported calculation is performed.
checklist_catalog|registry|Show approved checklist templates for this maintenance|Template versions, required fields/units and applicability equal saved catalog; draft/unconfirmed methodology is not described as customer-approved.
notifications_list|access|Show my notifications including unread items|Complete scoped set and unread count equal this user/site records; another user's notifications are absent.
notifications_read_all|access|Mark all my current notifications read|Only this actor's intended scoped notifications become read once; no notification is deleted and other actors' records remain unchanged.
notifications_clear|access|Clear all my current notifications after showing the scope|Only reviewed actor/scope notifications are removed or cleared per contract; other actors and business audit/history remain intact.
notification_delete|access|Delete the selected one of my TEST notifications|Only target owned notification is removed/cleared; unread totals are recomputed and other notifications remain unchanged.
notification_read|access|Mark this one of my notifications read|Only target owned notification becomes read with correct count; replay is harmless and no message is deleted.
incidents_list|execution|Show the defect incidents visible to my role|Complete incident set equals scoped ownership/role query with actual state and linked tasks; private foreign incidents are absent.
incident_create|execution|Report this TEST defect with my attached photo and description|One incident records exact description/equipment/location/owned photo once; no work order, analysis or acceptance is implicitly created.
incident_photo|execution|Open the photo of the selected permitted defect incident|Returned bytes/hash match the incident's saved owned photo under role/site checks.
incident_analyze|ml|Analyze this TEST defect using its saved evidence|Persisted advisory local assessment references actual incident/photo/input and uncertainty; no automatic engineering decision or task creation occurs.
incident_task|execution|Create the reviewed TEST work task from this analyzed incident|Exactly one task links the selected incident and approved explicit parameters after chief confirmation; incident history remains and replay creates no duplicate.
operations_list|registry|Show all service operations and publication states|Complete operation/version set equals authorized registry, including unpublished operations and required norm/source fields.
operation_read|registry|Show this operation's approved requirements and recurrence|Fields, units, publication/version and provenance match stored operation; no manufacturer recommendation or inferred norm is invented.
operation_create|registry|Create this TEST maintenance operation with explicit confirmed inputs|One operation stores exact supplied checklist/norm/recurrence/source at documented publication state; no equipment binding or tasks are created implicitly.
operation_edit|registry|Change only the specified TEST operation field|New valid revision contains requested field and retained source/history; existing task snapshots and other operation fields remain unchanged.
operation_retire|registry|Disable the selected TEST maintenance operation|Target is inactive per backend contract while historical bindings/task snapshots remain readable; unrelated operations remain active.
regulations_list|registry|Show published and draft regulation versions|Complete authorized regulation/version set and publication states equal stored records; draft versions are not represented as approved.
canonical_tasks|reporting|Show task records with normative parameters for this interval|Complete authorized task set and normative snapshot fields equal canonical backend/SQL records, including all lifecycle states.
canonical_calendar|reporting|Show the normative calendar events for this interval|Complete event set and normative/assigned date distinctions equal authorized calendar records and configured timezone policy.
equipment_executions|registry|Show the equipment's actual accepted maintenance history|Only accepted completed execution facts match equipment and period; submitted/in-progress tasks are excluded and absence of facts is not absence of all tasks.
ai_models|ml|Show supported photo-analysis models without running them|Catalog reflects configured/installed supported local models and availability; opening the catalog performs no generation, download or preference change.
'''


def specifications():
    result = {}
    for line in SPECIFICATIONS.strip().splitlines():
        name, domain, goal, postcondition = line.split('|')
        if name in result:
            raise AssertionError(f'Duplicate positive specification: {name}')
        if domain not in DOMAINS:
            raise AssertionError(f'Unknown domain: {domain}')
        result[name] = dict(domain=domain, goal=goal, postcondition=postcondition)
    return result


def static_test_mentions(root, names):
    """Candidate test locations only. A mention is neither execution nor success."""
    result = {name: [] for name in names}
    for path in sorted((root / 'tests/backend').glob('test_*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith('test_'):
                continue
            mentions = {part.value for part in ast.walk(node) if isinstance(part, ast.Constant) and isinstance(part.value, str)}
            for name in names & mentions:
                result[name].append(f'{path.relative_to(root).as_posix()}::{node.name}')
    return result


def build(manifest, *, root=ROOT, evidence=None):
    specs = specifications()
    tools = {tool['name']: tool for tool in manifest['tools']}
    missing, obsolete = set(tools) - set(specs), set(specs) - set(tools)
    if missing or obsolete:
        raise AssertionError(f'Acceptance specifications missing={sorted(missing)}, obsolete={sorted(obsolete)}')
    mentions = static_test_mentions(root, set(tools))
    operations = []
    cells = []
    for name, tool in tools.items():
        spec = specs[name]
        block, requirements, decisions, fixture = DOMAINS[spec['domain']]
        operations.append(dict(
            operation=name, title=tool['title'], method=tool['method'], path=tool['path'],
            roles=tool['roles'], denied_roles=[role for role in ROLES if role not in tool['roles']],
            requires_confirmation=tool['requires_confirmation'],
            protected_inputs=tool['protected_inputs'], optional_protected_inputs=tool['optional_protected_inputs'],
            file_fields=tool['file_fields'], domain=spec['domain'],
            traceability=dict(mvp_blocks=list(dict.fromkeys([block, 'MVP-11'])), source_requirements=requirements,
                              scope='Product-level mapping from docs/MVP_SCOPE.md section 7; not proof of complete requirement implementation.',
                              customer_decision_dependencies=decisions),
            positive_scenario=dict(user_goal=spec['goal'], fixture=fixture,
                first_visible_action='Open a fresh private conversation as the specified role and state this goal in natural language.',
                execution='Let the orchestrator resolve entities and choose any correct authorized tools; provide only missing user decisions. ' +
                          ('Review the exact target/diff and confirm only the intended action with its own payload hash.' if tool['requires_confirmation'] else 'Do not confirm any unrelated mutation; this operation has a read-only outcome.'),
                postconditions=[spec['postcondition'],
                    'Verify the goal against an independent authorized API/database/file oracle, not answer keywords or an exact tool sequence.',
                    'Reopen the conversation/resource after reload and verify persisted outcome and explicitly outstanding goals.'],
                next_action='Open the verified resource/result; if a dependency remains unresolved it stays explicitly pending/blocked.',
                forbidden_effects=['No cross-user/site/role data or rights expansion.', 'No unrequested writes or unsupported engineering/manufacturer claims.'] +
                                  (['No business mutation before the concrete human confirmation; repeated confirmation cannot duplicate the result.'] if tool['requires_confirmation'] else ['Business state is unchanged by this read/preview.'])),
            candidate_test_mentions=mentions[name],
            candidate_test_note='Static string references only; may be negative, mocked, incomplete or unexecuted. Never counted as passed.',
        ))
        for role in tool['roles']:
            cells.append(dict(operation=name, role=role, registered=True,
                              verification={category:dict(status='not_run', records=[]) for category in CATEGORIES}))
    index = {(cell['operation'], cell['role']): cell for cell in cells}
    for record in evidence or []:
        validate_record(record, index)
        cell = index[(record['operation'], record['role'])]
        category = record['category']
        cell['verification'][category]['records'].append(record)
        # Keep failures visible even after a later pass; latest execution is the
        # current status and all attempts remain present for independent review.
        cell['verification'][category]['status'] = record['status']
    summary = dict(operations=len(operations), role_operation_cells=len(cells),
                   by_role={role:sum(cell['role'] == role for cell in cells) for role in ROLES},
                   verification={category:{status:sum(cell['verification'][category]['status'] == status for cell in cells)
                                 for status in ('passed', 'failed', 'skipped', 'not_run')} for category in CATEGORIES})
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return dict(format_version=1, catalog_sha256=hashlib.sha256(canonical).hexdigest(),
                acceptance_rule='A finished response, registered tool, HTTP 200, negative boundary test, mocked completion or successful individual call does not prove the user goal. Positive acceptance requires an independently verified final result and data state for this exact role/operation.',
                generative_policy='Installed local Ollama only; no external LLM/fallback, weight downloads or runtime user preference changes.',
                summary=summary, operations=operations, cells=cells,
                excluded_routes=manifest['excluded'],
                exclusions_note='Exact infrastructure/pre-login/compatibility exclusions are inherited from the capability manifest. Password change is explicitly excluded by the owner; aliases inherit canonical operation acceptance rather than independent claims.')


def validate_record(record, index):
    required = {'operation', 'role', 'category', 'status', 'run_id', 'source_commit', 'fixture_sha256', 'artifact', 'test_node'}
    if required - set(record):
        raise ValueError(f'Incomplete execution evidence: {sorted(required - set(record))}')
    if (record['operation'], record['role']) not in index:
        raise ValueError('Evidence does not address an available role/operation cell')
    if record['category'] not in CATEGORIES or record['status'] not in ('passed', 'failed', 'skipped'):
        raise ValueError('Unknown evidence category or result')
    if not all(isinstance(record[key], str) and record[key].strip() for key in ('run_id', 'source_commit', 'fixture_sha256', 'artifact', 'test_node')):
        raise ValueError('Execution provenance must be nonempty')
    if len(record['source_commit']) != 40 or any(c not in '0123456789abcdef' for c in record['source_commit']):
        raise ValueError('source_commit must be an exact commit SHA')
    if len(record['fixture_sha256']) != 64 or any(c not in '0123456789abcdef' for c in record['fixture_sha256']):
        raise ValueError('fixture_sha256 must identify the actual input snapshot')
    if record['category'] == 'positive_e2e' and record['status'] == 'passed':
        if record.get('provider') != 'ollama' or record.get('mocked') is not False:
            raise ValueError('Positive generative E2E requires actual local Ollama, never a mock or external provider')
        for condition in ('goal_achieved', 'data_verified', 'no_unconfirmed_writes'):
            if record.get(condition) is not True:
                raise ValueError(f'Positive E2E requires explicit {condition}')
        if (not isinstance(record.get('model_ref'), str)
                or not re.fullmatch(r'ollama:[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}', record['model_ref'])
                or 'cloud' in record['model_ref'].casefold()):
            raise ValueError('Positive E2E requires the actual pinned Ollama model reference')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--evidence', type=Path, default=ROOT / 'contracts/assistant-acceptance-evidence.json', help='Explicit executed records; never infer success from test names')
    parser.add_argument('--output', type=Path, default=ROOT / 'contracts/assistant-acceptance.json')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'contracts/assistant-tools.json').read_text(encoding='utf-8'))
    evidence = json.loads(args.evidence.read_text(encoding='utf-8')) if args.evidence.exists() else None
    result = build(manifest, evidence=evidence)
    if args.write:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    else:
        assert json.loads(args.output.read_text(encoding='utf-8')) == result, 'Run scripts/assistant_acceptance_matrix.py --write'
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
