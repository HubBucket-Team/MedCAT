from medcat.preprocessing.tokenizers import spacy_split_all
from medcat.ner.vocab_based_ner import NER
from medcat.preprocessing.taggers import tag_skip_and_punct
from medcat.pipe import Pipe
from medcat.utils.normalizers import BasicSpellChecker
from medcat.vocab import Vocab
from medcat.preprocessing.cleaners import prepare_name
from medcat.linking.vector_context_model import ContextModel
from functools import partial
from medcat.linking.context_based_linker import Linker
from medcat.config import Config
import logging
from medcat.cdb import CDB
import os
import requests

config = Config()
config.general['log_level'] = logging.INFO
cdb = CDB(config=config)

nlp = Pipe(tokenizer=spacy_split_all, config=config)
nlp.add_tagger(tagger=partial(tag_skip_and_punct, config=config),
               name='skip_and_punct',
               additional_fields=['is_punct'])

# Add a couple of names
cdb.add_names(cui='S-229004', names=prepare_name('Movar', nlp, {}, config))
cdb.add_names(cui='S-229004', names=prepare_name('Movar viruses', nlp, {}, config))
cdb.add_names(cui='S-229005', names=prepare_name('CDB', nlp, {}, config))
# Check
#assert cdb.cui2names == {'S-229004': {'movar', 'movarvirus', 'movarviruses'}, 'S-229005': {'cdb'}}

vocab_path = "./tmp_vocab.dat"
if not os.path.exists(vocab_path):
    import requests
    tmp = requests.get("https://s3-eu-west-1.amazonaws.com/zkcl/vocab.dat")
    with open(vocab_path, 'wb') as f:
        f.write(tmp.content)

vocab = Vocab.load(vocab_path)
# Make the pipeline
nlp = Pipe(tokenizer=spacy_split_all, config=config)
nlp.add_tagger(tagger=partial(tag_skip_and_punct, config=config),
               name='skip_and_punct',
               additional_fields=['is_punct'])
spell_checker = BasicSpellChecker(cdb_vocab=cdb.vocab, config=config, data_vocab=vocab)
nlp.add_token_normalizer(spell_checker=spell_checker, config=config)
ner = NER(cdb, config)
nlp.add_ner(ner)

# Add Linker
link = Linker(cdb, vocab, config)
nlp.add_linker(link)

# Test limits for tokens and uppercase
config.ner['max_skip_tokens'] = 1
config.ner['upper_case_limit_len'] = 4
config.linking['disamb_length_limit'] = 2
text = "CDB - I was running and then Movar    Virus attacked and CDb"
d = nlp(text)

assert len(d._.ents) == 2
assert d._.ents[0]._.link_candidates[0] == 'S-229004'

# Change limit for skip
config.ner['max_skip_tokens'] = 3
d = nlp(text)
assert len(d._.ents) == 3

# Change limit for upper_case
config.ner['upper_case_limit_len'] = 3
d = nlp(text)
assert len(d._.ents) == 4

# Check name length limit
config.ner['min_name_len'] = 4
d = nlp(text)
assert len(d._.ents) == 2

# Speed tests
from timeit import default_timer as timer
text = "CDB - I was running and then Movar    Virus attacked and CDb"
text = text * 300
config.general['spell_check'] = True
start = timer()
for i in range(50):
    d = nlp(text)
end = timer()
print("Time: ", end - start)

# Now without spell check
config.general['spell_check'] = False
start = timer()
for i in range(50):
    d = nlp(text)
end = timer()
print("Time: ", end - start)


# Test for linker
import numpy as np

config = Config()
config.general['log_level'] = logging.DEBUG
cdb = CDB(config=config)

# Add a couple of names
cdb.add_names(cui='S-229004', names=prepare_name('Movar', nlp, {}, config))
cdb.add_names(cui='S-229004', names=prepare_name('Movar viruses', nlp, {}, config))
cdb.add_names(cui='S-229005', names=prepare_name('CDB', nlp, {}, config))
cdb.add_names(cui='S-2290045', names=prepare_name('Movar', nlp, {}, config))
# Check
#assert cdb.cui2names == {'S-229004': {'movar', 'movarvirus', 'movarviruses'}, 'S-229005': {'cdb'}, 'S-2290045': {'movar'}}

cuis = list(cdb.cui2names.keys())
for cui in cuis[0:50]:
    vectors = {'short': np.random.rand(300),
              'long': np.random.rand(300),
              'medium': np.random.rand(300)
              }
    cdb.update_context_vector(cui, vectors, negative=False)

vocab = Vocab.load(vocab_path)
cm = ContextModel(cdb, vocab, config)
cm.train_using_negative_sampling('S-229004')
config.linking['train_count_threshold'] = 0

cm.train('S-229004', d._.ents[1], d)

cm.similarity('S-229004', d._.ents[1], d)

cm.disambiguate(['S-2290045', 'S-229004'], d._.ents[1], 'movar', d)
