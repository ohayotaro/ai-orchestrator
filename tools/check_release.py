"""Read-only release evidence check; never publishes or invokes providers."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ai_orchestrator.release_evidence import ReleaseManifest, evaluate_release, read_json


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--evidence-root',type=Path,required=True)
    parser.add_argument('--qualification-only',action='store_true',help='Does not waive technical gates; omit only the final publication decision')
    args=parser.parse_args()
    try:
        value=ReleaseManifest.model_validate(read_json(args.manifest))
        report=evaluate_release(value,args.evidence_root,require_approval=not args.qualification_only)
    except (ValueError,OSError) as exc:
        report={'schema_version':1,'result':'INVALID','publication_performed':False,'error':str(exc)}
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['result']=='READY' else 1


if __name__=='__main__':raise SystemExit(main())
