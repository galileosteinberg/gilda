import os
import time
import json
from collections import Counter
from indra.literature import pubmed_client
from gilda.grounder import Grounder
from gilda.resources import get_grounding_terms

grounding_terms_file = os.path.join(os.path.dirname(__file__), os.pardir,
                                    os.pardir, 'resources',
                                    'grounding_terms.tsv')

gr = Grounder(get_grounding_terms())


def get_ambiguities():
    ambig_entries = {}
    asserted_entries = []
    for terms in gr.entries.values():
        for term in terms:
            if term.status == 'assertion':
                asserted_entries.append(term.text)
            if term.db != 'HGNC':
                continue
            # We consider it an ambiguity if the same text entry appears
            # multiple times in the same DB
            key = term.text
            if key in ambig_entries:
                ambig_entries[key].append(term)
            else:
                ambig_entries[key] = [term]

    ambigs = []
    for text, entries in ambig_entries.items():
        # We skip assertions because they are prioritized anyway
        if text in asserted_entries:
            continue
        # If there aren't multiple entries, we skip it
        if len(entries) <= 1:
            continue
        # If the entries all point to the same ID, we skip it
        ids = {e.id for e in entries}
        if len(ids) <= 1:
            continue
        # If there is a name in statuses, we skip it because it's prioritized
        statuses = {e.status for e in entries}
        if 'name' in statuses:
            continue
        # Everything else is an ambiguity
        ambigs.append(entries)
    ambigs = filter_out_duplicates(ambigs)
    ambigs = filter_out_shared_prefix(ambigs)
    return ambigs


def filter_out_shared_prefix(ambigs):
    non_long_prefix_ambigs = []
    for terms in ambigs:
        names = [term.entry_name for term in terms]
        prefix = lcp(names)
        if len(prefix) < 3:
            non_long_prefix_ambigs.append(terms)
    return non_long_prefix_ambigs


def filter_out_duplicates(ambigs):
    unique_ambigs = []
    for terms in ambigs:
        keys = set()
        unique_terms = []
        for term in terms:
            key = tuple(term.to_list()[:-1])
            if key not in keys:
                keys.add(key)
                unique_terms.append(term)
        unique_ambigs.append(unique_terms)
    return unique_ambigs


def find_families(ambigs):
    # Find possible families
    for ambig in ambigs:
        names = [term.entry_name for term in ambig]
        prefix = lcp(names)
        if len(prefix) < 3:
            continue
        print('%s -> %s' % (ambig[0].text, ', '.join(sorted(names))))


def lcp(strs):
    # This function helps identify hypothetical families based on shared
    # prefixes
    prefix = ''
    for letters in zip(*strs):
        if len(set(letters)) == 1:
            prefix += letters[0]
        else:
            break
    return prefix


def get_abstract(pmid):
    from indra_db.util import get_db
    from indra_db.util.content_scripts import get_text_content_from_text_refs
    from indra.literature.adeft_tools import universal_extract_text
    print('Getting %s' % pmid)
    db = get_db('primary')
    content = get_text_content_from_text_refs(text_refs={'PMID': pmid},
                                              db=db)
    if content:
        text = universal_extract_text(content)
        return text
    return None


def get_papers(ambig_terms):
    gene_pmids = {}
    pmid_counter = Counter()
    for term in ambig_terms:
        gene = term.entry_name
        gene_pmids[gene] = pubmed_client.get_ids_for_gene(gene)
        pmid_counter.update(gene_pmids[gene])
    texts = []
    labels = []
    for gene, pmids in gene_pmids.items():
        print('Loading %d PMIDs for %s' % (len(pmids), gene))
        pmids = [p for p in pmids if pmid_counter[p] == 1]
        for pmid in pmids:
            abstract = get_abstract(pmid)
            if abstract:
                texts.append(abstract)
                labels.append(gene)
    return texts, labels


def rank_ambiguities(ambigs):
    with open('raw_agent_text_count.json') as fh:
        counts = json.load(fh)
    sorted_ambigs = sorted(ambigs, key=lambda x: counts.get(x[0].text, 0),
                           reverse=True)
    return sorted_ambigs


if __name__ == '__main__':
    ambigs = get_ambiguities()
    ambigs = rank_ambiguities(ambigs)
    find_families(ambigs)
    # texts, labels = get_papers(ambigs[27])
    # cl = AdeftClassifier(['p75'], list(set(labels)))