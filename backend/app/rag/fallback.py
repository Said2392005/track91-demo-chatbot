"""Fixed fallback responses — plain strings, not LLM-generated, per the roadmap's rule that the
LLM never decides which system of record to hit and never speaks for gated content."""

PRICING_NO_APPROVED_DOC_RESPONSE = (
    "I don't have current pricing details for that — please contact our sales team for an "
    "accurate quote."
)

NO_RELEVANT_CONTENT_RESPONSE = (
    "I don't have information on that in our knowledge base — please contact support for help."
)
