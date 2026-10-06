"""Compare public surfaces against the retained reviewed baseline, not just the generated asset."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ai_orchestrator.contract_inventory import generate, ASSET

ROOT=Path(__file__).resolve().parents[1]


def differences(expected,actual,path='$') -> list[str]:
    if type(expected) is not type(actual):return [path]
    if isinstance(expected,dict):
        return [p for key in sorted(expected.keys()|actual.keys())
                for p in ([path+'.'+key] if key not in expected or key not in actual
                          else differences(expected[key],actual[key],path+'.'+key))]
    if isinstance(expected,list):
        if len(expected)!=len(actual):return [path+'.length']
        return [p for index,(left,right) in enumerate(zip(expected,actual)) for p in differences(left,right,f'{path}[{index}]')]
    return [] if expected==actual else [path]


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,default=ROOT/'tests/fixtures/v1/stable-baseline.json')
    args=parser.parse_args()
    current=generate(); packaged=json.loads(ASSET.read_text())
    baseline=json.loads(args.baseline.read_text())
    # Package identity changes do not themselves change API meaning. Schema,
    # defaults, behavior, SDK and policy are never stripped from this comparison.
    old={k:v for k,v in baseline.items() if k in current and k not in ('package_version','stability')}
    new={k:v for k,v in current.items() if k not in ('package_version','stability')}
    changes=differences(old,new)
    missing=sorted(set(baseline)-set(current)-{'package_version','stability'})
    result={'packaged_matches':packaged==current,'review_required':changes+missing}
    print(json.dumps(result,indent=2))
    return 0 if result['packaged_matches'] and not result['review_required'] else 1


if __name__=='__main__':raise SystemExit(main())
