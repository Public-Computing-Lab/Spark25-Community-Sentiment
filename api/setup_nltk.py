"""
NLTK Data Downloader

This script downloads necessary datasets from the Natural Language Toolkit (NLTK)
to facilitate text processing tasks such as tokenization, part-of-speech tagging,
and stopword removal.

The following NLTK resources are downloaded:
- punkt: A tokenizer for splitting text into sentences and words.
- punkt_tab: A tab-based version of the punkt tokenizer.
- stopwords: A list of common words (like 'the', 'a', 'and') that are generally ignored in text analysis.
- averaged_perceptron_tagger: A POS tagger for assigning part-of-speech tags to words.
- averaged_perceptron_tagger_eng: An English version of the POS tagger.

Dependencies:
- nltk (install via `pip install nltk`)

After running this script, the necessary data files will be available for use in text processing tasks.
"""

import nltk

nltk.download("punkt")
nltk.download("punkt_tab")
nltk.download("stopwords")
nltk.download("averaged_perceptron_tagger")
nltk.download("averaged_perceptron_tagger_eng")
print("NLTK data downloaded successfully!")
