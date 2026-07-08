from backend.core.response_quality import response_looks_related, response_relevance_score, content_terms

q = "explain your builder brain and how you work"
r = "My builder brain is designed to analyze project workspace structures and file patterns."

print("Q TERMS:", content_terms(q))
print("R TERMS:", content_terms(r))
print("SCORE:", response_relevance_score(q, r))
print("LOOKS RELATED:", response_looks_related(q, r))
