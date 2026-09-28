# STAR annotation web app

Run from the project root:

```bash
python3 web/app.py
```

Then open:

```text
http://127.0.0.1:8765
```

The first launch creates `manifests/images.json` from the current CPTAC and EAY131
`vis_check` PNG folders. The manifest order is deterministically shuffled with a
fixed project seed, so different users see the same shuffled image sequence.

Outputs:

- `users/{user_id}.json`: user type, resume state, completed image IDs.
- `answers/{user_id}.jsonl`: one autosaved answer event per submitted stage.

## MLLM benchmark

Generate the frozen MLLM benchmark definition with:

```bash
python3 web/generate_mllm_split.py
python3 web/generate_mllm_prompts.py
```

`assignments/mllm_split.json` contains all 10,565 images that sg2162 marked
`No issue` for Q4, in filtered manifest order, plus source hashes and the exact
inclusion rule. MLLM users receive only this split. Human users continue to
receive the complete manifest. The generator validates that all 3,000 unique
radiologist-assignment images are a subset of the MLLM benchmark.

`assignments/mllm_prompts.json` freezes the English Q1-Q4 wording, exact choice
order, output fields, and the Q3 choice matrix. MLLMs must answer sequentially:
their own Q1 region and Q2 lymph-node answers determine the choices and context
shown for Q3, matching the web interface. The specification also lists inputs
that must remain hidden to prevent label leakage.

The browser UI asks Q1 region, Q2 site, and an image-quality check. The old
ground-truth confirmation question was removed to avoid label leakage. Images are
served by opaque image IDs instead of GT-bearing filenames.

The UI also shows live cumulative Q1/Q2 accuracy curves based only on completed
answers saved for the current user.

## Blinded radiologist assignments

The frozen radiologist cohort contains the 10,565 images that sg2162 marked as
`No issue` for Q4. Generate five deterministic, blinded groups before registration:

```bash
python3 web/generate_radiologist_groups.py
```

The generated files are:

- `assignments/radiologist_groups.json`: immutable image membership, stratification metadata, and source provenance.
- `assignments/group_registry.json`: persistent group claims by specialist users.

Human users continue to receive the complete manifest. The original five
radiologists atomically claimed anonymous Groups A–E. Every original group contains
the same 500 Phase 1 images followed by 500 group-specific Phase 2 images, for
1,000 answers per radiologist. Phase 2 starts automatically when Phase 1 is
complete. The 3,000 unique sampled images use the frozen dataset, region, site,
and lymph-node quotas in the assignment generator. Phase 1/Phase 2 are neutral
UI labels; shared/exclusive status is not exposed. A returning user always
resumes the existing group.

## Additional radiologists: Phase 3

`python3 web/generate_radiologist_phase3.py` preserves Groups A–E and all of
their Phase 1/2 image IDs. It adds Groups F–T for new radiologists. Each new
radiologist first answers the same 500 shared Phase 1 images, then automatically
continues to a non-overlapping Phase 3 group. Groups F–S contain 500 Phase 3
images each; Group T contains the final 565. Together, the Phase 3 groups cover
all 7,565 No-issue images not already present in Phase 1 or Phase 2.
New registrations claim the first available group from F–T. Once all available
groups have been claimed, registration returns HTTP 409 with the
`no_available_group` code.

The UI does not reveal the stratification fields or show accuracy feedback to
radiologist users, preventing assignment and iterative ground-truth leakage.

Do not regenerate the frozen groups after radiologist registration begins. The
generator refuses to replace assignments while the registry contains claims.
