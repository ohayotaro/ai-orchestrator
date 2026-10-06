"""Export complete schemas for the versioned public inventory; provider-free."""
from __future__ import annotations
import json
from ai_orchestrator.public_contracts import surface, resolve, output_schemas
from ai_orchestrator.service import TOOLS
from ai_orchestrator.human_gates import GATE_TOOLS


def export() -> dict:
    return {'schema_version':1,
            'models':{name:resolve(name).model_json_schema() for name in surface()['models']},
            'mcp_inputs':{name:entry[0].model_json_schema() for name,entry in sorted({**TOOLS,**GATE_TOOLS}.items())},
            'outputs':output_schemas()}


if __name__=='__main__':
    print(json.dumps(export(),ensure_ascii=False,sort_keys=True,indent=2))
