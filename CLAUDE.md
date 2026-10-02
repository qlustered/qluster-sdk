# qluster-sdk

Holds `Rule`, `RuleMetadata`, `RuleResult`, `Issue` and `RowProxy`. A uv
workspace member tracked by this repo, so an SDK change and its atlas
consumers ship together and the editable install picks it up.
`/home/erasmose/Workspace/qluster/qluster-sdk` is a separate, stale checkout:
do not edit or diff against it unless the task is publishing that repo, and
then treat atlas as the newer side.

```bash
cd qluster-sdk && pytest --timeout=60 tests
```

- `RuleMetadata` declares no `model_config`, so unknown keys are ignored: a
  new field needs no tolerant reader and the pod keeps loading stored
  revisions. `static_metadata_errors`
  (`cettings/cettings/controllers/rule_controller/rule_controller_core.py`)
  rejects an unknown keyword at submit instead, so a retired field needs no
  class-level forbid. `RuleSlicer._extract_metadata`
  (`common/common/static_analysis/rule_slicer.py`) reduces every keyword it can
  and names the rest, and `RuleController.load_rules` builds a `RuleMetadata`
  from the reduced dict, answering 422 with one entry per problem, each naming
  its rule class. So a new field needs no analyzer change, and a new enum-typed
  field is read off the model's own annotations (`METADATA_ENUM_CLASSES`) — but
  a new validator rejects rule files that submitted cleanly before.
- The package is baked into the WASI infrastructure archive; an edit here
  shifts its digest (`wasi/CLAUDE.md`, Editing the guest).
- `EnumStrBase` reprs as the bare value, so a failed `is` between a member and
  a string prints `assert 'x' is 'x'`.
- `tests/` ships in the public SDK repo (`make gitpush-sdk`), so an SDK test
  imports no backend module (`common`, `cettings`, ...). A check that needs the
  backend lives in the backend's tests: the README Quick Start runs in
  `tests/test_readme.py` and goes through preflight and `static_metadata_errors`
  in `cettings/tests/test_rules/test_rule_fixture_corpus_preflight.py`.
