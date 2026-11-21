# Foundation dependency remediation

Owner: lead; directly coupled follow-up to the #6 foundation manifests.

The live forge inventory contained 33 manifest-specific alert rows across
PyJWT and pytest, representing 17 distinct advisories. Runtime/dev manifests
duplicate the PyJWT alerts; no count of exploitable application flaws is inferred.

Reviewed and merged existing PR #51 as `6492968`, upgrading PyJWT to 2.15.0.
Upgrade the directly pinned development runner to pytest 9.0.3 for
GHSA-6w46-j5rx-g56g. Current main plus the reviewed #18 component and both
patched pins passed 192 backend tests with six existing Linux-only PDF skips;
dependency consistency also passed. No auth-policy change, provider/cloud
certification, deployment or service activation is implied.
