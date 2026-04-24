# TODO: Step 8 — MCP-wrapped tools (fastmcp)
#
# Tool 1 — pubmed_search(query, max_results=5) -> list[dict]
#   Bio.Entrez → {pmid, title, abstract, authors, pub_date, doi}
#   time.sleep(0.5) between calls to respect rate limits
#
# Tool 2 — web_search(query, max_results=3) -> list[dict]
#   Tavily client → {title, url, content, score}
#   Filters to trusted medical domains only:
#   pubmed.ncbi.nlm.nih.gov, nih.gov, who.int, cochrane.org, bmj.com,
#   nejm.org, mayoclinic.org, medscape.com, uptodate.com, nice.org.uk
#
# Tool 3 — download_and_parse(url, patient_id) -> dict
#   Downloads PDF/HTML → data/research/{patient_id}/
#   Runs through Docling parser
#   Skips if URL already in research_docs table
#   Returns {success, local_path, text_preview}
