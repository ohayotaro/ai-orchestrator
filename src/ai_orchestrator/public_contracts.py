"""Reviewed public *data/wire* surface; not a promise of private Python imports.

Response schemas describe the existing envelopes. They are used by inventory
and conformance tests, never to grant authority or to rewrite runtime results.
Open report maps/opaque evidence are explicit extension points, not approvals.
"""
from __future__ import annotations

import copy
import dataclasses
import importlib
import inspect
import json
from pathlib import Path
from typing import Any

SURFACE = Path(__file__).resolve().parent / 'assets/public-surface.json'
STRING = {'type': 'string'}
BOOL = {'type': 'boolean'}
NUMBER = {'type': 'number'}
INTEGER = {'type': 'integer'}
OBJECT = {'type': 'object'}
NULLABLE_OBJECT = {'type': ['object', 'null']}
NULLABLE_STRING = {'type': ['string', 'null']}
STRINGS = {'type': 'array', 'items': STRING}
OBJECTS = {'type': 'array', 'items': OBJECT}
HASH = {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
FALSE = {'const': False}


def surface() -> dict[str, Any]:
    return json.loads(SURFACE.read_text(encoding='utf-8'))


def resolve(name: str):
    module, symbol = name.rsplit('.', 1)
    return getattr(importlib.import_module('ai_orchestrator.' + module), symbol)


def obj(properties: dict, required: list[str] | None = None, *, extra=False) -> dict:
    return {'type': 'object', 'properties': copy.deepcopy(properties),
            'required': list(properties) if required is None else required,
            'additionalProperties': extra}


def model_output(name: str, *, extra: dict | None = None, required=()) -> dict:
    """Inline local definitions so independently composed schemas have no ref capture."""
    raw = resolve(name).model_json_schema(mode='serialization')
    definitions = raw.get('$defs', {})

    def expand(value, stack=()):
        if isinstance(value, list):
            return [expand(item, stack) for item in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            ref = value['$ref']; key = ref.removeprefix('#/$defs/')
            if key not in definitions or key in stack:
                raise ValueError('public response schema needs reviewed recursive/external ref handling')
            return {**expand(definitions[key], (*stack, key)),
                    **{k: expand(v, stack) for k, v in value.items() if k != '$ref'}}
        return {k: expand(v, stack) for k,v in value.items() if k != '$defs'}
    result = expand(raw)
    result.setdefault('properties', {}).update(copy.deepcopy(extra or {}))
    result['required'] = sorted(set(result.get('required', [])) | set(required))
    return result


def tool_annotations(name: str, readonly: bool) -> dict[str, bool]:
    return {'readOnlyHint': readonly,
            'destructiveHint': name in ('cancel_job', 'request_execution', 'request_provider_change',
                                       'request_provider_change_set', 'request_binding_cleanup', 'request_provider_permission'),
            'idempotentHint': True,
            'openWorldHint': name in ('explore', 'propose_from_exploration', 'propose_task', 'run_task',
                                     'request_start', 'request_execution', 'request_provider_permission')}


def output_schemas() -> dict[str, dict]:
    cancellation = model_output('cancellation.CancellationView')
    task = model_output('models.TaskState', extra={'approval_scope':HASH})
    task_view = model_output('models.TaskState', extra={
        'approval_scope':HASH, 'cancellation':cancellation, 'usage':OBJECT,
        'budget':OBJECT, 'recovery':OBJECT}, required=('cancellation','usage','budget'))
    cli_task = model_output('models.TaskState', extra={
        'approval_scope':HASH, 'cancellation':cancellation, 'recovery':OBJECT}, required=('cancellation',))
    job = model_output('jobs.Job', extra={'poll_after_seconds':INTEGER, 'worker':OBJECT,
                                         'wait_timed_out':BOOL, 'waited_seconds':INTEGER})
    gate = obj({
        'gate_id':STRING, 'kind':{'enum':['start','execution','acceptance','profile_change','profile_change_set','binding_cleanup','provider_permission']},
        'subject':STRING, 'gate_status':{'enum':['pending','applying','applied','declined','cancelled','expired','stale','failed','uncertain']},
        'scope':STRING, 'assurance':STRING, 'result':NULLABLE_OBJECT, 'error':NULLABLE_STRING,
        'transport_diagnostics':NULLABLE_OBJECT,
        'durability':obj({'effect_state':{'enum':['uncertain','not_marked_uncertain']},
                         'automatic_replay':FALSE, 'request_reuse_allowed':{'enum':[False,None]},
                         'operator_action':NULLABLE_STRING})})
    gate_stale = obj({'gate_id':STRING,'gate_status':{'const':'stale'},'result':{'type':'null'},'error':STRING})
    intake = model_output('contracts.IntakeState', extra={'intake_scope':HASH})
    exploration = model_output('exploration.ExplorationState', extra={
        'usage_evidence':OBJECT, 'budget':OBJECT, 'in_flight_or_interrupted':BOOL,
        'interruption_policy':STRING,'authority':STRING},
        required=('usage_evidence','budget','in_flight_or_interrupted','interruption_policy','authority'))
    coverage = {'anyOf':[{'type':'null'},obj({
        'retained_evidence_refs':INTEGER,'total_evidence_refs':INTEGER,'evidence_refs_truncated':BOOL,
        'retained_task_ids':INTEGER,'total_task_ids':INTEGER,'task_ids_truncated':BOOL,
        'retained_validation_artifact_refs':INTEGER,'corroborating_validations':INTEGER,
        'retained_review_artifact_refs':INTEGER,'corroborating_reviews':INTEGER,'note':STRING})]}
    proposal = model_output('models.Proposal', extra={'scope':HASH})
    candidate = model_output('models.Proposal', extra={'scope':HASH,'evidence_coverage':coverage,'authority':STRING},
                             required=('scope','evidence_coverage','authority'))
    inspect_properties = {
        'project':STRING,'name':STRING,'profile_digest':HASH,'trusted':BOOL,'roles':OBJECT,
        'capabilities':OBJECT,'provider_plugins':OBJECT,'provider_compatibility':OBJECT,'runtime_options':OBJECT,
        'usage_observability':OBJECT,'budget_policy':OBJECT,'project_learning':OBJECT,'exploration_sessions':OBJECT,
        'installation':OBJECT,'operational_hardening':OBJECT,'recovery_durability':OBJECT,
        'persistence_compatibility':OBJECT,'workflow':OBJECT,'workflows':OBJECT,'adaptive_orchestration':OBJECT,
        'authority_control':OBJECT,'validators':OBJECT,'execution':STRING,'operator_only':STRINGS,
        'human_gate_authority':STRINGS,'operator_only_note':STRING,
        'host_confirmation':OBJECT,'worker':OBJECT}
    inspect_project = {'anyOf':[obj(inspect_properties, [k for k in inspect_properties if k not in ('host_confirmation','worker')]),
        obj({'schema_version':{'const':1},'project':STRING,'blocked':{'const':True},'installation':OBJECT,
             'maintenance':OBJECT,'agent_can_restore':FALSE,'agent_can_cleanup':FALSE,'automatic_replay':FALSE,
             'execution':STRING,'host_confirmation':OBJECT,'worker':OBJECT},
            ['schema_version','project','blocked','installation','maintenance','agent_can_restore','agent_can_cleanup','automatic_replay'])]}
    change_properties = {'change_id':STRING,'change_set':OBJECT,'changes':OBJECTS,'resolution_after':OBJECT,
                         'ready':BOOL,'blocked_by':obj({'task_ids':STRINGS,'intake_ids':STRINGS}),
                         'trust_effect':STRING,'task_effect':STRING}
    generic_error = obj({'error':STRING, 'schema_version':INTEGER, 'code':STRING,
                         'request_id':STRING,'original_job_id':STRING,'outcome':STRING,'automatic_replay':FALSE},
                        ['error'], extra=True)
    # Code-specific details remain mandatory when that machine code is present.
    generic_error['allOf'] = [{'if':{'required':['code'],'properties':{'code':{'const':'request_retired'}}},
        'then':{'required':['schema_version','request_id','original_job_id','outcome','automatic_replay'],
                'properties':{'schema_version':{'const':1},'outcome':{'enum':['succeeded','failed','cancelled','interrupted']}}}}]
    return {
        'task':task, 'task_view':task_view, 'cli_task_view':cli_task, 'job':job,
        'wait_job':{'anyOf':[job,obj({'job_id':STRING,'wait_cancelled':{'const':True},'note':STRING})]},
        'intake':intake,'gate':{'anyOf':[gate,gate_stale]},'exploration':exploration,
        'exploration_state':model_output('exploration.ExplorationState'),
        'artifact':obj({'task_id':STRING,'kind':STRING,'content':{},'trust':STRING}),
        'exploration_artifact':obj({'content':{},'authority':STRING}),
        'explorations':obj({'schema_version':{'const':1},'total':INTEGER,'truncated':BOOL,
                           'sessions':{'type':'array','items':obj({'id':STRING,'revision':INTEGER,'status':STRING,
                             'latest_intake_id':NULLABLE_STRING,'task_id':NULLABLE_STRING})},'authority':STRING}),
        'proposal':proposal,'candidate':candidate,
        'candidates':obj({'schema_version':{'const':1},'total':INTEGER,'truncated':BOOL,'candidates':{'type':'array','items':obj({
            'id':STRING,'kind':STRING,'status':STRING,'statement_type':STRING,'statement':STRING,
            'support':NULLABLE_OBJECT,'evidence_coverage':coverage,'canonical_key':NULLABLE_STRING,
            'supersedes':STRINGS,'contradictions':STRINGS,'scope':HASH})},'authority':STRING}),
        'context':obj({'schema_version':{'const':1},'manifest':model_output('models.ContextInfluence'),
                       'selected_paths':STRINGS,'authority':STRING}, ['manifest','selected_paths','authority']),
        'inspect_project':inspect_project,
        'provider_change':obj({**change_properties,'change':OBJECT}),
        'provider_change_set':obj(change_properties),
        'binding_cleanup':obj({'cleanup_id':STRING,'task_ids':STRINGS,'intake_ids':STRINGS,'tasks':OBJECTS,
                              'intakes':OBJECTS,'scope':HASH,'effect':STRING,'workspace_rollback':FALSE}),
        'error':generic_error,
        'rpc_error':obj({'jsonrpc':{'const':'2.0'},'id':{'type':['string','integer','null']},
                         'error':obj({'code':{'enum':[-32700,-32600,-32601,-32602,-32603]},'message':STRING})}),
        # Operator reports have explicitly named top-level requirements. Opaque
        # maps remain open where the underlying report is a versioned extension.
        'identity':obj({'schema_version':{'const':1},'package_version':STRING,'loaded_build':HASH,
            'disk_build':{'anyOf':[HASH,{'type':'null'}]},'matches':BOOL,'process_started_at':NUMBER,'process_id':INTEGER,
            'skill_sha256':{'anyOf':[HASH,{'type':'null'}]},'contract_inventory_sha256':{'anyOf':[HASH,{'type':'null'}]},
            'host_skills_checked':BOOL,'host_skills':OBJECTS}),
        'contracts':obj({'schema_version':{'const':2},'package_version':STRING,'target_version':STRING,
                          'canonicalizer':STRING,'inventory_digest':HASH},extra=True),
        'init':obj({'project':STRING,'initialized':{'const':True},'trusted':FALSE}),
        'skill':obj({'path':STRING,'backup':NULLABLE_STRING,'installed_into_client':FALSE}),
        'schema':{'anyOf':[obj({'path':STRING}),obj({'type':STRING,'properties':OBJECT},['type'],extra=True)]},
        'events':{'type':'array','items':obj({'schema_version':{'const':1},'event_id':STRING,'source':{'const':'runtime_event_log'},'sequence':INTEGER,'task_id':NULLABLE_STRING,'kind':STRING,
                                           'payload':OBJECT,'created_at':STRING})},
        'cancel':{'anyOf':[obj({'task_id':STRING,'cancellation_requested':{'const':True},'cancellation':cancellation}),
                    obj({'task_id':STRING,'status':{'const':'cancelled'},'already_finalized':BOOL,
                         'automatic_replay':FALSE,'cancellation':cancellation},
                        ['task_id','status','already_finalized','automatic_replay'])]},
        'diagnostics':{'type':'object','additionalProperties':{'type':'object'}},
        'capabilities':obj({'registry':model_output('capabilities.CapabilityRegistryDescriptor'),'providers':OBJECT,'roles':OBJECT,'provider_compatibility':OBJECT,'review_independence':STRING}),
        'persistence':obj({'schema_version':INTEGER,'contracts':OBJECT,'databases':OBJECT},['schema_version','contracts','databases'],extra=True),
        **operator_schemas(),
        'worker':obj({'processed':INTEGER,'interrupted_jobs':INTEGER,'job':NULLABLE_OBJECT,'stopped':BOOL,'idle_exit':BOOL},['processed','interrupted_jobs']),
        'serve':{'description':'stdio JSON-RPC stream; no dispatch JSON result', 'type':'null'},
    }


SDK_EXPORTS = (
    'provider_sdk.RunRequest', 'provider_sdk.ProviderAdapter', 'provider_sdk.ProviderExecutionError',
    'provider_sdk.RuntimeOptionsDescriptor', 'provider_sdk.UsageDescriptor',
    'provider_sdk.assert_provider_adapter_conforms', 'provider_sdk.normalize_provider_failure_diagnostics',
    'models.Contract', 'models.ProviderConfig',
)


def _annotation(value):
    if value is inspect.Parameter.empty:
        return None
    if isinstance(value,str):
        return value
    from .contract_inventory import _symbol
    return _symbol(value)


def _default(value):
    from .contract_inventory import _symbol, _json_value
    if value is inspect.Parameter.empty or value is dataclasses.MISSING:
        return {'required':True}
    if inspect.isclass(value) or inspect.isfunction(value):
        return {'symbol':_symbol(value)}
    if isinstance(value,(set,frozenset,tuple)):
        return {'collection':type(value).__name__,'items':sorted(value)}
    return _json_value(value)


def signature(function) -> dict:
    value=inspect.signature(function)
    return {'parameters':[{'name':p.name,'kind':p.kind.name,'annotation':_annotation(p.annotation),
                            'default':_default(p.default)} for p in value.parameters.values()],
            'returns':_annotation(value.return_annotation)}


def sdk_contracts() -> dict:
    from . import provider_sdk
    from .contract_inventory import _symbol, digest, schema_semantics
    entries=[]
    for name in SDK_EXPORTS:
        value=resolve(name); record={'import': 'ai_orchestrator.'+name}
        if dataclasses.is_dataclass(value):
            record.update(kind='dataclass',frozen=value.__dataclass_params__.frozen,
                fields=[{'name':f.name,'annotation':_annotation(f.type),'init':f.init,'kw_only':f.kw_only,
                         'default':_default(f.default),
                         'default_factory':None if f.default_factory is dataclasses.MISSING else _symbol(f.default_factory)}
                        for f in dataclasses.fields(value)])
        elif hasattr(value,'model_json_schema'):
            record.update(kind='data-model',schema_sha256=digest(schema_semantics(value.model_json_schema())))
        elif name.endswith('ProviderAdapter'):
            record.update(kind='protocol', attributes=dict(value.__annotations__),
                          methods={method:signature(getattr(value,method)) for method in ('doctor','execute')})
        else:
            record.update(kind='exception' if inspect.isclass(value) else 'function',
                          signature=signature(value.__init__ if inspect.isclass(value) else value))
        entries.append(record)
    return {'sdk_version':provider_sdk.PROVIDER_SDK_VERSION,
            'adapter_api_versions':sorted(provider_sdk.SUPPORTED_EXTERNAL_ADAPTER_API_VERSIONS),
            'entry_point_group':provider_sdk.PROVIDER_PLUGIN_ENTRYPOINT_GROUP,
            'failure_categories':sorted(provider_sdk.PROVIDER_FAILURE_CATEGORIES),
            'exports':entries,
            'optional_methods':{
                'describe_runtime_options':{'parameters':['config','workspace'],'returns':'runtime_options.RuntimeOptionsDescriptor'},
                'describe_usage':{'parameters':['config','workspace'],'returns':'usage.UsageDescriptor'},
                'role_compatibility':{'parameters':['role'],'returns':'dict[str, object]'}},
            'execute_returns':'an instance of request.result_model; controller validates before use',
            'plugin_authority':'installed metadata is not activation; exact trusted project pin is required',
            'negative_tests':['tests/test_v013_provider_sdk.py','tests/test_v1_public_contracts.py']}


def operator_schemas() -> dict[str, dict]:
    """Operation-specific operator responses; dynamic maps are explicitly typed."""
    workflow = {'schema_version':INTEGER,'id':STRING,'digest':HASH,'order':STRINGS,
                'repair_on':NULLABLE_STRING,'repair_from':NULLABLE_STRING,'template_version':INTEGER,
                'provenance':NULLABLE_OBJECT,'nodes':{'type':'array','items':model_output('models.WorkflowNodeSpec')},
                'artifacts':OBJECT,'source':STRING,'is_default':BOOL}
    template = {'schema_version':INTEGER,'intake_id':STRING,'task_id':STRING,'task_status':STRING,
                'reviewed_snapshot':HASH,'source_workflow_id':STRING,'source_workflow_digest':HASH,
                'template_id':STRING,'template_version':INTEGER,'template_digest':HASH,
                'parent_template_digest':NULLABLE_STRING,'replace':BOOL,'profile_digest':HASH,
                'workflow':model_output('models.WorkflowSpec'),'authority_change':STRING}
    backup = {'path':STRING,'mode':{'enum':['full','runtime']},'scope':HASH,'manifest':OBJECT}
    return {
        'backup_create':obj({**backup,'authority':STRING}),
        'backup_inspect':obj({**backup,'verified':{'const':True}}),
        'restore':obj({'restored':{'const':True},'mode':STRING,'scope':HASH,'current_profile_digest':HASH,
            'source_profile_digest':HASH,'profile_matches_backup':BOOL,'restored_trusted_profile':NULLABLE_STRING,
            'current_profile_trusted':BOOL,'retrust_required':BOOL,'maintenance_event':OBJECT,
            'request_receipt_coverage':OBJECT,'automatic_replay':FALSE}),
        'retention':obj({'schema_version':INTEGER,'cutoff':STRING,'evidence_inventory_sha256':HASH,
            'worktrees':STRINGS,'worktree_markers':OBJECT,'terminal_jobs':STRINGS,'terminal_job_sha256':OBJECT,
            'orphan_artifacts':STRINGS,'orphan_artifact_sha256':OBJECT,'protected_evidence_ids':INTEGER,
            'legacy_untyped_learning_evidence':BOOL,'policy':OBJECT,'scope':HASH,'authority':STRING}),
        'cleanup':obj({'scope':HASH,'cutoff':STRING,'worktrees_removed':STRINGS,'terminal_jobs_removed':INTEGER,
            'orphan_artifacts_removed':STRINGS,'maintenance_event':OBJECT,'automatic_repair':FALSE}),
        'maintenance_inspect':obj({'schema_version':{'const':1},'ok':BOOL,'pending':BOOL,'valid':BOOL,
            'reconciliation_scope':NULLABLE_STRING,'automatic_repair':FALSE,'reconcilable':BOOL,
            'operation_id':STRING,'action':STRING,'phase':STRING,'before_matches':BOOL,'after_matches':BOOL,'error':STRING},
            ['schema_version','ok','pending','reconciliation_scope','automatic_repair']),
        'maintenance_reconcile':{'anyOf':[obj({'schema_version':{'const':1},'reconciled':{'const':False},'already_clear':{'const':True}}),
            obj({'schema_version':{'const':1},'reconciled':{'const':True},'maintenance_event':OBJECT,'automatic_replay':FALSE})]},
        'promote':model_output('models.Proposal',extra={'profile_retrust_required':{'const':True}},required=('profile_retrust_required',)),
        'learning_report':obj({'schema_version':INTEGER,'distillation_version':INTEGER,'context_selector_version':INTEGER,
            'selection_budget_bytes':INTEGER,'accepted_context_universe':OBJECT,'candidates':OBJECT,'durable_evidence':OBJECT,'governance':OBJECT}),
        'learning_distill':obj({'schema_version':INTEGER,'distillation_version':INTEGER,'task_count':INTEGER,'event_count':INTEGER,
            'artifact_counts':OBJECT,'candidate_patterns':INTEGER,'created':STRINGS,'retained':STRINGS,'rejected_suppressed':STRINGS,'authority':STRING}),
        'provider_plugins':obj({'schema_version':INTEGER,'provider_sdk_version':INTEGER,'entry_point_group':STRING,
            'profile_trusted':BOOL,'configured':OBJECT,'installed_entry_points':OBJECTS,'metadata_errors':OBJECTS,
            'activation_policy':STRING,'trust_boundary':STRING}),
        'trust':obj({'trusted_profile':HASH,'execution':{'const':'local-trusted'},'actor':STRING}),
        'validator_add':obj({'validator':STRING,'ok':BOOL,'executable':STRING,'argv':STRINGS,'generated_paths':STRINGS,
            'warnings':STRINGS,'execution':STRING,'profile_retrust_required':{'const':True}}),
        'validator_check':obj({'ok':BOOL,'check':OBJECT,'artifact':model_output('models.Artifact')}),
        'workflow':obj(workflow),
        'workflows':obj({'schema_version':INTEGER,'default':STRING,'workflows':OBJECT}),
        'workflow_candidate':obj({**template,'scope':HASH}),
        'workflow_save':obj({**template,'saved_by':STRING,'previous_profile_digest':HASH,'new_profile_digest':HASH,'profile_retrust_required':BOOL}),
    }
