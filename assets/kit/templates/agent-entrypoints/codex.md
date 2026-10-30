# Harness startup bridge

First read and follow the project's root AGENTS.md, if present. Codex selects this override instead of that file, so explicitly load AGENTS.md before doing any work. Preserve its corporate rules and all applicable parent/nested instructions. This bridge adds workflow; it does not replace project policy or grant permissions.

Then read .harness/BOOTSTRAP.md and follow it automatically for the current request. If you are installing harness, continue the bootstrap now in the target project. Do not ask the user to paste a setup prompt.

Use shared Python `workflow assess/confirm` and `status TASK-ID --format terminal` commands for adaptive tasks; follow the adaptive contract in docs/HARNESS.md. FAST permits one combined workflow/plan confirmation and requires final approval after verification/review.

For eligible compact tasks follow the compact route in .harness/BOOTSTRAP.md. `run` supports this current IDE host without a nested CLI; use bound plan and final decisions.
