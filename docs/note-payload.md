# Note payload and model mapper (#25)

This library parses one generated note, sanitizes its fields and returns an
**unsaved** Anki note with a revalidated numeric deck target. It is not wired to
Tools, generation, review, approval, insertion or acknowledgements. It does not
implement #24/#26/#27/#28/#29/#30 or image occlusion workflows. Squad is not a
runtime dependency.

## Proposed wire contract: version 1

Backend generation should consume this exact proposal only after parent/lead
acceptance. It is not an existing HTTP endpoint or result-envelope schema.
One JSON object has exactly these properties (synthetic example):

```json
{
  "schema_version": 1,
  "model_family": "basic",
  "import_id": "11111111-1111-4111-8111-111111111111",
  "fields": {"Front": "<b>What is the basic unit of life?</b>", "Back": "A cell."},
  "source": {
    "document_id": "22222222-2222-4222-8222-222222222222",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "name": "Synthetic.txt",
    "location": {"page": 2, "slide": null, "section": "Chapter 1"}
  },
  "prompt_version": "synthetic-v1",
  "model_version": "synthetic-model-v1"
}
```

| Property | Exact validation |
| --- | --- |
| `schema_version` | Integer `1`, not a string, float or boolean; other versions fail |
| `model_family` | Exact `basic`, `reversed` or `cloze`; no aliases/localized built-in names |
| `fields` | Basic/reversed: exactly `Front`, `Back`; cloze: exactly `Text`, `Back Extra` |
| Field values | Strings, at most 32,768 Unicode characters each; visible non-whitespace text required except `Back Extra` may be empty |
| `import_id`, `source.document_id` | Canonical lowercase hyphenated UUID strings |
| `source.sha256` | Exactly 64 lowercase hexadecimal characters; mapper validates shape, not the original bytes/hash algorithm |
| `source.name` | Non-whitespace string, at most 255 characters; plain display metadata, never a path/URL to open |
| `source.location` | Exactly `page`, `slide`, `section`, all required; page/slide are `null` or integers 1 through 2,147,483,647, never booleans; section is `null` or a non-whitespace string of at most 255 characters |
| `prompt_version`, `model_version` | Trusted producer version labels matching `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, not prompt text, credentials or endpoint URLs |

Unknown/missing properties at every object level fail; no defaulting, truncation
or string/number coercion. Names/sections reject C0/C1 controls; content fields
allow tab/newline/carriage return, but reject other controls and lone surrogates.
All-null location denotes document-level attribution. A producer may supply both
page and slide when meaningful. Location quality/content correctness remains
the extraction/validation pipeline's responsibility.

`parse_generated_note(object)` returns immutable `GeneratedNote`, `Source` and
`BasicFields`/`ClozeFields` dataclasses with content-free representations.
The mapping entry point always parses the wire object itself, so direct
construction of an unchecked dataclass cannot bypass validation.

## Markup policy

Generated fields accept only balanced HTML using:
`b strong i em u s sub sup p div span br ul ol li pre code blockquote table
thead tbody tr th td`. Names are canonicalized to lowercase, `br` is void, and
**all attributes are removed**, including events, styles, links and hidden state.
Text/entities are decoded then escaped into inert HTML; no URLs or media are
loaded. Maximum input is 32,768 characters and maximum nesting is 32 elements.

Unknown elements (including script/style/svg/math/img/iframe/object/a/form),
comments, declarations, processing instructions and mismatched/unclosed tags
fail explicitly. This is a deliberately limited format, not a general HTML
cleaner or media pipeline. Anki `[sound:...]`, `[latex]`, `[$]` and `[$$]` syntax
is also rejected, including entity-encoded or tag-split variants, so generated
text cannot trigger local media or external LaTeX processing.

Cloze `Text` must contain one or more `{{cN::deletion}}` or
`{{cN::deletion::hint}}` tokens, N=1..99 without leading zeros. Repeated numbers,
multiple numbers in separate tokens, multiline text and balanced inline HTML
inside deletions/hints are preserved. Deletions/hints must have visible text.
Nested deletions, comma-group ordinals, extra `::`, missing delimiters and tokens
crossing element boundaries fail; entity-encoded delimiters are validated after
decoding. Basic/Back/Back Extra fields cannot contain double-brace tokens.
Anki supports additional cloze forms; this version intentionally accepts only
this documented subset. Note/card counting and pedagogical validation belong to
later issues; a mapped cloze/reversed note does not imply one rendered card.

## Managed models and persistent fields

Built-in and arbitrary user note models are never edited or selected by their
localized names. The mapper uses these separate names:

| Family | Exact model name | Primary fields | Kind/templates |
| --- | --- | --- | --- |
| `basic` | `Anki AI Deck Generator::basic::v1` | `Front`, `Back` | Normal, one forward template |
| `reversed` | `Anki AI Deck Generator::reversed::v1` | `Front`, `Back` | Normal, forward and reverse templates |
| `cloze` | `Anki AI Deck Generator::cloze::v1` | `Text`, `Back Extra` | Cloze kind, one `cloze:Text` template |

Each appends exactly these fields in this order:

| Field | Stored value |
| --- | --- |
| `Source` | Escaped name and available `page: N`, `slide: N`, `section: value`, joined by `; `; shown on answer faces |
| `Import ID` | Unchanged canonical generated import UUID; not displayed by templates |
| `Payload Version` | Literal text `1`; not displayed |
| `Provenance` | Escaped canonical JSON (`ensure_ascii=True`, sorted keys, compact separators) containing exactly `model_family`, `model_version`, `prompt_version`, `source`; source has the original wire shape including nested `location` |

Metadata escapes HTML plus square-bracket and brace delimiters,
keeping Anki media/LaTeX/cloze syntax literal even in source names and JSON.
To decode stored provenance, HTML-unescape once then parse JSON; never display
that decoded JSON as raw HTML.

Existing managed models must match field order/ordinals, kind, sort field, CSS
and exact template names/question/answer formats. Nonempty browser formats or
template deck overrides also fail. Customized/incompatible managed models cause
`model_fields` or `model_collision`, without overwriting them, silently changing
the name, or choosing a built-in fallback. Preserve the model and ask the user to
resolve the conflict; this slice provides no automatic migration/repair.

The producer must assign and persist one import UUID per generated note before
result publication. Retries and review edits retain that UUID. It identifies a
**note**, including all reverse/cloze cards, not a rendered card or concept hash.
It matches the backend's canonical import UUID shape but does not authorize
access, compute hashes or implement duplicate skipping. Future #24 must inspect
the stored `Import ID` under the originating collection/deck context immediately
before approved insertion, and acknowledge the same UUID only after Anki commit.
Deleting/editing that field or changing note models can invalidate retry safety;
do not promise protection against arbitrary user edits.

These fields become persistent only when later approved insertion commits them.
There is no side database/cache, note insertion, save/flush or backend
acknowledgement here. Local imported note content/provenance remains with the
user's collection; cloud expiry must not delete it or the user's local originals.

## Supported API and caller boundary

`map_generated_note(collection, wire_object, captured_deck, create_model=False)`
returns `MappedNote(note, deck, model_changes)`. The numeric deck snapshot
contract from [#3](deck-selector.md) is unchanged. The returned deck keeps its ID
and updated display name, or fails for deleted/filtered/unselected targets.
No resolution by name/default and no deck override on templates is allowed.

Call only inside the originating profile's serialized collection operation,
with cancellation/profile-lifetime checks supplied by the future caller.
Payload/markup validation occurs before collection access/model changes.
Creation is disabled by default; only explicit boolean `create_model=True`
permits creating the one required managed model. That write must be an explicit
user-directed setup/approved operation, not a reaction to downloaded results.
The caller must preserve/use the returned Anki changes result for operation/UI
notifications and undo coordination. Model creation is a real collection write
and can persist even if later mapping/insertion fails; do not claim rollback.

The implementation uses public `models.by_name`, `new`, `new_field`, `add_field`,
`new_template`, `add_template`, `add_dict`, `get`, `Collection.new_note` and
`Note.__setitem__`. `add_dict` is preferred over deprecated `add`; the saved model
is fetched again to obtain normalized field/template ordinals. No SQL, private
collection internals or existing model update API is used. Serialized execution
is essential: Anki's add API may rename a concurrent name collision. A changed
post-add name fails visibly but cannot undo that write automatically.

`NoteMappingError` supplies a fixed content-free `code`/message and, when known,
a fixed field path; `DeckError` keeps the existing deck errors. Unexpected Anki
API/storage exceptions propagate to the caller's privacy-safe failure boundary;
they are not converted to success or logged here. Future UI must display the
safe expected error and use existing content-free diagnostics for unexpected
failures, never raw exception/payload text.

APIs inspected on **both Anki 25.09 and 26.09.4, Qt6 desktop**, 2026-11-21 UTC:
[25.09 models](https://github.com/ankitects/anki/blob/25.09/pylib/anki/models.py),
[26.09.4 models](https://github.com/ankitects/anki/blob/26.09.4/pylib/anki/models.py),
[25.09 collection](https://github.com/ankitects/anki/blob/25.09/pylib/anki/collection.py),
[26.09.4 collection](https://github.com/ankitects/anki/blob/26.09.4/pylib/anki/collection.py),
[26.09.4 cloze](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/cloze.rs),
[26.09.4 LaTeX](https://github.com/ankitects/anki/blob/26.09.4/pylib/anki/latex.py).

## Evidence and open gates

```sh
cd addon/tests
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_note_models test_markup -v
cd ../..
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s addon/tests -q
```

Synthetic tests inspect exact unsaved field/model/template artifacts, malformed
versions/shapes/IDs/metadata, size boundaries, executable HTML and Anki syntax,
cloze edge cases, customized built-ins/managed collisions, explicit creation,
deck rename/deletion/filtering and propagated collection outages. Source
mutations prove persistent identity, attribute removal and model protection
assertions fail for regressions. A copied supported-model API double demonstrates
identity retention across mapper recreation, **not real disk persistence**.

Actual Anki collection writes/undo, Qt responsiveness, saved question/answer and
browser rendering after restart on both targets/platforms remain **unverified**.
No disposable desktop profile was provided or used, and no saved notes were
inserted. Backend producer contract acceptance/consumption, review approval,
import identity lookup/revalidation/commit/partial-retry and acknowledgement,
source metadata UI, media and image occlusion integration remain separate gates.
Existing real OS credential/provider/Azure evidence gaps are unchanged.
