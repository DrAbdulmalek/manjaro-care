# Read-Only Diagnostics and Feedback Roadmap

**Status:** Proposal only. No system repair, cleanup, or automatic action is authorized.

## Product principles

Preserve Manjaro Care's established workflow:

1. **Scan:** read-only diagnostics.
2. **Preview:** display exact commands and expected effects.
3. **Apply:** only after explicit user confirmation.

Any feedback or AI integration must preserve this contract. The diagnostic layer must not gain implicit repair privileges.

## Proposed feedback events

- diagnostic identifier and version;
- sanitized system category (not serial numbers or personal paths);
- observed state and expected state;
- evidence source (command and exit status, with sensitive output redacted);
- severity and confidence;
- reproducibility notes;
- user decision: accepted, rejected, corrected, or deferred.

## AI-assisted analysis

AI may summarize diagnostics, cluster duplicates, explain likely causes, and propose a remediation plan. It must not:
- execute commands;
- modify bootloader, partitions, filesystems, packages, network settings, or services;
- delete logs or snapshots;
- elevate privileges;
- convert a suggestion into an automatic repair.

Any future Apply integration remains within the existing preview-and-confirmation mechanism and requires a separate safety review.

## Privacy

- redact usernames, hostnames, IP/MAC addresses, serial numbers, mount paths, and tokens from exported reports;
- do not upload raw journal logs or full command output automatically;
- no cloud fallback;
- local-only analysis by default;
- allow the user to inspect the final report before export.

## Acceptance tests

- diagnostic scan is read-only (filesystem and system-state assertions);
- AI analysis has no command-execution capability;
- redaction tests cover IPv4/IPv6, MAC, serials, usernames, home paths, and secrets;
- preview matches the exact operation that would be applied;
- dry-run blocks privileged execution even if a module attempts to bypass the UI;
- no cleanup or repair is triggered by feedback capture.

## Future integration

A shared feedback engine may receive sanitized diagnostic events, but Manjaro Care remains the authority for its own system operations and approval flow. Avoid adding a cloud reporting dependency.
