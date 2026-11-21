# Parser test dependency remediation

Owner: lead; directly coupled follow-up to merged PDF issue #9.

After the runtime PyJWT remediation, the live forge separately indexed the
standalone extraction test manifest. Its old pytest/cryptography pins must not
remain vulnerable merely because the root test environment resolves newer
versions.

Align that manifest with pytest 9.0.3 and cryptography 50.0.2. The combined
backend/text candidate already passed 221 tests with six existing Linux-only
skips using those exact installed versions; preserve genuine AES/encryption
fixtures and the pinned pypdf rejection hook. Runtime PDF dependencies and
decryption behavior do not change. Supersede redundant dependency PRs only
after this combined manifest update is reviewed and merged.
