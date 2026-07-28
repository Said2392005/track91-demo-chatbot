"""
Retrieval precision@k golden set — Phase 7 testing requirement (roadmap.md). One entry per
query; `relevant_doc_ids` is the set of source doc_ids (from kb_sources front-matter) a
retrieved chunk must belong to in order to count as relevant for precision@k purposes.

3 queries per KB category (5 categories) + 1 for the unapproved pricing doc specifically
(retrieval quality there matters even though the PRICING gate will reject it downstream) = 16.
"""

GOLDEN_SET = [
    # feature_guide
    {"query": "How does geofencing work?", "category": "feature_guide", "relevant_doc_ids": ["geofencing-feature-guide"]},
    {
        "query": "What happens when a vehicle enters or exits a geofence?",
        "category": "feature_guide",
        "relevant_doc_ids": ["geofencing-feature-guide"],
    },
    {
        "query": "How do I create a geofence from the dashboard?",
        "category": "feature_guide",
        "relevant_doc_ids": ["geofencing-feature-guide"],
    },
    # app_faq
    {
        "query": "How do I register a new GPS device?",
        "category": "app_faq",
        "relevant_doc_ids": ["track91-app-faq"],
    },
    {"query": "How do I add a driver to my fleet?", "category": "app_faq", "relevant_doc_ids": ["track91-app-faq"]},
    {
        "query": "How can I export my trip data as CSV?",
        "category": "app_faq",
        "relevant_doc_ids": ["track91-app-faq"],
    },
    # troubleshooting
    {
        "query": "My GPS device shows offline, what should I do?",
        "category": "troubleshooting",
        "relevant_doc_ids": ["gps-device-offline-troubleshooting"],
    },
    {
        "query": "Why would a GPS device stop sending data?",
        "category": "troubleshooting",
        "relevant_doc_ids": ["gps-device-offline-troubleshooting"],
    },
    {
        "query": "When should I contact support about a device issue?",
        "category": "troubleshooting",
        "relevant_doc_ids": ["gps-device-offline-troubleshooting"],
    },
    # policy
    {
        "query": "How long is trip and location history retained?",
        "category": "policy",
        "relevant_doc_ids": ["data-retention-policy"],
    },
    {
        "query": "What happens to my data if I cancel my subscription?",
        "category": "policy",
        "relevant_doc_ids": ["data-retention-policy"],
    },
    {
        "query": "How long are chat conversations stored?",
        "category": "policy",
        "relevant_doc_ids": ["data-retention-policy"],
    },
    # pricing — approved
    {
        "query": "How much does the Pro plan cost per month?",
        "category": "pricing",
        "relevant_doc_ids": ["track91-pricing-sheet"],
    },
    {
        "query": "What's included in the Enterprise plan?",
        "category": "pricing",
        "relevant_doc_ids": ["track91-pricing-sheet"],
    },
    {
        "query": "Is there a discount for paying annually?",
        "category": "pricing",
        "relevant_doc_ids": ["track91-pricing-sheet"],
    },
    # pricing — unapproved (retrieval should still find it; the PRICING gate rejects it later)
    {
        "query": "What is your custom pricing rate for 1000 or more vehicles?",
        "category": "pricing",
        "relevant_doc_ids": ["enterprise-pricing-draft-notes", "track91-pricing-sheet"],
    },
]
