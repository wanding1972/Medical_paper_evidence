"""Pure syntax and location algorithms. Admission policy is injected."""
import re
from evidence_check.contracts.errors import InputError
from evidence_check.contracts.models import Citation, CitationFacts, Location, Sentence, ParserFacts
from evidence_check.contracts.policy import Policy
from evidence_check.contracts.predicates import enforce


def _expand(content: str, policy: Policy) -> tuple[int, ...]:
    parts = re.split(policy.parsing.citation_separator_pattern, content)
    tokens = [tuple(n.strip() for n in part.split(policy.parsing.range_separator)) for part in parts]
    enforce(policy.limits.citation_gates, CitationFacts(
        minimum_id=None, descending_count=0, expanded_count=0, malformed_count=0,
        maximum_token_length=max(len(n) for pair in tokens for n in pair),
    ))
    try:
        bounds = [tuple(int(n) for n in pair) for pair in tokens]
    except ValueError as error:
        raise InputError("invalid_integer", "Citation contains an unparseable integer.") from error
    descending = sum(len(pair) > 1 and pair[0] > pair[-1] for pair in bounds)
    count = sum(pair[-1] - pair[0] + 1 for pair in bounds)
    enforce(policy.limits.citation_gates, CitationFacts(
        minimum_id=min(n for pair in bounds for n in pair),
        descending_count=descending, expanded_count=count, malformed_count=0, maximum_token_length=0,
    ))
    return tuple(dict.fromkeys(n for pair in bounds for n in range(pair[0], pair[-1] + 1)))


def citations(text: str, offset: int, paragraph: int, sentence: int, policy: Policy) -> tuple[Citation, ...]:
    grammar = re.compile(policy.parsing.citation_pattern)
    anchors = tuple(grammar.finditer(text))
    starts = {match.start() for match in anchors}
    numeric_starts = tuple(re.finditer(policy.parsing.numeric_bracket_pattern, text))
    malformed = sum(match.start() not in starts for match in numeric_starts)
    enforce(policy.limits.citation_gates, CitationFacts(
        minimum_id=None, descending_count=0, expanded_count=0, malformed_count=malformed, maximum_token_length=0,
    ))
    return tuple(Citation(
        reference_ids=_expand(match.group(1), policy),
        location=Location(paragraph_index=paragraph, sentence_index=sentence,
                          char_start=offset + match.start(), char_end=offset + match.end()),
    ) for match in anchors)


def parse_sentences(text: str, policy: Policy) -> tuple[Sentence, ...]:
    result = []
    offset = 0
    separator = policy.parsing.paragraph_separator
    for paragraph_index, paragraph in enumerate(text.split(separator)):
        for sentence_index, match in enumerate(re.finditer(policy.parsing.sentence_pattern, paragraph)):
            raw = match.group()
            trimmed = raw.strip()
            if not trimmed:
                continue
            start = offset + match.start() + len(raw) - len(raw.lstrip())
            end = start + len(trimmed)
            location = Location(paragraph_index=paragraph_index, sentence_index=sentence_index,
                                char_start=start, char_end=end)
            result.append(Sentence(text=trimmed, location=location,
                citations=citations(trimmed, start, paragraph_index, sentence_index, policy)))
        offset += len(paragraph) + len(separator)
    parsed_chars = sum(sum(not char.isspace() for char in sentence.text) for sentence in result)
    enforce(policy.limits.parser_gates, ParserFacts(
        unparsed_chars=sum(not char.isspace() for char in text) - parsed_chars))
    return tuple(result)
