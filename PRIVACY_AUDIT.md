# Public release privacy audit

BloxBinds 1.2.0 public developer identity: **wirru**.

Scope: the allowlisted source bundle, release ZIP members, Windows version metadata, unpacked PyInstaller code and data, and inspectable Git identity/history. The final automated scan is required before packaging; results are recorded in TEST_RESULTS.md.

The repository had no commits when inspected, so no identifying Git history required rewriting. An inherited personal author name/email was found in local Git configuration. This project's local author name is now wirru, its email is deliberately empty, and user.useConfigOnly is enabled. A local pre-commit hook checks both author and committer identity and blocks commits until the owner supplies their **actual GitHub-provided noreply email**. The hook lives only in this working repository, not in release bundles; new clones must configure their own Git identity. None was invented. Global Git configuration and other repositories were not changed.

Public bundles omit .git, local settings/calibration, virtual environments, build diagnostics, test caches, previous executables/archives and backups. Local development/build directories can contain machine-specific paths; never publish them. The executable's own version strings use wirru and relative Python code filenames are checked. PE/archive timestamps use a neutral fixed date.

**Remaining upstream metadata:** this build's bundled Python/native runtime libraries retain 59 account-directory build/debug references from their upstream compiler environment. They did not match the local developer name, email, Windows account or computer name scanned here. Standard-library documentation also contains generic example account paths. These are explicitly reported rather than claimed absent. Upstream runtime binaries are kept unchanged for reliability; a stricter requirement to remove every vendor build path would require a separately vetted runtime build. No local BloxBinds workspace paths or developer identifiers were found in the inspected executable contents. Upstream Python/Tcl/Tk legal notices identify their respective copyright owners; these are not BloxBinds developer identities.

No publication or Git history rewriting is performed. Review GitHub account visibility, future commit authorship, signing metadata, screenshots, and manually added release files before publication. Static inspection cannot guarantee anonymity or detect every possible secret or indirect identifier.
